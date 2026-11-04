"""Classement des marchés par thème à partir du texte de la question.

Règles volontairement simples et lisibles : la première catégorie dont un mot-clé
apparaît l'emporte. L'ordre compte (ex. « Bitcoin ETF approved » doit tomber en Crypto).
"""

import re

RULES: list[tuple[str, list[str]]] = [
    ("Météo", [
        r"temperature", r"°[cf]", r"\bweather\b", r"\brain(fall)?\b", r"\bsnow", r"hurricane",
        r"tropical storm", r"\bheat\b", r"degrees", r"climate", r"tornado", r"earthquake",
        r"highest temp", r"lowest temp",
    ]),
    ("Crypto", [
        r"bitcoin", r"\bbtc\b", r"ethereum", r"\beth\b", r"solana", r"\bsol\b", r"\bxrp\b",
        r"dogecoin", r"\bdoge\b", r"crypto", r"\btoken\b", r"memecoin", r"binance", r"coinbase",
        r"stablecoin", r"\bfdv\b", r"airdrop", r"\busdt\b", r"\busdc\b", r"\bbnb\b", r"cardano",
    ]),
    ("Économie", [
        r"\bfed\b", r"interest rate", r"\brates?\b.*(cut|hike)", r"inflation", r"\bcpi\b", r"\bgdp\b",
        r"recession", r"unemployment", r"jobs report", r"s&p", r"nasdaq", r"dow jones", r"stock",
        r"\bipo\b", r"earnings", r"tariff", r"\becb\b", r"oil price", r"gold price", r"\bshares?\b",
    ]),
    ("Politique", [
        r"election", r"president", r"trump", r"biden", r"harris", r"senate", r"congress",
        r"governor", r"mayor", r"parliament", r"prime minister", r"\bvote\b", r"\bpoll", r"minister",
        r"democrat", r"republican", r"impeach", r"supreme court", r"\bnato\b", r"ukraine", r"russia",
        r"israel", r"gaza", r"iran", r"china", r"ceasefire", r"executive order", r"white house",
        r"macron", r"putin", r"zelensky", r"netanyahu", r"pope",
    ]),
    ("Sport", [
        r"\bvs\.?\b", r"\bnba\b", r"\bnfl\b", r"\bnhl\b", r"\bmlb\b", r"\bufc\b", r"premier league",
        r"champions league", r"la liga", r"serie a", r"bundesliga", r"ligue 1", r"world cup",
        r"super bowl", r"stanley cup", r"grand slam", r"wimbledon", r"roland", r"open\b.*(win|champion)",
        r"\bf1\b", r"formula 1", r"grand prix", r"tennis", r"golf", r"masters", r"\bwin the\b.*(cup|title|championship|series)",
        r"\bfc\b", r"o/u", r"over/under", r"spread", r"\bmvp\b", r"playoffs?", r"\bmatch\b", r"\bgame \d",
        r"cricket", r"boxing", r"esports", r"\blol\b", r"counter-strike", r"\bcs2\b", r"dota",
    ]),
    ("Tech & IA", [
        r"\bai\b", r"openai", r"chatgpt", r"\bgpt", r"gemini", r"claude", r"anthropic", r"grok",
        r"\bxai\b", r"apple", r"google", r"microsoft", r"nvidia", r"tesla", r"spacex", r"starship",
        r"elon musk", r"\bmusk\b", r"tweet", r"meta\b", r"tiktok", r"app store",
    ]),
    ("Culture", [
        r"oscar", r"grammy", r"emmy", r"golden globe", r"box office", r"movie", r"film", r"album",
        r"song", r"spotify", r"billboard", r"netflix", r"eurovision", r"taylor swift", r"youtube",
        r"mrbeast", r"time person of the year", r"nobel",
    ]),
]

_COMPILED = [(cat, re.compile("|".join(pats), re.IGNORECASE)) for cat, pats in RULES]


def categorize(text: str) -> str:
    """Renvoie la catégorie d'un marché à partir de sa question (et du titre de l'événement)."""
    if not text:
        return "Autre"
    for cat, rx in _COMPILED:
        if rx.search(text):
            return cat
    return "Autre"
