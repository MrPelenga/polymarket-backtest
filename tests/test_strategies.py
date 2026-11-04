import numpy as np
import pandas as pd

from pmbt.categorize import categorize
from pmbt.collect import parse_market
from pmbt.strategies import calibration_table, estimate_calibration, estimate_momentum, estimate_random


def test_calibration_learns_bias():
    rng = np.random.default_rng(0)
    p = np.full(2000, 0.15)
    y = (rng.random(2000) < 0.05).astype(int)  # outsiders à 15 % qui ne gagnent que 5 % du temps
    table = calibration_table(pd.DataFrame({"prix_j3": p, "resultat_yes": y}))
    est = estimate_calibration(pd.DataFrame({"prix_j3": [0.15]}), table)
    assert est.iloc[0] < 0.08


def test_calibration_shrinks_small_buckets():
    table = calibration_table(pd.DataFrame({"prix_j3": [0.15] * 3, "resultat_yes": [1, 1, 1]}))
    est = estimate_calibration(pd.DataFrame({"prix_j3": [0.15]}), table)
    assert est.iloc[0] < 0.30  # 3 exemples ne suffisent pas à croire à 100 %


def test_momentum_without_history_is_neutral():
    est = estimate_momentum(pd.DataFrame({"prix_j3": [0.4], "prix_j7": [np.nan]}))
    assert est.iloc[0] == 0.4


def test_random_is_reproducible():
    d = pd.DataFrame({"prix_j3": [0.5] * 10})
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
    assert parse_market({**base, "outcomes": '["A","B"]', "outcomePrices": '["1","0"]'}) is None
