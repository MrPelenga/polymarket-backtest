"""Backtest complet : prépare les données, joue chaque stratégie, exporte pour Power BI.

Sorties dans data/powerbi/ (schéma en étoile) et data/summary.json (résumé pour le site).
"""

from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from . import config as C
from .simulate import ARTICLE, FULL_KELLY, simulate
from .strategies import (calibration_table, estimate_calibration, estimate_momentum,
                         estimate_random, price_bucket)

log = logging.getLogger(__name__)

STRATEGIES = {
    "calibration": ("Calibration", "Règles de l'article",
                    "Corrige le prix selon les écarts constatés par tranche de prix en 2025."),
    "momentum_kelly_plein": ("Momentum", "Kelly plein, sans garde-fous",
                             "Même estimation que Momentum, mais mise de Kelly entière, sans plafond, ni limite, ni arrêt."),
    "momentum": ("Momentum", "Règles de l'article",
                 "Prolonge la tendance du prix entre J-2 et J-1."),
    "aleatoire": ("Aléatoire", "Règles de l'article",
                  f"Pile ou face, mêmes règles de mise. Tirage médian sur {C.RANDOM_RUNS}."),
}


def load() -> pd.DataFrame:
    m = pd.read_csv(C.RAW / "markets.csv", parse_dates=["date_cloture"])
    s = pd.read_csv(C.RAW / "snapshots.csv")
    m["market_id"] = m["market_id"].astype(str)
    s["market_id"] = s["market_id"].astype(str)
    df = m.merge(s, on="market_id", how="inner")
    df["date_cloture"] = pd.to_datetime(df["date_cloture"], utc=True)
    df["date_decision"] = df["date_cloture"] - pd.Timedelta(hours=C.DECISION_HOURS)
    df["prix"] = df[f"prix_j{C.DECISION_HOURS // 24}"]
    df["prix_avant"] = df[f"prix_j{C.MOMENTUM_FROM_HOURS // 24}"]
    df["periode"] = np.where(df["date_cloture"] < pd.Timestamp(C.TRAIN_END, tz="UTC"), "Apprentissage", "Test")
    return df


def brier(p: pd.Series, y: pd.Series) -> float:
    return float(((p - y) ** 2).mean())


