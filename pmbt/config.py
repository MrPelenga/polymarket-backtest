"""Paramètres du projet. Chaque règle de l'article est une constante nommée,
pour pouvoir la retrouver et la modifier sans fouiller le code."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
OUT = DATA / "powerbi"

GAMMA_URL = "https://gamma-api.polymarket.com/markets"
CLOB_HISTORY_URL = "https://clob.polymarket.com/prices-history"

# --- Périmètre des données ---------------------------------------------------
END_MIN = "2025-01-01"          # marchés clos à partir de cette date
END_MAX = "2026-10-31"          # ... et jusqu'à celle-ci
TRAIN_END = "2026-01-01"        # avant : apprentissage ; après : test (backtest)
MIN_VOLUME = 5_000              # l'article écarte les marchés sous 5 000 $
MAX_MARKETS_PRICED = 6_000      # nombre de marchés dont on télécharge l'historique

# --- Moment de la décision ----------------------------------------------------
DECISION_HOURS = 72             # on décide 72 h avant la clôture du marché
SNAPSHOT_HOURS = (168, 72, 24)  # prix relevés à J-7, J-3 et J-1
SNAPSHOT_TOLERANCE_H = 12       # un prix plus vieux que ça avant l'horaire visé est ignoré

# --- Règles de l'article -----------------------------------------------------
BANKROLL = 50.0                 # cagnotte de départ
MIN_EDGE = 0.08                 # écart minimal de 8 points entre estimation et prix
KELLY_FRACTION = 0.5            # Kelly divisé par deux
MAX_STAKE_PCT = 0.06            # jamais plus de 6 % de la cagnotte sur un pari
MAX_OPEN = 5                    # cinq paris ouverts au maximum
STOP_DRAWDOWN = 0.40            # arrêt complet à -40 % depuis le plus haut

# --- Hypothèses de marché (non précisées dans l'article) ----------------------
SLIPPAGE = 0.01                 # on paie 1 point au-dessus du dernier prix (écart achat/vente)
MIN_STAKE = 1.0                 # mise minimale supposée : 1 $
MAX_ENTRY_PRICE = 0.97          # au-delà, le gain potentiel ne couvre pas le coût d'entrée

RANDOM_RUNS = 300               # nombre de tirages pour la stratégie aléatoire
SEED = 42
