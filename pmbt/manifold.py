"""Contre-épreuve Manifold : un marché de prédiction en monnaie fictive est-il aussi bien
calibré que Polymarket ?

API publique, sans compte ni clé (https://api.manifold.markets, limite : 500 appels/min par IP) :
- /v0/search-markets : les marchés binaires résolus ;
- /v0/bets           : les paris d'un marché, chacun avec la probabilité avant/après (probBefore/probAfter).

Le prix d'un marché à J-1 est la probabilité affichée juste après le dernier pari placé
24 h avant la clôture : c'est le même moment de décision que pour Polymarket.

Le script est incrémental : data/manifold/marches.csv sert de cache. Un marché déjà traité
n'est jamais redemandé, ce qui permet un passage quotidien sans approcher la limite d'appels.
Si l'API ne répond pas, les données de la veille restent en place et summary.json
l'indique (statut « echec », date du dernier succès).

Sorties :
- data/manifold/marches.csv        : cache, un marché par ligne ;
- data/manifold/summary.json       : résumé lu par le portfolio ;
- data/powerbi/manifold_marches.csv et manifold_calibration.csv : tables pour Power BI.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

from . import config as C
from .strategies import price_bucket

log = logging.getLogger(__name__)

# --- Réglages (ici plutôt que dans config.py : modifier config.py relance la collecte Polymarket) ---
API_URL = "https://api.manifold.markets/v0"
OUT_DIR = C.DATA / "manifold"
CREATED_MIN = "2025-07-01"     # marchés créés à partir de cette date...
RESOLVED_MIN = "2026-01-01"    # ...et résolus pendant la période de test Polymarket
MIN_BETTORS = 10               # écarte les marchés trop confidentiels
MAX_PRICED_PER_RUN = 1500      # nouveaux marchés dont on cherche le prix à chaque passage
TIMEOUT_S = 8                  # délai maximum d'un appel
PAUSE_S = 0.15                 # ≈ 400 appels/min, sous la limite de 500/min par IP

SOURCE = "Données : Manifold Markets (api.manifold.markets)"
CACHE_COLUMNS = [
    "market_id", "question", "url", "date_creation", "date_cloture", "date_resolution",
    "resultat", "resultat_yes", "parieurs", "volume", "prix_j1", "collecte_le",
]
DAY_MS = 86_400_000


def new_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = "polymarket-backtest (projet portfolio data)"
    return s


def _get(session: requests.Session, path: str, params: dict, tries: int = 4) -> object:
    """GET avec délai maximum de 8 s et quelques reprises sur les erreurs passagères."""
    url = f"{API_URL}{path}"
    for i in range(tries):
        try:
            r = session.get(url, params=params, timeout=TIMEOUT_S)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504) and i < tries - 1:
                log.warning("Manifold HTTP %s, nouvel essai dans %ss", r.status_code, 2 ** i)
                time.sleep(2 ** i)
                continue
            raise RuntimeError(f"Manifold HTTP {r.status_code} sur {path}")
        except requests.RequestException as e:
            if i == tries - 1:
                raise RuntimeError(f"Manifold injoignable sur {path} : {e}") from e
            log.warning("Manifold, erreur réseau (%s), nouvel essai", e)
            time.sleep(2 ** i)
    raise RuntimeError(f"Manifold : échec après {tries} essais sur {path}")


def _ms_to_ts(ms) -> pd.Timestamp:
    return pd.Timestamp(int(ms), unit="ms", tz="UTC")


def parse_market(m: dict) -> dict | None:
    """Garde un marché binaire résolu Oui/Non, assez suivi et ouvert assez longtemps.

    Les résolutions CANCEL (annulé) ou MKT (au prix du marché) n'ont pas de vrai résultat :
    elles fausseraient la mesure de précision.
    """
    if m.get("outcomeType") != "BINARY" or not m.get("isResolved"):
        return None
    if m.get("resolution") not in ("YES", "NO"):
        return None
    if (m.get("uniqueBettorCount") or 0) < MIN_BETTORS:
        return None
    created, close, resolved = m.get("createdTime"), m.get("closeTime"), m.get("resolutionTime")
    if not (created and close and resolved):
        return None
    if resolved < pd.Timestamp(RESOLVED_MIN, tz="UTC").value // 1_000_000:
        return None
    if (close - created) < C.MIN_LIFESPAN_DAYS * DAY_MS:
        return None
    return {
        "market_id": m["id"],
        "question": m.get("question", ""),
        "url": m.get("url", ""),
        "date_creation": _ms_to_ts(created),
        "date_cloture": _ms_to_ts(close),
        "date_resolution": _ms_to_ts(resolved),
        "resultat": m["resolution"],
        "resultat_yes": int(m["resolution"] == "YES"),
        "parieurs": int(m.get("uniqueBettorCount") or 0),
        "volume": float(m.get("volume") or 0.0),
    }


def price_from_bets(bets: list[dict]) -> float:
    """Probabilité affichée après le pari le plus récent de la liste (triée du plus récent au plus ancien).

    On ignore les paris annulés et les rachats de parts (isRedemption), qui ne reflètent pas
    une décision d'un parieur. Un ordre limite non exécuté reste valable : son probAfter
    est simplement la probabilité du moment.
    """
    for b in bets:
        if b.get("isCancelled") or b.get("isRedemption"):
            continue
        p = b.get("probAfter")
        if isinstance(p, (int, float)) and 0 <= p <= 1:
            return float(p)
    return np.nan


def fetch_resolved(session: requests.Session, known: set[str]) -> list[dict]:
    """Parcourt les marchés binaires résolus, du plus récent au plus ancien (par date de création)."""
    created_min = pd.Timestamp(CREATED_MIN, tz="UTC").value // 1_000_000
    params = {"filter": "resolved", "contractType": "BINARY", "sort": "newest", "limit": 1000}
    out, before = [], None
    while True:
        page = _get(session, "/search-markets", {**params, **({"beforeTime": before} if before else {})})
        if not page:
            break
        for m in page:
            if m.get("id") in known:
                continue
            row = parse_market(m)
            if row:
                out.append(row)
        oldest = min(m.get("createdTime", 0) for m in page)
        if oldest < created_min or len(page) < params["limit"] or oldest == before:
            break
        before = oldest
        time.sleep(PAUSE_S)
    log.info("Manifold : %d nouveaux marchés éligibles", len(out))
    return out


def price_at_decision(session: requests.Session, market_id: str, close: pd.Timestamp) -> float:
    decision_ms = int((close - pd.Timedelta(hours=C.DECISION_HOURS)).value // 1_000_000)
    bets = _get(session, "/bets", {"contractId": market_id, "beforeTime": decision_ms,
                                   "limit": 50, "order": "desc"})
    return price_from_bets(bets or [])


def load_cache() -> pd.DataFrame:
    path = OUT_DIR / "marches.csv"
    if not path.exists():
        return pd.DataFrame(columns=CACHE_COLUMNS)
    df = pd.read_csv(path, dtype={"market_id": str})
    for col in ("date_creation", "date_cloture", "date_resolution"):
        df[col] = pd.to_datetime(df[col], utc=True)
    return df


def brier(p: pd.Series, y: pd.Series) -> float:
    return float(((p - y) ** 2).mean())


def build_summary(cache: pd.DataFrame, now: str, polymarket_brier: float | None) -> dict:
    priced = cache.dropna(subset=["prix_j1"])
    calib = (priced.assign(tranche=price_bucket(priced["prix_j1"]))
             .groupby("tranche", observed=True)
             .agg(n=("resultat_yes", "size"), prix_moyen=("prix_j1", "mean"), freq_reelle=("resultat_yes", "mean"))
             .reset_index())
    calib["tranche"] = calib["tranche"].astype(str)
    calib["ecart_points"] = (calib["freq_reelle"] - calib["prix_moyen"]) * 100
    return {
        "statut": "ok",
        "message": None,
        "source": SOURCE,
        "derniere_reussite": now,
        "derniere_tentative": now,
        "periode": f"marchés résolus depuis le {RESOLVED_MIN}",
        "marches_traites": int(len(cache)),
        "marches_avec_prix_j1": int(len(priced)),
        "brier_manifold": round(brier(priced["prix_j1"], priced["resultat_yes"]), 4) if len(priced) else None,
        "brier_polymarket_test": polymarket_brier,
        "ecart_max_points": round(float(calib["ecart_points"].abs().max()), 1) if len(calib) else None,
        "calibration": [
            {"tranche": r.tranche, "n": int(r.n), "prix_moyen": round(float(r.prix_moyen), 4),
             "freq_reelle": round(float(r.freq_reelle), 4)}
            for r in calib.itertuples()
        ],
        "regles": {"decision_heures": C.DECISION_HOURS, "parieurs_min": MIN_BETTORS,
                   "duree_min_jours": C.MIN_LIFESPAN_DAYS},
    }


def _write_json(path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _polymarket_brier() -> float | None:
    path = C.DATA / "summary.json"
    if not path.exists():
        return None
    return json.loads(path.read_text()).get("brier_test")


def run(session: requests.Session | None = None) -> dict:
    """Passage quotidien. Ne lève jamais d'erreur réseau : en cas d'échec, la dernière valeur connue reste."""
    session = session or new_session()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    C.OUT.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    summary_path = OUT_DIR / "summary.json"
    cache = load_cache()

    try:
        new = fetch_resolved(session, set(cache["market_id"].astype(str)))
    except Exception as e:  # API tombée ou format changé : on garde la veille
        log.error("Manifold indisponible, données précédentes conservées : %s", e)
        previous = json.loads(summary_path.read_text()) if summary_path.exists() else {"source": SOURCE}
        previous.update({"statut": "echec", "derniere_tentative": now,
                         "message": "Manifold n'a pas répondu ; affichage de la dernière mise à jour réussie."})
        _write_json(summary_path, previous)
        return previous

    rows, failures = [], 0
    for m in new[: MAX_PRICED_PER_RUN]:
        try:
            m["prix_j1"] = price_at_decision(session, m["market_id"], m["date_cloture"])
        except Exception as e:  # un marché raté sera retenté le lendemain
            failures += 1
            log.warning("Prix J-1 indisponible pour %s : %s", m["market_id"], e)
            continue
        m["collecte_le"] = now
        rows.append(m)
        time.sleep(PAUSE_S)
    log.info("Manifold : %d marchés ajoutés, %d en échec, %d reportés au prochain passage",
             len(rows), failures, max(0, len(new) - MAX_PRICED_PER_RUN))

    if rows:
        cache = pd.concat([cache, pd.DataFrame(rows)[CACHE_COLUMNS]], ignore_index=True)
    cache = cache.sort_values("date_resolution").reset_index(drop=True)
    cache.to_csv(OUT_DIR / "marches.csv", index=False)

    summary = build_summary(cache, now, _polymarket_brier())
    _write_json(summary_path, summary)

    cache.drop(columns=["question", "url"]).to_csv(C.OUT / "manifold_marches.csv", index=False)
    pd.DataFrame(summary["calibration"]).assign(source="Manifold").to_csv(
        C.OUT / "manifold_calibration.csv", index=False)
    log.info("Manifold : Brier %s sur %d marchés", summary["brier_manifold"], summary["marches_avec_prix_j1"])
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
