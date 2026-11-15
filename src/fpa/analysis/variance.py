"""Analyse des écarts : pont de résultat opérationnel et réel contre guidance.

Pont de résultat opérationnel (EBIT) entre une période de référence 0 et une période 1.
Avec R le CA et g, s, d les taux de marge brute, de SG&A et d'amortissements (en % du CA) :

    EBIT = R × (g − s − d)
    ΔEBIT = ΔR × m0               effet volume (CA supplémentaire à la marge de l'an dernier)
          + R1 × (g1 − g0)        effet taux de marge brute
          − R1 × (s1 − s0)        effet taux de SG&A
          − R1 × (d1 − d0)        effet taux d'amortissements

La somme des quatre effets est exactement égale à ΔEBIT (pas de résidu).

L'effet volume se décompose à son tour avec les ventes comparables publiées :
    trafic ≈ R0 × t,   panier moyen ≈ R0 × (1 + t) × a,   autres = ΔR − trafic − panier
« autres » regroupe les nouveaux magasins, les revenus hors marchandises et la 53e semaine.
C'est une approximation : les ventes comparables ne portent que sur les ventes de marchandises.
"""

from __future__ import annotations

import pandas as pd

BRIDGE_STEPS = [
    ("start", "Résultat opérationnel N-1"),
    ("volume_traffic", "Volume : trafic"),
    ("volume_ticket", "Volume : panier moyen"),
    ("volume_other", "Volume : magasins, autres revenus, calendrier"),
    ("gross_margin_rate", "Taux de marge brute"),
    ("sga_rate", "Taux de SG&A"),
    ("da_rate", "Taux d'amortissements"),
    ("end", "Résultat opérationnel N"),
]


def operating_income_bridge(p0: pd.Series, p1: pd.Series, traffic_pct=None, ticket_pct=None) -> pd.DataFrame:
    """Pont EBIT entre deux périodes. p0 et p1 contiennent revenue, cogs, sga, da_opex, operating_income."""
    r0, r1 = p0["revenue"], p1["revenue"]
    g0, g1 = 1 - p0["cogs"] / r0, 1 - p1["cogs"] / r1
    s0, s1 = p0["sga"] / r0, p1["sga"] / r1
    d0, d1 = p0["da_opex"] / r0, p1["da_opex"] / r1
    m0 = p0["operating_income"] / r0

    delta_r = r1 - r0
    if traffic_pct is not None and ticket_pct is not None and pd.notna(traffic_pct) and pd.notna(ticket_pct):
        t, a = traffic_pct / 100, ticket_pct / 100
        rev_traffic = r0 * t
        rev_ticket = r0 * (1 + t) * a
    else:
        rev_traffic = rev_ticket = 0.0
    rev_other = delta_r - rev_traffic - rev_ticket

    values = {
        "start": p0["operating_income"],
        "volume_traffic": rev_traffic * m0,
        "volume_ticket": rev_ticket * m0,
        "volume_other": rev_other * m0,
        "gross_margin_rate": r1 * (g1 - g0),
        "sga_rate": -r1 * (s1 - s0),
        "da_rate": -r1 * (d1 - d0),
        "end": p1["operating_income"],
    }
    revenue_effect = {"volume_traffic": rev_traffic, "volume_ticket": rev_ticket, "volume_other": rev_other}
    rate_change = {"gross_margin_rate": g1 - g0, "sga_rate": s1 - s0, "da_rate": d1 - d0}
    rows = []
    for order, (step, label) in enumerate(BRIDGE_STEPS):
        rows.append(
            {
                "step_order": order,
                "step": step,
                "label_fr": label,
                "value": values[step],
                "is_total": step in ("start", "end"),
                "revenue_effect": revenue_effect.get(step),
                "rate_change_pts": rate_change[step] * 100 if step in rate_change else None,
            }
        )
    return pd.DataFrame(rows)


def bridges(kpi_q: pd.DataFrame, kpi_a: pd.DataFrame, comps: pd.DataFrame) -> pd.DataFrame:
    """Ponts annuels (exercice vs N-1) et trimestriels (trimestre vs même trimestre N-1)."""
    out = []
    annual = kpi_a.set_index("fiscal_year")
    comps_fy = comps[comps["fiscal_quarter"] == 4].set_index("fiscal_year")
    for fy in annual.index:
        if fy - 1 not in annual.index:
            continue
        c = comps_fy.loc[fy] if fy in comps_fy.index else {}
        b = operating_income_bridge(
            annual.loc[fy - 1], annual.loc[fy], c.get("traffic_ytd_pct"), c.get("average_ticket_ytd_pct")
        )
        out.append(b.assign(grain="annual", period_key=f"FY{fy}", reference_key=f"FY{fy - 1}"))

    quarterly = kpi_q.set_index(["fiscal_year", "fiscal_quarter"])
    comps_q = comps.set_index(["fiscal_year", "fiscal_quarter"])
    for fy, fq in quarterly.index:
        if (fy - 1, fq) not in quarterly.index:
            continue
        c = comps_q.loc[(fy, fq)] if (fy, fq) in comps_q.index else {}
        b = operating_income_bridge(
            quarterly.loc[(fy - 1, fq)], quarterly.loc[(fy, fq)], c.get("traffic_pct"), c.get("average_ticket_pct")
        )
        out.append(b.assign(grain="quarterly", period_key=f"FY{fy}-Q{fq}", reference_key=f"FY{fy - 1}-Q{fq}"))
    cols = [
        "grain",
        "period_key",
        "reference_key",
        "step_order",
        "step",
        "label_fr",
        "value",
        "is_total",
        "revenue_effect",
        "rate_change_pts",
    ]
    return pd.concat(out, ignore_index=True)[cols]


