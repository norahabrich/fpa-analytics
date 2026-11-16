"""Simulateur d'hypothèses : atterrissage de l'exercice et trésorerie de fin d'année.

Lancement :
    pip install -e ".[app]"
    streamlit run app/simulateur.py

En ligne (Streamlit Community Cloud), seules les dépendances de requirements.txt sont
installées : le dossier src/ est alors ajouté au chemin d'import ci-dessous.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from fpa.config import DATA_DIR  # noqa: E402
from fpa.forecast import cash  # noqa: E402

GOLD = DATA_DIR / "gold"


@st.cache_data
def load():
    kpi_q = pd.read_parquet(GOLD / "kpi_quarterly.parquet")
    facts = pd.read_parquet(GOLD / "fact_financials.parquet")
    landing = pd.read_parquet(GOLD / "forecast_landing.parquet").set_index("metric")
    return kpi_q, facts, landing


def pct(v: float, decimals: int = 1) -> str:
    return f"{v:.{decimals}f} %".replace(".", ",")


def fmt_bn(v: float) -> str:
    return f"{v / 1000:,.1f} Md$".replace(",", " ").replace(".", ",")


kpi_q, facts, landing = load()
fy_label = landing["fiscal_year"].iloc[0]
fy = int(fy_label[2:])
prev_revenue = kpi_q.loc[kpi_q["fiscal_year"] == fy - 1, "revenue"].sum()
growth0 = round(float(landing.loc["net_sales_growth", "landing"]), 1)
margin0 = round(float(landing.loc["operating_margin_rate", "landing"]), 1)
base = cash.base_hypotheses(
    kpi_q, facts, {"revenue": prev_revenue * (1 + growth0 / 100), "operating_margin": margin0 / 100}, fy
)
# Valeurs de départ arrondies au pas des curseurs, pour que la base et la simulation coïncident
base = replace(
    base,
    dio_end=round(base.dio_end * 2) / 2,
    dpo_end=round(base.dpo_end * 2) / 2,
    capex=round(base.capex, -2),
    buybacks=round(base.buybacks, -2),
)

st.set_page_config(page_title="Simulateur FP&A Target", layout="wide")
st.title(f"Target {fy_label} : atterrissage et trésorerie")
st.caption(
    "Base : prévision du projet (réel du 1er semestre + prévision du 2e). Délais, capex et distributions "
    f"de l'exercice FY{fy - 1}. Montants en dollars US. Données SEC EDGAR, calculs du projet."
)

with st.sidebar:
    st.header("Hypothèses")
    growth = st.slider("Croissance du CA (%)", -5.0, 10.0, growth0, 0.1)
    margin = st.slider("Taux de marge opérationnelle (%)", 0.0, 10.0, margin0, 0.1)
    dio = st.slider("Jours de stock en fin d'exercice (DIO)", 35.0, 75.0, base.dio_end, 0.5)
    dpo = st.slider("Jours fournisseurs en fin d'exercice (DPO)", 35.0, 75.0, base.dpo_end, 0.5)
    capex = st.slider("Investissements (Md$)", 1.0, 7.0, base.capex / 1000, 0.1)
    buybacks = st.slider("Rachats d'actions (Md$)", 0.0, 8.0, base.buybacks / 1000, 0.1)

h = replace(
    base,
    revenue=prev_revenue * (1 + growth / 100),
    operating_margin=margin / 100,
    dio_end=dio,
    dpo_end=dpo,
    capex=capex * 1000,
    buybacks=buybacks * 1000,
)
r, r0 = cash.project(h), cash.project(base)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Chiffre d'affaires", fmt_bn(r["revenue"]), f"{growth:+.1f} % vs N-1".replace(".", ","))
c2.metric(
    "Résultat opérationnel", fmt_bn(r["operating_income"]), f"{margin:.1f} % du CA".replace(".", ","), delta_color="off"
)
c3.metric(
    "Free cash-flow", fmt_bn(r["free_cash_flow"]), fmt_bn(r["free_cash_flow"] - r0["free_cash_flow"]) + " vs base"
)
c4.metric(
    "Dette nette fin d'exercice",
    fmt_bn(r["net_debt_end"]),
    fmt_bn(r["net_debt_end"] - r0["net_debt_end"]) + " vs base",
    delta_color="inverse",
)

g = landing.loc["net_sales_growth"]
m = landing.loc["operating_margin_rate"]
st.info(
    f"Dernière guidance ({g['guidance_issued']}) : croissance du CA d'environ {pct(g['guidance_mid'], 0)}, "
    f"marge opérationnelle d'environ {pct(m['guidance_mid'], 0)}. Prévision du projet : {pct(growth0)} "
    f"[{pct(g['low_80'])} ; {pct(g['high_80'])}] et {pct(margin0)} [{pct(m['low_80'])} ; {pct(m['high_80'])}], "
    "intervalles à 80 %."
)

st.subheader("Du résultat au cash")
bridge = pd.DataFrame(
    {
        "Poste": [
            "Résultat net",
            "+ Amortissements",
            "− Variation du BFR (stocks − fournisseurs)",
            "= Flux de trésorerie opérationnel",
            "− Investissements",
            "= Free cash-flow",
        ],
        "Simulation (MUSD)": [
            r["net_income"],
            r["depreciation"],
            -r["working_capital_change"],
            r["cfo"],
            -r["capex"],
            r["free_cash_flow"],
        ],
        "Base (MUSD)": [
            r0["net_income"],
            r0["depreciation"],
            -r0["working_capital_change"],
            r0["cfo"],
            -r0["capex"],
            r0["free_cash_flow"],
        ],
    }
)
st.dataframe(bridge.style.format({"Simulation (MUSD)": "{:,.0f}", "Base (MUSD)": "{:,.0f}"}), hide_index=True)

per_day = cash.cash_per_day(h)
st.caption(
    f"Repère : un jour de stock en moins, ou un jour de crédit fournisseur en plus, libère environ "
    f"{per_day:,.0f} MUSD de trésorerie en fin d'exercice. Un point de marge opérationnelle vaut environ "
    f"{h.revenue * 0.01 * (1 - h.tax_rate):,.0f} MUSD de résultat net."
)
