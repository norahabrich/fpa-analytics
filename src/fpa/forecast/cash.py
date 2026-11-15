"""Projection de trésorerie de fin d'exercice et scénarios.

Le free cash-flow se reconstruit à partir de quelques leviers de pilotage :

    Résultat net      = (EBIT − charges d'intérêts) × (1 − taux d'impôt)
    Flux opérationnel ≈ résultat net + amortissements − Δ stocks + Δ dettes fournisseurs
    Free cash-flow    = flux opérationnel − investissements (capex)
    Dette nette fin   = dette nette début − (free cash-flow − dividendes − rachats d'actions)

Les stocks et les dettes fournisseurs de fin d'exercice viennent des délais :

    stocks fin = DIO × coût des ventes du T4 / jours du T4
    dettes fournisseurs fin = DPO × coût des ventes du T4 / jours du T4

Vérification sur FY2018–FY2025 : l'écart entre ce flux opérationnel simplifié et le flux
publié est inférieur à 0,75 % du CA sauf en FY2020 (2,6 %) et FY2023 (1,4 %), voir `proxy_check`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

import pandas as pd

Q4_DAYS = 91


@dataclass(frozen=True)
class Hypotheses:
    revenue: float  # CA de l'exercice (MUSD)
    operating_margin: float  # taux de marge opérationnelle (0,05 = 5 %)
    gross_margin: float  # taux de marge brute, pour le coût des ventes
    da_rate: float  # amortissements totaux / CA
    interest: float  # charges d'intérêts nettes (MUSD)
    tax_rate: float  # taux d'impôt effectif
    q4_cogs_share: float  # part du coût des ventes annuel réalisée au T4
    dio_end: float  # jours de stock en fin d'exercice
    dpo_end: float  # jours de crédit fournisseurs en fin d'exercice
    capex: float
    dividends: float
    buybacks: float
    inventory_start: float
    payables_start: float
    net_debt_start: float


def project(h: Hypotheses) -> dict[str, float]:
    ebit = h.revenue * h.operating_margin
    net_income = (ebit - h.interest) * (1 - h.tax_rate)
    da = h.revenue * h.da_rate
    cogs_q4 = h.revenue * (1 - h.gross_margin) * h.q4_cogs_share
    inventory_end = h.dio_end * cogs_q4 / Q4_DAYS
    payables_end = h.dpo_end * cogs_q4 / Q4_DAYS
    delta_wc = (inventory_end - h.inventory_start) - (payables_end - h.payables_start)
    cfo = net_income + da - delta_wc
    fcf = cfo - h.capex
    net_debt_end = h.net_debt_start - (fcf - h.dividends - h.buybacks)
    return {
        "revenue": h.revenue,
        "operating_income": ebit,
        "net_income": net_income,
        "depreciation": da,
        "inventory_end": inventory_end,
        "payables_end": payables_end,
        "working_capital_change": delta_wc,
        "cfo": cfo,
        "capex": h.capex,
        "free_cash_flow": fcf,
        "net_debt_end": net_debt_end,
    }


def cash_per_day(h: Hypotheses) -> float:
    """Trésorerie libérée par un jour de stock en moins (ou un jour fournisseur en plus), en MUSD."""
    return h.revenue * (1 - h.gross_margin) * h.q4_cogs_share / Q4_DAYS


def base_hypotheses(kpi_q: pd.DataFrame, facts: pd.DataFrame, landing: dict[str, float], fy: int) -> Hypotheses:
    """Hypothèses de base : atterrissage prévu pour le CA et la marge, le reste calé sur l'exercice précédent."""
    prev = fy - 1
    f = facts.assign(fy=facts["period_key"].str[2:6].astype(int))
    flows = f[f["fy"] == prev].pivot_table(index="account", values="value", aggfunc="sum")["value"]
    q_prev = kpi_q[kpi_q["fiscal_year"] == prev].set_index("fiscal_quarter")
    q4 = q_prev.loc[4]
    pretax = flows["operating_income"] - flows["interest_expense"]
    return Hypotheses(
        revenue=landing["revenue"],
        operating_margin=landing["operating_margin"],
        gross_margin=q_prev["gross_margin"].sum() / q_prev["revenue"].sum(),
        da_rate=flows["da_total"] / flows["revenue"],
        interest=flows["interest_expense"],
        tax_rate=flows["income_tax"] / pretax,
        q4_cogs_share=q4["cogs"] / q_prev["cogs"].sum(),
        dio_end=q4["dio_days"],
        dpo_end=q4["dpo_days"],
        capex=flows["capex"],
        dividends=flows["dividends_paid"],
        buybacks=flows["share_buybacks"],
        inventory_start=q4["inventory"],
        payables_start=q4["accounts_payable"],
        net_debt_start=q4["net_debt"],
    )


def scenarios(base: Hypotheses) -> pd.DataFrame:
    """Scénarios à un levier, puis combinés. Chaque ligne : hypothèses modifiées et résultat."""
    cases = {
        "Base": {},
        "Stocks : +5 jours (DIO)": {"dio_end": base.dio_end + 5},
        "Stocks : −5 jours (DIO)": {"dio_end": base.dio_end - 5},
        "Fournisseurs : −5 jours (DPO)": {"dpo_end": base.dpo_end - 5},
        "Capex : +1 Md$": {"capex": base.capex + 1000},
        "Marge opérationnelle : −1 point": {"operating_margin": base.operating_margin - 0.01},
        "Choc type FY2022 : marge −2 pts, stocks +10 j, DPO −5 j": {
            "operating_margin": base.operating_margin - 0.02,
            "dio_end": base.dio_end + 10,
            "dpo_end": base.dpo_end - 5,
        },
        "Plan cash : stocks −5 j, capex −0,5 Md$": {"dio_end": base.dio_end - 5, "capex": base.capex - 500},
    }
    ref = project(base)
    rows = []
    for name, change in cases.items():
        h = replace(base, **change)
        r = project(h)
        rows.append(
            {
                "scenario": name,
                **{k: v for k, v in asdict(h).items() if k in ("operating_margin", "dio_end", "dpo_end", "capex")},
                **r,
                "fcf_vs_base": r["free_cash_flow"] - ref["free_cash_flow"],
            }
        )
    return pd.DataFrame(rows)


def proxy_check(facts: pd.DataFrame) -> pd.DataFrame:
    """Flux opérationnel simplifié vs flux publié, par exercice."""
    f = facts.assign(fy=facts["period_key"].str[2:6].astype(int))
    full = f.groupby("fy")["period_key"].nunique()
    full_years = full[full == 4].index
    flows = f[f["account"].isin(["net_income", "da_total", "cfo", "revenue"])].pivot_table(
        index="fy", columns="account", values="value", aggfunc="sum"
    )
    stocks = f[f["period_key"].str.endswith("Q4") & f["account"].isin(["inventory", "accounts_payable"])].pivot_table(
        index="fy", columns="account", values="value"
    )
    d = flows.join(stocks).loc[lambda x: x.index.isin(full_years)]
    d["cfo_proxy"] = d["net_income"] + d["da_total"] - d["inventory"].diff() + d["accounts_payable"].diff()
    d["gap"] = d["cfo"] - d["cfo_proxy"]
    d["gap_pct_revenue"] = d["gap"] / d["revenue"] * 100
    return d.dropna(subset=["cfo_proxy"]).reset_index()[["fy", "cfo", "cfo_proxy", "gap", "gap_pct_revenue"]]
