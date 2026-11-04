import numpy as np
import pandas as pd

from pmbt.categorize import categorize
from pmbt.collect import parse_market
from pmbt.strategies import calibration_table, estimate_calibration, estimate_momentum, estimate_random


def test_calibration_learns_bias():
    rng = np.random.default_rng(0)
    p = np.full(2000, 0.15)
    y = (rng.random(2000) < 0.05).astype(int)  # outsiders à 15 % qui ne gagnent que 5 % du temps
    table = calibration_table(pd.DataFrame({"prix": p, "resultat_yes": y}))
    est = estimate_calibration(pd.DataFrame({"prix": [0.15]}), table)
    assert est.iloc[0] < 0.08


def test_calibration_shrinks_small_buckets():
    table = calibration_table(pd.DataFrame({"prix": [0.15] * 3, "resultat_yes": [1, 1, 1]}))
    est = estimate_calibration(pd.DataFrame({"prix": [0.15]}), table)
    assert est.iloc[0] < 0.30  # 3 exemples ne suffisent pas à croire à 100 %


def test_momentum_without_history_is_neutral():
    est = estimate_momentum(pd.DataFrame({"prix": [0.4], "prix_avant": [np.nan]}))
    assert est.iloc[0] == 0.4


def test_random_is_reproducible():
    d = pd.DataFrame({"prix": [0.5] * 10})
    assert estimate_random(d, 1).equals(estimate_random(d, 1))


def test_categorize():
    assert categorize("Will Bitcoin reach $150k by June?") == "Crypto"
    assert categorize("Highest temperature in NYC on May 3?") == "Météo"
    assert categorize("Lakers vs. Celtics") == "Sport"
    assert categorize("Will it happen?") == "Autre"


def test_parse_market_keeps_resolved_binary():
    m = {"id": 1, "question": "Will Bitcoin hit $100k?", "outcomes": '["Yes","No"]',
         "outcomePrices": '["0","1"]', "clobTokenIds": '["111","222"]',
         "endDate": "2026-03-01T00:00:00Z", "closedTime": "2026-02-27 10:00:00+00", "volumeNum": 12000}
    p = parse_market(m)
    assert p["resultat_yes"] == 0 and p["token_yes"] == "111" and p["categorie"] == "Crypto"
    assert p["date_cloture"] == pd.Timestamp("2026-02-27 10:00", tz="UTC")


def test_parse_market_rejects_unresolved_and_multi():
    base = {"id": 1, "question": "q", "clobTokenIds": '["1","2"]', "endDate": "2026-03-01T00:00:00Z",
            "volumeNum": 12000}
    assert parse_market({**base, "outcomes": '["Yes","No"]', "outcomePrices": '["0.5","0.5"]'}) is None
    assert parse_market({**base, "outcomes": '["A","B","C"]', "outcomePrices": '["1","0","0"]'}) is None


def test_parse_market_accepts_team_matchups():
    m = {"id": 2, "question": "Lakers vs. Celtics", "outcomes": '["Lakers","Celtics"]',
         "outcomePrices": '["1","0"]', "clobTokenIds": '["1","2"]', "endDate": "2026-03-01T00:00:00Z",
         "volumeNum": 9000}
    p = parse_market(m)
    assert p["resultat_yes"] == 1 and p["issue_1"] == "Lakers" and p["categorie"] == "Sport"


def test_fetch_markets_slides_window_past_offset_cap(monkeypatch):
    """L'API refuse les décalages > ~2 000 : la collecte doit repartir de la dernière date reçue."""
    import pmbt.collect as col

    days = pd.date_range("2025-01-01", periods=450, freq="D", tz="UTC")
    universe = [{"id": i, "endDate": d.strftime("%Y-%m-%dT%H:%M:%SZ")} for i, d in enumerate(days.repeat(10))]

    def fake_get(url, params):
        assert params["offset"] <= 1900
        rows = [m for m in universe if m["endDate"] >= params["end_date_min"]]
        return rows[params["offset"]: params["offset"] + params["limit"]]

    monkeypatch.setattr(col, "_get", fake_get)
    got = col.fetch_markets()
    assert len(got) == len(universe)
