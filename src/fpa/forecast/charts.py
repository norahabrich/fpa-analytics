"""Graphiques de la phase 4 (docs/img/).

Usage :
    python -m fpa.forecast.charts
"""

from __future__ import annotations

import pandas as pd
from matplotlib.ticker import FuncFormatter, PercentFormatter

from fpa.analysis.charts import BLUE, GOLD, GREY, GRID, INK, INK2, ORANGE, SURFACE, _save, plt

BN = FuncFormatter(lambda v, _: f"{v / 1000:,.0f} Md$".replace(",", " "))


def revenue_forecast() -> None:
    fq = pd.read_parquet(GOLD / "forecast_quarterly.parquet")
    r = fq[(fq["series"] == "revenue")].reset_index(drop=True)
    r = r[r["period_key"] >= "FY2022-Q1"].reset_index(drop=True)
    act, fut = r[r["kind"] == "réel"], r[r["kind"] == "prévision"]
    fig, ax = plt.subplots(figsize=(10, 4.4))
    ax.plot(act.index, act["value"], color=BLUE, linewidth=2, marker="o", markersize=4, label="Réel")
    x = [act.index[-1], *fut.index]
    ax.fill_between(
        x,
        [act["value"].iloc[-1], *fut["low"]],
        [act["value"].iloc[-1], *fut["high"]],
        color=ORANGE,
        alpha=0.18,
        linewidth=0,
        label="Intervalle à 80 %",
    )
    ax.plot(
        x,
        [act["value"].iloc[-1], *fut["value"]],
        color=ORANGE,
        linewidth=2,
        linestyle="--",
        marker="o",
        markersize=4,
        label="Prévision (moyenne référence + ETS)",
    )
    ticks = [i for i, k in enumerate(r["period_key"]) if k.endswith("Q1")]
    ax.set_xticks(ticks, [r.loc[i, "period_key"][:6] for i in ticks])
    ax.yaxis.set_major_formatter(BN)
    ax.set_ylim(20000, 36000)
    ax.legend(frameon=False, loc="upper left", ncols=3)
    land = pd.read_parquet(GOLD / "forecast_landing.parquet").set_index("metric").loc["net_sales_growth"]
    ax.set_title(
        f"{land['fiscal_year']} : la prévision place la croissance du CA à {land['landing']:.1f} %, "
        f"pour un objectif d'environ {land['guidance_mid']:.0f} %".replace(".", ",")
    )
    ax.text(
        0,
        -0.14,
        "CA trimestriel publié et prévision des 4 trimestres suivants. Intervalle tiré des erreurs de la "
        "validation chronologique. Source : SEC EDGAR, calculs du projet.",
        transform=ax.transAxes,
        fontsize=8.5,
        color=INK2,
    )
    _save(fig, "prevision-ca.png")


def model_accuracy() -> None:
    s = pd.read_parquet(GOLD / "forecast_scores.parquet")
    s = s[(s["series"] == "revenue") & (s["horizon"] != "tous")].assign(h=lambda d: d["horizon"].astype(int))
    style = {
        "combo": (BLUE, 2.4, "Moyenne référence + ETS"),
        "naive_seasonal": (ORANGE, 2.0, "Référence saisonnière (N-1)"),
    }
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for model, d in s.groupby("model"):
        color, lw, label = style.get(model, (GREY, 1.2, d["model_label"].iloc[0]))
        d = d.sort_values("h")
        ax.plot(d["h"], d["wape_pct"], color=color, linewidth=lw, marker="o", markersize=5)
        ax.text(4.08, d["wape_pct"].iloc[-1], label, va="center", fontsize=9, color=INK if color != GREY else INK2)
    ax.set_xticks([1, 2, 3, 4], ["1 trimestre", "2 trimestres", "3 trimestres", "4 trimestres"])
    ax.set_xlim(0.8, 5.6)
    ax.yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax.set_ylim(0, 8)
    ax.set_title("Prévoir le CA : la combinaison bat la référence jusqu'à 3 trimestres")
    ax.text(
        0,
        -0.16,
        "WAPE (erreur absolue / CA réel) selon l'horizon de prévision, 66 prévisions par modèle, "
        "FY2022-T1 à FY2026-T2.",
        transform=ax.transAxes,
        fontsize=8.5,
        color=INK2,
    )
    _save(fig, "precision-modeles.png")


def cash_scenarios() -> None:
    c = pd.read_parquet(GOLD / "cash_scenarios.parquet").iloc[::-1].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    colors = [
        GREY if s == "Base" else (BLUE if v >= 0 else ORANGE)
        for s, v in zip(c["scenario"], c["fcf_vs_base"], strict=True)
    ]
    ax.barh(c.index, c["free_cash_flow"], color=colors, height=0.6, edgecolor=SURFACE, linewidth=2)
    for i, v in enumerate(c["free_cash_flow"]):
        ax.text(
            v + (120 if v >= 0 else -120),
            i,
            f"{v / 1000:,.1f} Md$".replace(".", ","),
            va="center",
            ha="left" if v >= 0 else "right",
            fontsize=9,
            color=INK,
        )
    ax.set_yticks(c.index, c["scenario"])
    ax.axvline(0, color=INK2, linewidth=0.8)
    ax.grid(axis="x", color=GRID)
    ax.grid(axis="y", visible=False)
    ax.set_axisbelow(True)
    ax.xaxis.set_major_formatter(BN)
    ax.set_xlim(-3000, 7500)
    fy = c["fiscal_year"].iloc[0]
    ax.set_title(f"Free cash-flow {fy} : 5 jours de stock pèsent plus que 1 Md$ de capex")
    ax.text(
        0,
        -0.14,
        "Free cash-flow de fin d'exercice selon les leviers. Base : atterrissage prévu, délais et capex "
        "de l'exercice précédent. Calculs du projet.",
        transform=ax.transAxes,
        fontsize=8.5,
        color=INK2,
    )
    _save(fig, "scenarios-cash.png")


def main() -> None:
    revenue_forecast()
    model_accuracy()
    cash_scenarios()
    print("Graphiques de prévision écrits dans docs/img/")


if __name__ == "__main__":
    main()
