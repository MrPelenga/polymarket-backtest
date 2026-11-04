"""Point d'entrée : python run_pipeline.py [collect|backtest|all]"""

import logging
import sys

from pmbt import backtest, collect

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    if step in ("collect", "all"):
        collect.run()
    if step in ("backtest", "all"):
        backtest.run()
