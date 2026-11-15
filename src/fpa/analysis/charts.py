"""Graphiques statiques de l'analyse (docs/img/), générés à partir de la couche Gold.

Usage :
    python -m fpa.analysis.charts
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter, PercentFormatter  # noqa: E402

from fpa.config import DATA_DIR, PROJECT_ROOT  # noqa: E402

GOLD = DATA_DIR / "gold"
OUT = PROJECT_ROOT / "docs" / "img"

# Palette de référence (validée daltonisme) : bleu, orange, gris neutre
BLUE, ORANGE, GREY = "#2a78d6", "#eb6834", "#8a8984"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK2,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "xtick.color": INK2,
        "ytick.color": INK2,
        "font.size": 10,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "text.color": INK,
    }
)

BN = FuncFormatter(lambda v, _: f"{v / 1000:,.0f} Md$".replace(",", " "))


def _save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, dpi=200, bbox_inches="tight")
    plt.close(fig)


def waterfall_fy2022() -> None:
    """Pont de résultat opérationnel FY2021 -> FY2022."""
    b = pd.read_parquet(GOLD / "bridge_operating_income.parquet")
    b = b[(b["grain"] == "annual") & (b["period_key"] == "FY2022")].sort_values("step_order")
    # Regroupe les trois effets volume pour la lisibilité
    vol = b[b["step"].str.startswith("volume")]["value"].sum()
    steps = [
        ("EBIT FY2021", b.iloc[0]["value"], "total"),
        ("Volume\n(CA +3,1 Md$)", vol, "delta"),
        ("Taux de\nmarge brute", b.set_index("step").loc["gross_margin_rate", "value"], "delta"),
        ("Taux de\nSG&A", b.set_index("step").loc["sga_rate", "value"], "delta"),
        ("Taux\nd'amortissements", b.set_index("step").loc["da_rate", "value"], "delta"),
        ("EBIT FY2022", b.iloc[-1]["value"], "total"),
    ]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    running = 0.0
    for i, (_label, v, kind) in enumerate(steps):
        if kind == "total":
            bottom, height, color = 0, v, GREY
            running = v
        else:
            bottom = running if v >= 0 else running + v
            height, color = abs(v), BLUE if v >= 0 else ORANGE
            running += v
        ax.bar(i, height, bottom=bottom, color=color, width=0.62, edgecolor=SURFACE, linewidth=2)
        text = f"{v / 1000:,.1f} Md$" if kind == "total" else f"{v / 1000:+,.1f} Md$"
        ax.text(i, bottom + height + 120, text.replace(".", ","), ha="center", va="bottom", fontsize=10, color=INK)
    ax.set_xticks(range(len(steps)), [s[0] for s in steps])
    ax.yaxis.set_major_formatter(BN)
    ax.set_ylim(0, 10500)
    ax.set_title("La chute du taux de marge brute explique presque toute la baisse de l'EBIT en FY2022")
    ax.text(
        0,
        -0.2,
        "Résultat opérationnel de Target, FY2021 (févr. 2021 – janv. 2022) vs FY2022. "
        "Source : SEC EDGAR, calculs du projet.",
        transform=ax.transAxes,
        fontsize=8.5,
        color=INK2,
    )
    _save(fig, "pont-ebit-fy2022.png")


def margin_vs_guidance() -> None:
    """Taux de marge opérationnelle trimestriel et objectifs annuels publiés."""
    q = pd.read_parquet(GOLD / "kpi_quarterly.parquet")
    q = q[q["fiscal_year"] >= 2019].reset_index(drop=True)
    g = pd.read_parquet(GOLD / "guidance_vs_actual.parquet")
    g = g[(g["metric"] == "operating_margin_rate") & (g["period"] == "FY")]
    x = range(len(q))
    pos = {k: i for i, k in enumerate(q["period_key"])}

    fig, ax = plt.subplots(figsize=(10, 4.4))
    ax.plot(
        x, q["operating_margin_rate"] * 100, color=BLUE, linewidth=2, marker="o", markersize=4, label="Réel trimestriel"
    )
    for r in g.itertuples():
        fy = int(r.fiscal_year[2:])
        xs = [pos.get(f"FY{fy}-Q1"), pos.get(f"FY{fy}-Q4", pos.get(f"FY{fy}-Q2"))]
        if None in xs:
            continue
        ax.plot(xs, [r.guidance_mid] * 2, color=ORANGE, linewidth=1.6, linestyle="--")
    ax.plot([], [], color=ORANGE, linestyle="--", label="Objectif annuel publié (chaque révision)")
    ticks = [i for i, k in enumerate(q["period_key"]) if k.endswith("Q1")]
    ax.set_xticks(ticks, [q.loc[i, "period_key"][:6] for i in ticks])
    ax.yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax.set_ylim(0, 11)
    i22 = pos["FY2022-Q2"]
    ax.annotate(
        "T2 FY2022 : 1,2 %\n(objectif initial ≥ 8 %)",
        (i22, q.loc[i22, "operating_margin_rate"] * 100),
        xytext=(i22 + 1.2, 1.2),
        fontsize=9,
        color=INK,
        arrowprops={"arrowstyle": "-", "color": INK2, "linewidth": 0.8},
    )
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0, -0.09), ncols=2)
    ax.set_title("FY2022 : la marge reste loin de l'objectif de 8 %, puis de l'objectif révisé à 6 %")
    ax.text(
        0,
        -0.24,
        "Taux de marge opérationnelle (EBIT / CA). Objectifs FY2021 et FY2022 : 8 % ou plus, puis "
        "≈ 6 %. Source : SEC EDGAR, communiqués de résultats.",
        transform=ax.transAxes,
        fontsize=8.5,
        color=INK2,
    )
    _save(fig, "marge-vs-guidance.png")


def inventory_and_gross_margin() -> None:
    """Deux panneaux alignés : jours de stock et taux de marge brute (même axe du temps)."""
    q = pd.read_parquet(GOLD / "kpi_quarterly.parquet")
    q = q[q["fiscal_year"] >= 2019].reset_index(drop=True)
    x = range(len(q))
    ticks = [i for i, k in enumerate(q["period_key"]) if k.endswith("Q1")]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 5.6), sharex=True, gridspec_kw={"hspace": 0.35})
    a1.plot(x, q["inventory"] / 1000, color=BLUE, linewidth=2, marker="o", markersize=3.5)
    a1.set_title("Les stocks gonflent fin FY2021 – début FY2022, puis la marge brute s'effondre", fontsize=12)
    a1.set_ylabel("Stocks (Md$)")
    a2.plot(x, q["gross_margin_rate"] * 100, color=BLUE, linewidth=2, marker="o", markersize=3.5)
    a2.set_ylabel("Taux de marge brute")
    a2.yaxis.set_major_formatter(PercentFormatter(decimals=0))
    a2.set_xticks(ticks, [q.loc[i, "period_key"][:6] for i in ticks])
    for ax in (a1, a2):
        ax.axvspan(
            q.index[q["period_key"] == "FY2022-Q1"][0] - 0.5,
            q.index[q["period_key"] == "FY2022-Q4"][0] + 0.5,
            color=GRID,
            alpha=0.6,
            linewidth=0,
        )
    a2.text(
        0,
        -0.32,
        "Stocks en fin de trimestre ; marge brute = (CA − coût des ventes) / CA. Zone grisée : FY2022. "
        "Source : SEC EDGAR.",
        transform=a2.transAxes,
        fontsize=8.5,
        color=INK2,
    )
    _save(fig, "stocks-et-marge-brute.png")


def comparable_sales() -> None:
    """Ventes comparables trimestrielles et leurs deux moteurs : trafic et panier moyen."""
    c = pd.read_csv(PROJECT_ROOT / "data" / "reference" / "comparable_sales.csv")
    c = c[c["fiscal_year"] >= 2021].reset_index(drop=True)
    x = range(len(c))
    w = 0.38
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.bar([i - w / 2 for i in x], c["traffic_pct"], width=w, color=BLUE, label="Trafic (nombre de transactions)")
    ax.bar([i + w / 2 for i in x], c["average_ticket_pct"], width=w, color=ORANGE, label="Panier moyen")
    ax.plot(x, c["comparable_sales_pct"], color=INK, linewidth=0, marker="D", markersize=5, label="Ventes comparables")
    ax.axhline(0, color=INK2, linewidth=0.8)
    ticks = [i for i, k in enumerate(c["period_key"]) if k.endswith("Q1")]
    ax.set_xticks(ticks, [c.loc[i, "period_key"][:6] for i in ticks])
    ax.yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax.legend(frameon=False, ncols=3, loc="upper right")
    ax.set_title("Le trafic porte les ventes : il ralentit dès FY2022 et recule en FY2023")
    ax.text(
        0,
        -0.16,
        "Variation vs même trimestre N-1. (1 + ventes comparables) = (1 + trafic) × (1 + panier moyen). "
        "Source : communiqués de résultats de Target.",
        transform=ax.transAxes,
        fontsize=8.5,
        color=INK2,
    )
    _save(fig, "ventes-comparables.png")


def main() -> None:
    waterfall_fy2022()
    margin_vs_guidance()
    inventory_and_gross_margin()
    comparable_sales()
    print(f"Graphiques écrits dans {OUT}")


if __name__ == "__main__":
    main()
