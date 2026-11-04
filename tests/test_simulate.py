import pandas as pd
import pytest

from pmbt.simulate import ARTICLE, FULL_KELLY, Rules, decide, simulate


def t(day: int, hour: int = 0) -> pd.Timestamp:
    return pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=day, hours=hour)


def cands(rows):
    return pd.DataFrame(rows, columns=["market_id", "date_decision", "date_cloture", "prix", "proba", "resultat_yes"])


def test_decide_skips_small_edge():
    # 62 % contre 66 % : 4 points d'écart moins 1 point de glissement, sous le seuil de 8
    assert decide(0.62, 0.66, ARTICLE) is None


def test_decide_yes_and_kelly():
    side, cost, kelly = decide(0.62, 0.74, ARTICLE)  # l'exemple de l'article
    assert side == "YES"
    assert cost == pytest.approx(0.63)
    assert kelly == pytest.approx((0.74 - 0.63) / (1 - 0.63))


def test_decide_no_side():
    side, cost, _ = decide(0.70, 0.50, ARTICLE)
    assert side == "NO"
    assert cost == pytest.approx(0.31)


def test_decide_rejects_expensive_contract():
    assert decide(0.98, 0.999, ARTICLE) is None


def test_stake_capped_at_six_percent():
    bets, _, _ = simulate(cands([["a", t(0), t(1), 0.20, 0.80, 1]]), ARTICLE, "x")
    assert bets.loc[0, "mise"] == pytest.approx(50 * 0.06)


def test_full_kelly_is_not_capped():
    bets, _, _ = simulate(cands([["a", t(0), t(1), 0.20, 0.80, 1]]), FULL_KELLY, "x")
    assert bets.loc[0, "mise"] > 50 * 0.5


def test_win_payout():
    bets, curve, s = simulate(cands([["a", t(0), t(1), 0.20, 0.80, 1]]), ARTICLE, "x")
    stake = 3.0
    assert bets.loc[0, "gain"] == pytest.approx(stake / 0.21 - stake, abs=1e-3)
    assert s["cagnotte_finale"] == pytest.approx(50 + stake / 0.21 - stake, abs=0.01)


def test_max_open_bets():
    rows = [[str(i), t(0, i), t(10), 0.20, 0.80, 0] for i in range(8)]
    bets, _, s = simulate(cands(rows), ARTICLE, "x")
    assert len(bets) == 5
    assert s["ignores_limite_paris_ouverts"] == 3


def test_money_is_locked_until_resolution():
    rows = [[str(i), t(0, i), t(10), 0.20, 0.80, 0] for i in range(3)]
    bets, _, _ = simulate(cands(rows), Rules(max_stake_pct=0.5, kelly_fraction=1.0), "x")
    assert bets["mise"].sum() <= 50 + 1e-9


def test_stop_after_drawdown():
    # Paris perdants successifs, mises plafonnées à 30 % : l'arrêt à -40 % doit se déclencher
    rules = Rules(max_stake_pct=0.30, kelly_fraction=1.0)
    rows = [[str(i), t(i), t(i, 12), 0.20, 0.80, 0] for i in range(10)]
    bets, _, s = simulate(cands(rows), rules, "x")
    assert s["arret_date"] is not None
    assert len(bets) < 10
    assert s["drawdown_max_pct"] >= 40


def test_min_stake_blocks_tiny_bets():
    rules = Rules(bankroll=10.0)
    bets, _, s = simulate(cands([["a", t(0), t(1), 0.20, 0.80, 1]]), rules, "x")
    assert len(bets) == 0 and s["ignores_mise_trop_faible"] == 1
