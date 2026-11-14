"""Calendrier fiscal de Target.

L'exercice se termine le samedi le plus proche du 31 janvier. « FY2022 » couvre donc
environ février 2022 à janvier 2023 : l'année fiscale est l'année civile de son début.
Les trimestres se terminent vers début mai (T1), début août (T2), début novembre (T3)
et fin janvier ou début février (T4). Certains exercices comptent 53 semaines (FY2017, FY2023).
"""

from __future__ import annotations

from datetime import date

QUARTER_BY_END_MONTH = {4: 1, 5: 1, 7: 2, 8: 2, 10: 3, 11: 3, 1: 4, 2: 4}

# Bornes de durée (jours) pour classer une période XBRL : 13 semaines = 91 jours,
# 14 semaines = 98 jours, 52 semaines = 364 jours, 53 semaines = 371 jours.
DURATION_CLASSES = {
    "Q": (84, 100),
    "6M": (175, 190),
    "9M": (266, 282),
    "FY": (357, 378),
}


def fiscal_period(end: date) -> tuple[int, int]:
    """(année fiscale, trimestre fiscal) de la période qui se termine à `end`."""
    quarter = QUARTER_BY_END_MONTH.get(end.month)
    if quarter is None:
        raise ValueError(f"Fin de période inattendue pour Target : {end}")
    year = end.year - 1 if quarter == 4 else end.year
    return year, quarter


def duration_class(start: date, end: date) -> str | None:
    """Classe une durée en Q, 6M, 9M ou FY ; None si elle ne correspond à aucune."""
    days = (end - start).days
    for label, (low, high) in DURATION_CLASSES.items():
        if low <= days <= high:
            return label
    return None


def ytd_quarters(label: str) -> int:
    """Nombre de trimestres couverts par une durée cumulée depuis le début de l'exercice."""
    return {"Q": 1, "6M": 2, "9M": 3, "FY": 4}[label]
