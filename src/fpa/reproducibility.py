"""Vérifie que les tables versionnées correspondent exactement au code.

À lancer après `python -m fpa.pipeline` : chaque CSV de data/silver, data/gold et
data/reference est comparé à sa version du dernier commit (`git show HEAD:...`).
Une différence signifie que le code a changé sans que les données aient été regénérées.
Les nombres sont comparés avec une tolérance relative de 1e-6 (arrondis de calcul entre machines).

Usage :
    python -m fpa.pipeline && python -m fpa.reproducibility
"""

from __future__ import annotations

import io
import subprocess
import sys

import pandas as pd

from fpa.config import DATA_DIR, PROJECT_ROOT

FOLDERS = ("silver", "gold", "reference")


def committed(path) -> pd.DataFrame | None:
    rel = path.relative_to(PROJECT_ROOT).as_posix()
    res = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=PROJECT_ROOT, capture_output=True)
    return pd.read_csv(io.BytesIO(res.stdout)) if res.returncode == 0 else None


def compare() -> list[str]:
    problems = []
    for folder in FOLDERS:
        for path in sorted((DATA_DIR / folder).glob("*.csv")):
            old = committed(path)
            if old is None:
                problems.append(f"{path.name} : fichier absent du dernier commit")
                continue
            new = pd.read_csv(path)
            try:
                pd.testing.assert_frame_equal(new, old, check_exact=False, rtol=1e-6, check_dtype=False)
            except AssertionError as err:
                problems.append(f"{folder}/{path.name} : {str(err).splitlines()[0]}")
    return problems


def main() -> None:
    problems = compare()
    if problems:
        print("Tables différentes du dernier commit (relancer `python -m fpa.pipeline` et committer) :")
        print("\n".join(f"  - {p}" for p in problems))
        sys.exit(1)
    print("Données reproductibles : toutes les tables correspondent au code.")


if __name__ == "__main__":
    main()
