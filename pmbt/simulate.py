"""Simulation chronologique d'une cagnotte avec les règles de l'article.

Déroulé : les marchés sont parcourus dans l'ordre où la décision aurait été prise
(J-3 avant leur clôture). Avant chaque décision, on encaisse les paris déjà résolus.
L'argent misé reste bloqué jusqu'à la résolution, comme sur le vrai site.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import config as C


@dataclass(frozen=True)
class Rules:
    bankroll: float = C.BANKROLL
    min_edge: float = C.MIN_EDGE
    kelly_fraction: float = C.KELLY_FRACTION
    max_stake_pct: float | None = C.MAX_STAKE_PCT  # None = pas de plafond
    max_open: int | None = C.MAX_OPEN               # None = pas de limite
    stop_drawdown: float | None = C.STOP_DRAWDOWN   # None = jamais d'arrêt
    slippage: float = C.SLIPPAGE
    min_stake: float = C.MIN_STAKE
    max_entry_price: float = C.MAX_ENTRY_PRICE


BET_COLUMNS = ["strategie", "market_id", "date_entree", "date_cloture", "sens", "prix_yes", "prix_paye",
               "proba_estimee", "ecart_points", "pct_cagnotte", "mise", "resultat_yes", "gagne", "gain",
               "cagnotte_apres"]

ARTICLE = Rules()
FULL_KELLY = Rules(kelly_fraction=1.0, max_stake_pct=None, max_open=None, stop_drawdown=None)


def decide(price_yes: float, proba: float, rules: Rules) -> tuple[str, float, float] | None:
    """Renvoie (sens, prix payé, fraction de Kelly) ou None si le pari ne passe pas les filtres.

    Acheter « Yes » coûte le prix + glissement ; acheter « No » coûte (1 - prix) + glissement.
    Kelly pour un contrat qui paie 1 $ acheté au prix c avec une probabilité q : f = (q - c) / (1 - c).
    """
    cost_yes = price_yes + rules.slippage
    cost_no = (1 - price_yes) + rules.slippage
    edge_yes = proba - cost_yes
    edge_no = (1 - proba) - cost_no
    side, cost, q = ("YES", cost_yes, proba) if edge_yes >= edge_no else ("NO", cost_no, 1 - proba)
    if q - cost < rules.min_edge or cost >= rules.max_entry_price or cost <= 0:
        return None
    kelly = (q - cost) / (1 - cost)
    return side, cost, kelly


def simulate(cands: pd.DataFrame, rules: Rules, label: str) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """cands : market_id, date_decision, date_cloture, prix_j3, proba, resultat_yes."""
    cands = cands.sort_values("date_decision")
    cash = rules.bankroll
    peak = rules.bankroll
    open_bets: list[dict] = []
    bets: list[dict] = []
    curve: list[dict] = [{"date": cands["date_decision"].min(), "cagnotte": cash}]
    stopped_at = None
    skipped = {"ecart_insuffisant": 0, "limite_paris_ouverts": 0, "mise_trop_faible": 0}

    def equity() -> float:
        return cash + sum(b["mise"] for b in open_bets)

    def settle(until: pd.Timestamp) -> None:
        nonlocal cash, peak, stopped_at
        for b in sorted([b for b in open_bets if b["date_cloture"] <= until], key=lambda b: b["date_cloture"]):
            open_bets.remove(b)
            won = (b["sens"] == "YES") == bool(b["resultat_yes"])
            payout = b["mise"] / b["prix_paye"] if won else 0.0
            cash += payout
            b.update(gagne=int(won), gain=round(payout - b["mise"], 4))
            eq = equity()
            peak = max(peak, eq)
            b["cagnotte_apres"] = round(eq, 4)
            curve.append({"date": b["date_cloture"], "cagnotte": eq})
            if rules.stop_drawdown is not None and stopped_at is None and eq <= peak * (1 - rules.stop_drawdown):
                stopped_at = b["date_cloture"]

    for r in cands.itertuples():
        settle(r.date_decision)
        if stopped_at is not None:
            break
        d = decide(r.prix_j3, r.proba, rules)
        if d is None:
            skipped["ecart_insuffisant"] += 1
            continue
        if rules.max_open is not None and len(open_bets) >= rules.max_open:
            skipped["limite_paris_ouverts"] += 1
            continue
        side, cost, kelly = d
        pct = kelly * rules.kelly_fraction
        if rules.max_stake_pct is not None:
            pct = min(pct, rules.max_stake_pct)
        eq0 = equity()
        stake = min(pct * eq0, cash)
        if stake < rules.min_stake:
            skipped["mise_trop_faible"] += 1
            continue
        cash -= stake
        bet = {
            "strategie": label, "market_id": r.market_id, "date_entree": r.date_decision,
            "date_cloture": r.date_cloture, "sens": side, "prix_yes": round(r.prix_j3, 4),
            "prix_paye": round(cost, 4), "proba_estimee": round(r.proba, 4),
            "ecart_points": round((((r.proba if side == "YES" else 1 - r.proba) - cost) * 100), 2),
            "pct_cagnotte": round(stake / eq0, 4),
            "mise": round(stake, 4), "resultat_yes": r.resultat_yes,
        }
        open_bets.append(bet)
        bets.append(bet)

    # Les paris encore ouverts au moment d'un arrêt sont laissés aller à leur terme.
    settle(pd.Timestamp.max.tz_localize("UTC"))

    bets_df = pd.DataFrame(bets, columns=BET_COLUMNS)
    curve_df = pd.DataFrame(curve).assign(strategie=label)
    final = float(curve_df["cagnotte"].iloc[-1])
    running_peak = curve_df["cagnotte"].cummax()
    summary = {
        "strategie": label,
        "cagnotte_finale": round(final, 2),
        "roi_pct": round((final / rules.bankroll - 1) * 100, 1),
        "nb_paris": len(bets_df),
        "taux_reussite_pct": round(float(bets_df["gagne"].mean()) * 100, 1) if len(bets_df) else None,
        "drawdown_max_pct": abs(round(float(((curve_df["cagnotte"] / running_peak) - 1).min()) * 100, 1)),
        "plus_haut": round(float(running_peak.max()), 2),
        "arret_date": stopped_at.strftime("%Y-%m-%d") if stopped_at is not None else None,
        **{f"ignores_{k}": v for k, v in skipped.items()},
    }
    return bets_df, curve_df, summary
