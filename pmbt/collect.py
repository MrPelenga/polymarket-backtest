"""Collecte des marchés Polymarket résolus et de leurs prix historiques.

Deux API publiques, sans compte ni clé :
- Gamma : la liste des marchés (question, dates, volume, résultat) ;
- CLOB  : l'historique des prix du jeton « Yes » de chaque marché.

Le script écrit deux fichiers dans data/raw/ :
- markets.csv   : un marché binaire résolu par ligne ;
- snapshots.csv : le prix du « Yes » à J-7, J-3 et J-1 avant la clôture.
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import requests

from . import config as C
from .categorize import categorize

log = logging.getLogger(__name__)
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "polymarket-backtest (projet portfolio data)"


def _get(url: str, params: dict, tries: int = 8) -> object:
    """GET avec reprises : les API publiques renvoient parfois des 429/5xx passagers."""
    for i in range(tries):
        try:
            r = SESSION.get(url, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504):
                log.warning("HTTP %s, nouvel essai dans %ss", r.status_code, min(2 ** i, 60))
                time.sleep(min(2 ** i, 60))
                continue
            r.raise_for_status()
        except requests.RequestException as e:
            if i == tries - 1:
                raise
            log.warning("Erreur réseau (%s), nouvel essai", e)
            time.sleep(min(2 ** i, 60))
    raise RuntimeError(f"Échec après {tries} essais : {url} {params}")


def _as_list(v) -> list:
    """Gamma renvoie certaines listes sous forme de texte JSON (ex. '["Yes","No"]')."""
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.strip().startswith("["):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return []
    return []


def fetch_markets(max_pages: int = 3000, page_size: int = 100, max_offset: int = 1900) -> list[dict]:
    """Récupère les marchés clos de la période, triés par date de fin.

    L'API plafonne à 100 marchés par page et refuse un décalage (offset) au-delà de
    ~2 000. On avance donc par fenêtres : une fois le décalage maximal atteint, la
    fenêtre repart de la dernière date de fin reçue. Les doublons sont écartés par id.
    """
    seen: dict[str, dict] = {}
    start, offset = C.END_MIN, 0
    for page in range(max_pages):
        params = {
            "closed": "true", "limit": page_size, "offset": offset,
            "end_date_min": start, "end_date_max": C.END_MAX,
            "volume_num_min": C.MIN_VOLUME, "order": "endDate", "ascending": "true",
        }
        batch = _get(C.GAMMA_URL, params)
        time.sleep(0.1)  # rester poli avec l'API publique
        if isinstance(batch, dict):  # certaines versions de l'API enveloppent la liste
            batch = batch.get("data") or batch.get("markets") or []
        for m in batch:
            seen[str(m.get("id"))] = m
        if page % 50 == 0:
            log.info("Page %d (depuis %s, décalage %d) : %d marchés uniques", page, start, offset, len(seen))
        if len(batch) < page_size:
            break
        if offset + page_size <= max_offset:
            offset += page_size
            continue
        last = max(m.get("endDate") or "" for m in batch)
        if not last or last <= start:  # plus de 2 000 marchés à la même date : on avance d'une seconde
            last = (pd.Timestamp(start) + pd.Timedelta(seconds=1)).isoformat()
        start, offset = last, 0
    return list(seen.values())


def parse_market(m: dict) -> dict | None:
    """Garde un marché seulement s'il a deux issues et qu'il est clairement résolu.

    La plupart des marchés sont en Oui/Non ; les matchs (« A vs. B ») ont le nom des
    équipes. Dans les deux cas, la première issue joue le rôle du « Oui ».
    """
    outcomes = [str(o).strip() for o in _as_list(m.get("outcomes"))]
    prices = [float(p) for p in _as_list(m.get("outcomePrices")) if p not in (None, "")]
    tokens = _as_list(m.get("clobTokenIds"))
    if len(outcomes) != 2 or len(prices) != 2 or len(tokens) != 2:
        return None
    if max(prices) < 0.99:  # résultat non tranché (annulé, 50/50…)
        return None

    end = pd.to_datetime(m.get("endDate"), utc=True, errors="coerce")
    closed = pd.to_datetime(m.get("closedTime"), utc=True, errors="coerce")
    # Date de référence = la plus tôt des deux : un marché peut se clore en avance
    # (événement survenu), ou rester ouvert après la date prévue le temps de la résolution.
    ref = min([d for d in (end, closed) if pd.notna(d)], default=pd.NaT)
    if pd.isna(ref):
        return None

    try:
        volume = float(m.get("volumeNum") or m.get("volume") or 0)
    except (TypeError, ValueError):
        volume = 0.0
    if volume < C.MIN_VOLUME:
        return None

    events = m.get("events") or []
    event_title = events[0].get("title", "") if events and isinstance(events[0], dict) else ""
    question = m.get("question") or ""
    return {
        "market_id": str(m.get("id")),
        "question": question,
        "evenement": event_title,
        "slug": m.get("slug") or "",
        "categorie": categorize(f"{question} {event_title}"),
        "date_cloture": ref,
        "volume": round(volume, 2),
        "issue_1": outcomes[0],
        "issue_2": outcomes[1],
        "resultat_yes": int(prices[0] > 0.5),
        "token_yes": str(tokens[0]),
    }


def select_for_pricing(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    """Échantillon réparti par mois, pour ne pas sur-représenter les mois très actifs."""
    df = df.copy()
    df["mois"] = df["date_cloture"].dt.strftime("%Y-%m")
    per_month = max(1, n // df["mois"].nunique())
    parts = [g.sample(min(len(g), per_month), random_state=seed) for _, g in df.groupby("mois")]
    return pd.concat(parts).drop(columns="mois")


def price_snapshots(token: str, close: pd.Timestamp) -> dict[str, float]:
    """Prix du « Yes » à J-7, J-3 et J-1 avant la clôture (NaN si aucun échange récent)."""
    close_ts = int(close.timestamp())
    start = close_ts - (max(C.SNAPSHOT_HOURS) + C.SNAPSHOT_TOLERANCE_H) * 3600
    data = _get(C.CLOB_HISTORY_URL, {"market": token, "startTs": start, "endTs": close_ts, "fidelity": 60})
    hist = data.get("history", []) if isinstance(data, dict) else []
    pts = sorted((int(h["t"]), float(h["p"])) for h in hist if "t" in h and "p" in h)
    snap = {}
    for h in C.SNAPSHOT_HOURS:
        target = close_ts - h * 3600
        cands = [p for t, p in pts if target - C.SNAPSHOT_TOLERANCE_H * 3600 <= t <= target]
        snap[f"prix_j{h // 24}"] = cands[-1] if cands else np.nan
    return snap


def run() -> None:
    C.RAW.mkdir(parents=True, exist_ok=True)
    raw = fetch_markets()
    if raw:
        (C.RAW / "sample_market.json").write_text(json.dumps(raw[0], indent=2, ensure_ascii=False))
    parsed = [p for m in raw if (p := parse_market(m))]
    markets = pd.DataFrame(parsed).drop_duplicates("market_id")
    markets = markets[(markets["date_cloture"] >= C.END_MIN) & (markets["date_cloture"] < C.END_MAX)]
    log.info("%d marchés reçus, %d binaires résolus et dans le périmètre", len(raw), len(markets))

    sample = select_for_pricing(markets, C.MAX_MARKETS_PRICED, C.SEED)
    rows, errors = [], 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(price_snapshots, r.token_yes, r.date_cloture): r.market_id
                for r in sample.itertuples()}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                rows.append({"market_id": futs[f], **f.result()})
            except Exception as e:  # un marché en échec ne doit pas bloquer les autres
                errors += 1
                log.warning("Historique indisponible pour %s : %s", futs[f], e)
            if i % 500 == 0:
                log.info("Historiques : %d/%d", i, len(futs))
    snaps = pd.DataFrame(rows)

    # Seul l'échantillon est sauvegardé (le repo reste léger) ; les totaux vont dans les stats.
    sample.drop(columns="token_yes").to_csv(C.RAW / "markets.csv", index=False)
    snaps.to_csv(C.RAW / "snapshots.csv", index=False)
    stats = {
        "marches_recus": len(raw),
        "marches_binaires_resolus": len(markets),
        "marches_echantillon": len(sample),
        "marches_par_categorie": markets["categorie"].value_counts().to_dict(),
        "historiques_en_echec": errors,
        "historiques_avec_prix_j3": int(snaps["prix_j3"].notna().sum()) if len(snaps) else 0,
        "date_extraction": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d"),
    }
    (C.RAW / "collect_stats.json").write_text(json.dumps(stats, indent=2))
    log.info("Collecte terminée : %s", stats)
