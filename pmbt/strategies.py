"""Les « estimateurs » qui remplacent l'IA de l'article.

L'article ne dit pas comment l'agent calcule sa probabilité (lecture de X, intuition
du modèle…). Un backtest honnête ne peut pas rejouer ce qui se disait sur X il y a un an.
On teste donc des estimateurs reproductibles, chacun avec une hypothèse claire :

- calibration : le marché se trompe de façon régulière selon le niveau de prix
  (ex. les outsiders à 10 % gagnent en réalité moins souvent). L'écart est appris
  sur 2025 et appliqué à 2026, donc sans regarder les résultats qu'on cherche à prédire.
- momentum    : un prix qui monte entre J-7 et J-3 continue de monter.
- aléatoire   : on parie au hasard, avec exactement les mêmes règles de mise.
  C'est la référence : une stratégie qui ne fait pas mieux n'a aucun avantage.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BUCKETS = np.linspace(0, 1, 11)  # tranches de 10 points
SHRINK = 30                      # poids du prix du marché quand une tranche a peu d'exemples


def price_bucket(p: pd.Series) -> pd.Series:
    labels = [f"{int(a * 100)}-{int(b * 100)} %" for a, b in zip(BUCKETS[:-1], BUCKETS[1:])]
    return pd.cut(p, BUCKETS, labels=labels, include_lowest=True)


def calibration_table(train: pd.DataFrame, price_col: str = "prix_j3") -> pd.DataFrame:
    """Pour chaque tranche de prix : prix moyen, fréquence réelle de « Yes », et estimation lissée.

    Le lissage tire la fréquence observée vers le prix du marché quand la tranche compte
    peu de marchés : on ne croit à un écart que s'il repose sur assez d'exemples.
    """
    d = train.dropna(subset=[price_col]).assign(tranche=lambda x: price_bucket(x[price_col]))
    g = d.groupby("tranche", observed=True).agg(
        n=("resultat_yes", "size"), prix_moyen=(price_col, "mean"), freq_reelle=("resultat_yes", "mean"))
    g["estimation"] = (g["freq_reelle"] * g["n"] + g["prix_moyen"] * SHRINK) / (g["n"] + SHRINK)
    g["ecart"] = g["estimation"] - g["prix_moyen"]
    return g.reset_index()


def estimate_calibration(test: pd.DataFrame, table: pd.DataFrame) -> pd.Series:
    """Probabilité estimée = prix + écart moyen constaté dans sa tranche sur la période d'apprentissage."""
    ecart = price_bucket(test["prix_j3"]).map(dict(zip(table["tranche"], table["ecart"]))).astype(float)
    return (test["prix_j3"] + ecart.fillna(0)).clip(0.01, 0.99)


def estimate_momentum(test: pd.DataFrame, k: float = 1.0) -> pd.Series:
    """Prolonge la tendance J-7 → J-3. Sans prix à J-7, aucune tendance : estimation = prix."""
    trend = (test["prix_j3"] - test["prix_j7"]).fillna(0)
    return (test["prix_j3"] + k * trend).clip(0.01, 0.99)


def estimate_random(test: pd.DataFrame, seed: int, size: float = 0.15) -> pd.Series:
    """Écart de ±15 points tiré à pile ou face : assez pour franchir le seuil de 8 points."""
    rng = np.random.default_rng(seed)
    sign = rng.choice([-1.0, 1.0], size=len(test))
    return (test["prix_j3"] + sign * size).clip(0.01, 0.99)
