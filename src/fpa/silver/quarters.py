"""Reconstruction d'une série trimestrielle par compte.

Règles, dans l'ordre de préférence, pour un compte de flux (P&L, flux de trésorerie) :

1. `reported` : valeur publiée pour le trimestre seul (durée de 13 ou 14 semaines) ;
2. `derived_ytd` : cumul depuis le début de l'exercice moins le cumul précédent
   (par exemple T3 = 9 mois − 6 mois). Les tableaux de flux des 10-Q ne sont publiés
   qu'en cumul, d'où cette règle ;
3. `derived_fy` : T4 = exercice − 9 mois, car le T4 n'a pas de 10-Q.

Un cumul n'est soustrait que d'un autre cumul **qui démarre le même jour** (même exercice).

Pour un compte de stock (bilan), on prend la valeur à la date de clôture du trimestre.
Pour un BPA ou un nombre moyen d'actions, rien n'est additif : on ne garde que les valeurs
publiées pour le trimestre ou l'exercice.

Quand plusieurs concepts XBRL peuvent porter un compte (changement de libellé), on prend,
pour chaque période, le premier concept de la liste qui a une valeur.
"""

from __future__ import annotations

import pandas as pd

from fpa.silver.calendar import ytd_quarters

OUT_COLUMNS = [
    "account",
    "fiscal_year",
    "fiscal_quarter",
    "period_start",
    "period_end",
    "value",
    "method",
    "concept",
    "accn",
    "filed",
    "restated",
]


def _pick_concept(rows: pd.DataFrame, concepts: list[str]) -> pd.DataFrame:
    """Pour chaque (début, fin), garde la ligne du concept prioritaire."""
    rank = {c: i for i, c in enumerate(concepts)}
    rows = rows.assign(_rank=rows["concept"].map(rank)).sort_values("_rank", kind="stable")
    return rows.drop_duplicates(["start", "end"], keep="first").drop(columns="_rank")


def _record(account, fy, q, start, end, value, method, src):
    return {
        "account": account,
        "fiscal_year": fy,
        "fiscal_quarter": q,
        "period_start": start,
        "period_end": end,
        "value": value,
        "method": method,
        "concept": src["concept"],
        "accn": src["accn"],
        "filed": src["filed"],
        "restated": bool(src["restated"]),
    }


def quarterly_flow(facts: pd.DataFrame, account: str, concepts: list[str]) -> pd.DataFrame:
    rows = facts[facts["concept"].isin(concepts) & facts["duration"].isin(["Q", "6M", "9M", "FY"])]
    rows = _pick_concept(rows, concepts)
    # Cumuls depuis le début de l'exercice : clé = (date de début, nombre de trimestres)
    ytd = {
        (r.start, ytd_quarters(r.duration)): r for r in rows.itertuples() if r.duration != "Q" or r.fiscal_quarter == 1
    }
    direct = {(r.fiscal_year, r.fiscal_quarter): r for r in rows[rows["duration"] == "Q"].itertuples()}

    out = []
    for (start, n), cur in ytd.items():
        fy = cur.fiscal_year
        q = n
        if (fy, q) in direct:
            d = direct[(fy, q)]
            out.append(_record(account, fy, q, d.start, d.end, d.val, "reported", d._asdict()))
            continue
        prev = ytd.get((start, n - 1)) if n > 1 else None
        if prev is None:
            continue
        method = "derived_fy" if n == 4 else "derived_ytd"
        out.append(_record(account, fy, q, prev.end, cur.end, cur.val - prev.val, method, cur._asdict()))
    # Trimestres publiés seuls sans cumul correspondant (rare)
    seen = {(r["fiscal_year"], r["fiscal_quarter"]) for r in out}
    for (fy, q), d in direct.items():
        if (fy, q) not in seen:
            out.append(_record(account, fy, q, d.start, d.end, d.val, "reported", d._asdict()))
    return pd.DataFrame(out, columns=OUT_COLUMNS)


def quarterly_stock(facts: pd.DataFrame, account: str, concepts: list[str]) -> pd.DataFrame:
    rows = facts[facts["concept"].isin(concepts) & (facts["duration"] == "instant")]
    rows = _pick_concept(rows, concepts)
    out = [
        _record(account, r.fiscal_year, r.fiscal_quarter, None, r.end, r.val, "reported", r._asdict())
        for r in rows.itertuples()
    ]
    df = pd.DataFrame(out, columns=OUT_COLUMNS)
    # Une seule valeur par trimestre fiscal (la date de clôture la plus tardive)
    return df.sort_values("period_end").drop_duplicates(["fiscal_year", "fiscal_quarter"], keep="last")


def reported_only(facts: pd.DataFrame, account: str, concepts: list[str], durations: tuple[str, ...]) -> pd.DataFrame:
    rows = facts[facts["concept"].isin(concepts) & facts["duration"].isin(durations)]
    rows = _pick_concept(rows, concepts)
    out = [
        _record(account, r.fiscal_year, r.fiscal_quarter, r.start, r.end, r.val, "reported", r._asdict())
        for r in rows.itertuples()
    ]
    return pd.DataFrame(out, columns=OUT_COLUMNS)


def annual_flow(facts: pd.DataFrame, account: str, concepts: list[str]) -> pd.DataFrame:
    """Valeurs d'exercice complet publiées (durée FY)."""
    df = reported_only(facts, account, concepts, ("FY",))
    return df.assign(fiscal_quarter=pd.NA)
