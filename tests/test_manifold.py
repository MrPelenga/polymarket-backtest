"""Tests hors ligne du module Manifold.

Les données de référence sont tirées de vraies réponses de l'API, obtenues depuis la France
le 4 novembre 2026 (search-markets et bets) ; seuls les champs inutiles ont été retirés.
"""

import json

import numpy as np
import pandas as pd
import pytest
import requests

from pmbt import config as C
from pmbt import manifold

# Réponse réelle de /v0/search-markets?filter=resolved&contractType=BINARY (question raccourcie)
MARKET_NO = {
    "id": "gwm12OQZf2V58a9JkAYP", "question": "Will Joe Biden say a swear word on camera before April 1st?",
    "url": "https://manifold.markets/Joshua/will-joe-biden-say-fuck-on-camera-b",
    "createdTime": 1707448257512, "closeTime": 1712010910052, "resolutionTime": 1712010910052,
    "probability": 0.0006282453992063229, "outcomeType": "BINARY", "mechanism": "cpmm-1",
    "volume": 107702.7131753061, "isResolved": True, "resolution": "NO", "uniqueBettorCount": 50,
    "token": "MANA",
}
MARKET_CANCEL = {
    "id": "GF2XuchW9kfFvtTbx3Ps",
    "question": "Will student loan payments resume by Sep 1st if SCOTUS permits Biden's student loan forgiveness to proceed?",
    "createdTime": 1677883374246, "closeTime": 1688137496869, "resolutionTime": 1688137496869,
    "outcomeType": "BINARY", "volume": 42814.582261094794, "isResolved": True, "resolution": "CANCEL",
    "uniqueBettorCount": 12, "token": "MANA",
}
# Réponse réelle de /v0/bets (du plus récent au plus ancien)
BETS = [
    {"id": "yXB8lVbs86TKkhWA1FVi", "outcome": "YES", "isFilled": False, "limitProb": 0.5,
     "probBefore": 0.5730753474948571, "probAfter": 0.5730753474948571, "createdTime": 1659482775970,
     "isCancelled": False, "isRedemption": False, "contractId": "Tz5dA01GkK5QKiQfZeDL"},
    {"id": "1LPJHNz5oAX4K6YtJlP1", "outcome": "YES", "isFilled": True,
     "probBefore": 0.5304358279113885, "probAfter": 0.5730753474948571, "createdTime": 1659482757271,
     "isCancelled": False, "isRedemption": False, "contractId": "Tz5dA01GkK5QKiQfZeDL"},
]


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Chaque test écrit dans un dossier temporaire et accepte les marchés anciens des exemples."""
    monkeypatch.setattr(C, "DATA", tmp_path)
    monkeypatch.setattr(C, "OUT", tmp_path / "powerbi")
    monkeypatch.setattr(manifold, "OUT_DIR", tmp_path / "manifold")
    monkeypatch.setattr(manifold, "CREATED_MIN", "2023-01-01")
    monkeypatch.setattr(manifold, "RESOLVED_MIN", "2023-01-01")
    monkeypatch.setattr(manifold, "PAUSE_S", 0)
    return tmp_path


class FakeResponse:
    def __init__(self, data, status=200):
        self.status_code, self._data = status, data

    def json(self):
        return self._data


class FakeSession:
    """Répond comme l'API Manifold et compte les appels."""

    def __init__(self, markets, bets):
        self.markets, self.bets, self.calls = markets, bets, []

    def get(self, url, params=None, timeout=None):
        assert timeout == manifold.TIMEOUT_S
        self.calls.append((url, params))
        if url.endswith("/search-markets"):
            return FakeResponse([] if params.get("beforeTime") else self.markets)
        return FakeResponse(self.bets)


class DownSession:
    def get(self, url, params=None, timeout=None):
        raise requests.ConnectionError("hors ligne")


def test_parse_keeps_resolved_no_market():
    row = manifold.parse_market(MARKET_NO)
    assert row["resultat"] == "NO" and row["resultat_yes"] == 0
    assert row["parieurs"] == 50
    assert row["date_cloture"] == pd.Timestamp(1712010910052, unit="ms", tz="UTC")


def test_parse_rejects_cancelled_market():
    assert manifold.parse_market(MARKET_CANCEL) is None


def test_parse_rejects_small_market():
    assert manifold.parse_market({**MARKET_NO, "uniqueBettorCount": 3}) is None


def test_parse_rejects_short_market():
    short = {**MARKET_NO, "closeTime": MARKET_NO["createdTime"] + manifold.DAY_MS}
    assert manifold.parse_market(short) is None


def test_price_uses_latest_valid_bet():
    assert manifold.price_from_bets(BETS) == pytest.approx(0.5730753474948571)
    cancelled_first = [{**BETS[0], "isCancelled": True, "probAfter": 0.99}, BETS[1]]
    assert manifold.price_from_bets(cancelled_first) == pytest.approx(0.5730753474948571)
    assert np.isnan(manifold.price_from_bets([]))


def test_run_writes_summary_and_is_incremental():
    session = FakeSession([MARKET_NO, MARKET_CANCEL], BETS)
    summary = manifold.run(session)
    assert summary["statut"] == "ok"
    assert summary["marches_avec_prix_j1"] == 1
    assert summary["source"].startswith("Données : Manifold")
    assert (C.OUT / "manifold_calibration.csv").exists()
    written = json.loads((manifold.OUT_DIR / "summary.json").read_text())
    assert written["brier_manifold"] == pytest.approx(0.5730753474948571 ** 2, abs=1e-4)

    # Le lendemain : le marché déjà traité n'est pas redemandé.
    session2 = FakeSession([MARKET_NO], BETS)
    manifold.run(session2)
    assert not any(url.endswith("/bets") for url, _ in session2.calls)
    assert len(manifold.load_cache()) == 1


def test_api_down_keeps_last_known_values():
    manifold.run(FakeSession([MARKET_NO], BETS))
    before = json.loads((manifold.OUT_DIR / "summary.json").read_text())

    after = manifold.run(DownSession())
    assert after["statut"] == "echec"
    assert after["brier_manifold"] == before["brier_manifold"]
    assert after["derniere_reussite"] == before["derniere_reussite"]
    assert after["message"]


def test_api_down_on_first_run_does_not_crash():
    summary = manifold.run(DownSession())
    assert summary["statut"] == "echec"
