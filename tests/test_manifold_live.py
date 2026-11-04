"""Appelle la vraie API Manifold et vérifie que les champs utilisés existent toujours.

L'API est en « alpha » et peut changer sans prévenir : ce test le détecte avant que le
passage quotidien n'écrase des données saines. Il ne tourne que si MANIFOLD_LIVE=1
(c'est le cas dans le workflow GitHub Actions « Manifold »).

En local : MANIFOLD_LIVE=1 python -m pytest tests/test_manifold_live.py -q
"""

import os

import pytest

from pmbt import manifold

pytestmark = pytest.mark.skipif(os.environ.get("MANIFOLD_LIVE") != "1", reason="appel réseau : MANIFOLD_LIVE=1")

MARKET_FIELDS = {"id", "question", "outcomeType", "isResolved", "resolution", "createdTime",
                 "closeTime", "resolutionTime", "uniqueBettorCount", "volume"}
BET_FIELDS = {"probAfter", "createdTime", "contractId"}


def test_search_markets_fields():
    page = manifold._get(manifold.new_session(), "/search-markets",
                         {"filter": "resolved", "contractType": "BINARY", "sort": "newest", "limit": 5})
    assert page, "aucun marché résolu renvoyé"
    assert MARKET_FIELDS <= set(page[0]), f"champs manquants : {MARKET_FIELDS - set(page[0])}"


def test_bets_fields_and_time_filter():
    session = manifold.new_session()
    market = manifold._get(session, "/search-markets",
                           {"filter": "resolved", "contractType": "BINARY", "sort": "newest", "limit": 1})[0]
    cutoff = market["closeTime"]
    bets = manifold._get(session, "/bets", {"contractId": market["id"], "beforeTime": cutoff,
                                            "limit": 5, "order": "desc"})
    assert bets, "aucun pari renvoyé"
    assert BET_FIELDS <= set(bets[0]), f"champs manquants : {BET_FIELDS - set(bets[0])}"
    assert all(b["createdTime"] < cutoff for b in bets), "le filtre beforeTime n'est plus respecté"
