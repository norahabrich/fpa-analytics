"""Tables d'analyse de la phase 3, ajoutées à la couche Gold.

- `fact_comparable_sales` : ventes comparables, trafic et panier moyen par trimestre ;
- `bridge_operating_income` : ponts de résultat opérationnel (annuels et trimestriels) ;
- `guidance_vs_actual` : chaque objectif publié, le réel correspondant et le verdict.

Usage :
    python -m fpa.analysis.build
"""

from __future__ import annotations

import pandas as pd

from fpa.analysis.variance import bridges, guidance_vs_actual
from fpa.config import DATA_DIR, REFERENCE_DIR

GOLD_DIR = DATA_DIR / "gold"


def build(gold=GOLD_DIR) -> dict[str, pd.DataFrame]:
    kpi_q = pd.read_parquet(gold / "kpi_quarterly.parquet")
    kpi_a = pd.read_parquet(gold / "kpi_annual.parquet")
    comps = pd.read_csv(REFERENCE_DIR / "comparable_sales.csv")
    guidance = pd.read_csv(REFERENCE_DIR / "guidance.csv")

    tables = {
        "fact_comparable_sales": comps.drop(columns=[c for c in comps.columns if c.endswith("_source_row")]),
        "bridge_operating_income": bridges(kpi_q, kpi_a, comps),
        "guidance_vs_actual": guidance_vs_actual(guidance, kpi_q, kpi_a, comps),
    }
    for name, df in tables.items():
        df.to_parquet(gold / f"{name}.parquet", index=False)
        df.to_csv(gold / f"{name}.csv", index=False)
    return tables


def main() -> None:
    tables = build()
    for name, df in tables.items():
        print(f"{name:24s} {len(df):5d} lignes")
    b = tables["bridge_operating_income"]
    print(
        b[(b["grain"] == "annual") & (b["period_key"] == "FY2022")][["label_fr", "value"]]
        .round(0)
        .to_string(index=False)
    )
    g = tables["guidance_vs_actual"]
    print(
        g[g["fiscal_year"] == "FY2022"][["issued_date", "period", "metric", "guidance_mid", "actual", "verdict"]]
        .round(2)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
