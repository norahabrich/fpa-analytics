"""Mise à plat des faits XBRL et choix de la dernière version publiée.

Une même valeur (concept, période) apparaît dans plusieurs dépôts : le 10-Q d'origine,
puis le 10-Q de l'année suivante en comparatif, puis parfois un 10-K retraité. On garde
la **dernière version déposée** et on signale les périodes dont la valeur a changé
(retraitements), pour pouvoir les expliquer.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from fpa.silver.calendar import duration_class, fiscal_period

PERIODIC_FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A"}

COLUMNS = ["concept", "unit", "start", "end", "val", "accn", "form", "filed", "fp", "frame"]


def flatten(facts: dict, concepts: set[str], taxonomy: str = "us-gaap") -> pd.DataFrame:
    """Une ligne par observation des concepts demandés, issue d'un 10-K ou d'un 10-Q."""
    rows = []
    for concept in concepts:
        body = facts.get("facts", {}).get(taxonomy, {}).get(concept)
        if not body:
            continue
        for unit, observations in body.get("units", {}).items():
            for o in observations:
                if o.get("form") not in PERIODIC_FORMS:
                    continue
                rows.append(
                    {
                        "concept": concept,
                        "unit": unit,
                        "start": o.get("start"),
                        "end": o["end"],
                        "val": float(o["val"]),
                        "accn": o.get("accn"),
                        "form": o.get("form"),
                        "filed": o.get("filed"),
                        "fp": o.get("fp"),
                        "frame": o.get("frame"),
                    }
                )
    df = pd.DataFrame(rows, columns=COLUMNS)
    for col in ("start", "end", "filed"):
        df[col] = pd.to_datetime(df[col]).dt.date
    return df


def latest_versions(obs: pd.DataFrame) -> pd.DataFrame:
    """Garde la dernière valeur déposée par (concept, unité, début, fin).

    Ajoute `n_filings` (nombre de dépôts qui publient cette période) et
    `first_val` / `restated` (la première valeur publiée diffère de la dernière).
    """
    key = ["concept", "unit", "start", "end"]
    obs = obs.copy()
    obs["_start"] = obs["start"].astype("object").where(obs["start"].notna(), date.min)
    k = ["concept", "unit", "_start", "end"]
    obs = obs.sort_values([*k, "filed", "accn"], kind="stable")
    grouped = obs.groupby(k, sort=False, dropna=False)
    latest = grouped.tail(1).set_index(k)
    first = grouped.head(1).set_index(k)["val"].rename("first_val")
    count = grouped.size().rename("n_filings")
    out = latest.join(first).join(count).reset_index().drop(columns="_start")
    out["restated"] = (out["val"] - out["first_val"]).abs() > 0.5
    return out[[*key, "val", "first_val", "restated", "n_filings", "accn", "form", "filed", "fp", "frame"]]


def add_periods(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute l'année et le trimestre fiscaux, et la classe de durée (Q, 6M, 9M, FY, instant)."""
    df = df.copy()
    fy_q = df["end"].map(fiscal_period)
    df["fiscal_year"] = [y for y, _ in fy_q]
    df["fiscal_quarter"] = [q for _, q in fy_q]
    df["duration"] = [
        "instant" if pd.isna(s) else duration_class(s, e) for s, e in zip(df["start"], df["end"], strict=True)
    ]
    return df