def run() -> None:
    C.OUT.mkdir(parents=True, exist_ok=True)
    df = load()
    priced = df.dropna(subset=["prix"])
    train = priced[priced["periode"] == "Apprentissage"]
    test = priced[priced["periode"] == "Test"].copy()
    log.info("Marchés avec un prix au moment de la décision : %d (apprentissage %d, test %d)", len(priced), len(train), len(test))

    table = calibration_table(train)
    cols = ["market_id", "date_decision", "date_cloture", "prix", "resultat_yes"]

    runs: dict[str, tuple] = {}
    runs["calibration"] = simulate(test[cols].assign(proba=estimate_calibration(test, table)), ARTICLE, "calibration")
    runs["momentum"] = simulate(test[cols].assign(proba=estimate_momentum(test)), ARTICLE, "momentum")
    runs["momentum_kelly_plein"] = simulate(
        test[cols].assign(proba=estimate_momentum(test)), FULL_KELLY, "momentum_kelly_plein")

    # Stratégie aléatoire : on la joue de nombreuses fois pour voir la dispersion des résultats.
    random_runs = []
    for i in range(C.RANDOM_RUNS):
        b, c, s = simulate(test[cols].assign(proba=estimate_random(test, seed=C.SEED + i)), ARTICLE, "aleatoire")
        random_runs.append((s["cagnotte_finale"], i, (b, c, s)))
    random_runs.sort(key=lambda x: x[0])
    runs["aleatoire"] = random_runs[len(random_runs) // 2][2]
    dist = pd.DataFrame([{"tirage": i, "cagnotte_finale": v, "nb_paris": r[2]["nb_paris"],
                          "plus_haut": r[2]["plus_haut"]} for v, i, r in random_runs])

    # ---- Export Power BI ----------------------------------------------------
    bets = pd.concat([r[0] for r in runs.values()], ignore_index=True)
    curve = pd.concat([r[1] for r in runs.values()], ignore_index=True)
    summaries = [r[2] for r in runs.values()]

    marches = df[["market_id", "question", "evenement", "categorie", "date_cloture", "volume",
                  "resultat_yes", "periode", "prix_j7", "prix_j3", "prix_j2", "prix_j1"]].copy()
    marches["tranche_prix_decision"] = price_bucket(df["prix"]).astype(str).replace("nan", "")
    for frame, col in ((marches, "date_cloture"), (bets, "date_entree"), (bets, "date_cloture"), (curve, "date")):
        frame[col] = pd.to_datetime(frame[col], utc=True).dt.strftime("%Y-%m-%d %H:%M")

    calib = []
    for (periode, cat), g in priced.groupby(["periode", "categorie"]):
        t = calibration_table(g)[["tranche", "n", "prix_moyen", "freq_reelle"]]
        calib.append(t.assign(periode=periode, categorie=cat))
    for periode, g in priced.groupby("periode"):
        t = calibration_table(g)[["tranche", "n", "prix_moyen", "freq_reelle"]]
        calib.append(t.assign(periode=periode, categorie="Toutes"))
    calib = pd.concat(calib)

    strat = pd.DataFrame([{"strategie": k, "estimateur": v[0], "regles": v[1], "description": v[2]}
                          for k, v in STRATEGIES.items()])

    marches.to_csv(C.OUT / "marches.csv", index=False)
    bets.to_csv(C.OUT / "paris.csv", index=False)
    curve.to_csv(C.OUT / "cagnotte.csv", index=False)
    calib.to_csv(C.OUT / "calibration.csv", index=False)
    strat.to_csv(C.OUT / "strategies.csv", index=False)
    dist.to_csv(C.OUT / "aleatoire_tirages.csv", index=False)
    pd.DataFrame(summaries).to_csv(C.OUT / "resultats.csv", index=False)

    # ---- Résumé pour le site -----------------------------------------------
    collect_stats = json.loads((C.RAW / "collect_stats.json").read_text())
    by_cat = (priced.groupby("categorie")
              .apply(lambda g: pd.Series({"n": len(g), "brier": round(brier(g["prix"], g["resultat_yes"]), 4),
                                          "part_yes": round(g["resultat_yes"].mean(), 3)}), include_groups=False)
              .reset_index().sort_values("n", ascending=False))
    # Paris par stratégie et par catégorie : le rendement par dollar misé ne dépend pas
    # de la taille de la cagnotte, on peut donc comparer les catégories entre elles.
    all_bets = pd.concat([r[0] for r in runs.values()], ignore_index=True)
    by_cat_bets = (all_bets.merge(df[["market_id", "categorie"]], on="market_id")
                   .groupby(["strategie", "categorie"])
                   .agg(nb_paris=("gain", "size"), gain=("gain", "sum"), mise=("mise", "sum"), reussite=("gagne", "mean"))
                   .reset_index())
    # Plus grand écart de calibration par catégorie sur 2026 (tranches d'au moins 30 marchés) :
    # c'est l'avantage maximal qu'une correction statistique aurait pu exploiter.
    gaps = []
    for cat, g in test.groupby("categorie"):
        t = calibration_table(g)
        t = t[t["n"] >= 30]
        gaps.append({"categorie": cat, "n_test": len(g),
                     "ecart_max_points": round(float((t["freq_reelle"] - t["prix_moyen"]).abs().max() * 100), 1)
                     if len(t) else None})

    # Courbe hebdomadaire prolongée jusqu'à la fin du test : une stratégie arrêtée reste à plat.
    weeks = pd.date_range(C.TRAIN_END, C.END_MAX, freq="W", tz="UTC")

    def weekly(c: pd.DataFrame) -> list[dict]:
        s = c.assign(date=pd.to_datetime(c["date"], utc=True)).set_index("date")["cagnotte"].sort_index()
        s = s.resample("W").last().reindex(weeks).ffill().fillna(C.BANKROLL)
        start = [{"date": C.TRAIN_END, "cagnotte": C.BANKROLL}]
        return start + [{"date": d.strftime("%Y-%m-%d"), "cagnotte": round(float(v), 2)} for d, v in s.items()]

    summary = {
        "collecte": collect_stats,
        "periodes": {"apprentissage": f"{C.END_MIN} → {C.TRAIN_END}", "test": f"{C.TRAIN_END} → {C.END_MAX}"},
        "volumes": {"marches_avec_prix": len(priced), "apprentissage": len(train), "test": len(test)},
        "brier_marche": round(brier(priced["prix"], priced["resultat_yes"]), 4),
        "resultats": summaries,
        "courbes": {k: weekly(r[1]) for k, r in runs.items()},
        "calibration_test": calibration_table(test)[["tranche", "n", "prix_moyen", "freq_reelle"]]
        .round(4).to_dict("records"),
        "calibration_apprentissage": table[["tranche", "n", "prix_moyen", "freq_reelle", "ecart"]]
        .round(4).to_dict("records"),
        "categories": by_cat.to_dict("records"),
        "paris_par_categorie": by_cat_bets.round(3).to_dict("records"),
        "ecarts_calibration_test": gaps,
        "brier_test": round(brier(test["prix"], test["resultat_yes"]), 4),
        "aleatoire": {
            "tirages": C.RANDOM_RUNS,
            "mediane": float(dist["cagnotte_finale"].median()),
            "meilleur": float(dist["cagnotte_finale"].max()),
            "meilleur_plus_haut": float(dist["plus_haut"].max()),
            "part_gagnants_pct": round((dist["cagnotte_finale"] > C.BANKROLL).mean() * 100, 1),
            "histogramme": np.histogram(dist["cagnotte_finale"], bins=12)[0].tolist(),
            "bornes": [round(x, 2) for x in np.histogram(dist["cagnotte_finale"], bins=12)[1].tolist()],
        },
        "regles": {"cagnotte": C.BANKROLL, "ecart_min_points": C.MIN_EDGE * 100, "kelly": C.KELLY_FRACTION,
                   "plafond_pct": C.MAX_STAKE_PCT * 100, "max_ouverts": C.MAX_OPEN,
                   "stop_pct": C.STOP_DRAWDOWN * 100, "glissement_points": C.SLIPPAGE * 100,
                   "mise_min": C.MIN_STAKE, "decision_heures": C.DECISION_HOURS,
                   "duree_min_jours": C.MIN_LIFESPAN_DAYS},
    }
    (C.DATA / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    for s in summaries:
        log.info("%s", s)