def actual_for(metric: str, period: str, fy: int, kpi_q: pd.DataFrame, kpi_a: pd.DataFrame, comps: pd.DataFrame):
    """Valeur réelle comparable à une ligne de guidance, avec sa base de calcul."""
    q = kpi_q[kpi_q["fiscal_year"] == fy].set_index("fiscal_quarter")
    q_prev = kpi_q[kpi_q["fiscal_year"] == fy - 1].set_index("fiscal_quarter")
    quarters = {"FY": [1, 2, 3, 4], "H2": [3, 4]}.get(period, [int(period[1])] if period.startswith("Q") else [])
    if not quarters or not set(quarters) <= set(q.index):
        return None, "période non close"

    if metric == "operating_margin_rate":
        return q.loc[quarters, "operating_income"].sum() / q.loc[quarters, "revenue"].sum() * 100, "EBIT / CA"
    if metric in ("revenue_growth", "net_sales_growth"):
        if not set(quarters) <= set(q_prev.index):
            return None, "N-1 manquant"
        growth = q.loc[quarters, "revenue"].sum() / q_prev.loc[quarters, "revenue"].sum() - 1
        return growth * 100, "CA total vs N-1 (inclut une éventuelle 53e semaine)"
    if metric == "comparable_sales_growth":
        c = comps[comps["fiscal_year"] == fy].set_index("fiscal_quarter")
        if period == "FY":
            return (c.loc[4, "comparable_sales_ytd_pct"], "publié") if 4 in c.index else (None, "non publié")
        if not set(quarters) <= set(c.index):
            return None, "non publié"
        w = q.loc[quarters, "revenue"]
        value = (c.loc[quarters, "comparable_sales_pct"] * w).sum() / w.sum()
        return value, "publié" if len(quarters) == 1 else "moyenne des trimestres pondérée par le CA"
    if metric == "eps_adjusted":
        if period == "FY":
            a = kpi_a.set_index("fiscal_year")
            return (a.loc[fy, "eps_diluted"], "BPA GAAP dilué") if fy in a.index else (None, "non publié")
        value = q.loc[quarters[0], "eps_diluted"] if len(quarters) == 1 else None
        return (value, "BPA GAAP dilué") if pd.notna(value) else (None, "BPA trimestriel non balisé")
    if metric == "operating_income_change":
        a = kpi_a.set_index("fiscal_year")
        if fy in a.index and fy - 1 in a.index:
            return a.loc[fy, "operating_income"] - a.loc[fy - 1, "operating_income"], "EBIT N − EBIT N-1 (MUSD)"
    return None, "non calculé"


def guidance_vs_actual(guidance: pd.DataFrame, kpi_q, kpi_a, comps) -> pd.DataFrame:
    rows = []
    for g in guidance.itertuples():
        actual, basis = actual_for(g.metric, g.period, int(g.fiscal_year[2:]), kpi_q, kpi_a, comps)
        low, high, point = g.low, g.high, g.point
        mid = (
            point
            if pd.notna(point)
            else (low + high) / 2
            if pd.notna(low) and pd.notna(high)
            else (low if pd.notna(low) else high)
        )
        if actual is None or pd.isna(actual):
            verdict = "n.d."
        elif pd.notna(low) and actual < low:
            verdict = "sous l'objectif"
        elif pd.notna(high) and actual > high:
            verdict = "au-dessus de l'objectif"
        elif pd.notna(point) and pd.isna(low) and pd.isna(high):
            verdict = (
                "proche du point visé"
                if abs(actual - point) <= max(abs(point) * 0.1, 0.5)
                else ("sous l'objectif" if actual < point else "au-dessus de l'objectif")
            )
        else:
            verdict = "dans la fourchette"
        rows.append(
            {
                "issued_date": g.issued_date,
                "fiscal_year": g.fiscal_year,
                "period": g.period,
                "metric": g.metric,
                "unit": g.unit,
                "guidance_low": low,
                "guidance_high": high,
                "guidance_mid": mid,
                "actual": actual,
                "variance_vs_mid": None if actual is None or pd.isna(actual) else actual - mid,
                "verdict": verdict,
                "actual_basis": basis,
                "note": g.note,
                "source_url": g.source_url,
            }
        )
    return pd.DataFrame(rows)
