"""Reconstruit toute la chaîne à partir des archives Bronze, sans appel à la SEC.

    Bronze -> Silver -> Gold -> contrôles -> ventes comparables -> analyse -> prévision (-> graphiques)

Usage :
    python -m fpa.pipeline            # tables Silver et Gold, rapport de contrôles
    python -m fpa.pipeline --charts   # idem + graphiques de docs/img/
"""

from __future__ import annotations

import argparse
import importlib
import sys
import time

STEPS = [
    "fpa.silver.build",
    "fpa.gold.build",
    "fpa.gold.controls",
    "fpa.analysis.comparable_sales",
    "fpa.analysis.build",
    "fpa.forecast.build",
]
CHART_STEPS = ["fpa.analysis.charts", "fpa.forecast.charts"]


def run(charts: bool = False) -> None:
    for name in STEPS + (CHART_STEPS if charts else []):
        start = time.perf_counter()
        print(f"\n=== {name}")
        sys.argv = [name]  # chaque étape lit ses propres options : on lui passe une ligne de commande vide
        importlib.import_module(name).main()
        print(f"--- {name} : {time.perf_counter() - start:.1f} s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--charts", action="store_true", help="régénère aussi les graphiques")
    run(parser.parse_args().charts)


if __name__ == "__main__":
    main()
