"""Construit la couche Silver à partir de la dernière archive Bronze.

Sorties (data/silver/) :
- `facts_latest.parquet` : un fait XBRL par (concept, période), dernière version déposée ;
- `financials_quarterly.parquet` : une ligne par (compte, exercice, trimestre) avec la méthode ;
- `financials_annual.parquet` : valeurs d'exercice complet publiées ;
- `restatements.csv` : périodes dont la valeur a changé entre deux dépôts.

Usage :
    python -m fpa.silver.build
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from fpa.config import BRONZE_DIR, DATA_DIR, REFERENCE_DIR, TARGET_CIK
from fpa.ingestion.bronze import latest_snapshot
from fpa.silver.facts import add_periods, flatten, latest_versions
from fpa.silver.quarters import annual_flow, quarterly_flow, quarterly_stock, reported_only

SILVER_DIR = DATA_DIR / "silver"
# FY2017 : premier exercice dont le CA total (`RevenueFromContractWithCustomer…`) est publié
# trimestre par trimestre, retraité selon la norme ASC 606 dans le 10-K de 2019.
FIRST_FISCAL_YEAR = 2017


def load_mapping(path: Path = REFERENCE_DIR / "account_mapping.csv") -> pd.DataFrame:
    mapping = pd.read_csv(path)
    mapping["concepts"] = mapping["concepts"].str.split("|")
    return mapping


def fill_cogs_by_identity(q: pd.DataFrame) -> pd.DataFrame:
    """Complète le coût des ventes quand il n'est pas balisé en XBRL.

    Target n'a pas balisé `CostOfGoodsAndServicesSold` dans ses 10-Q de FY2020 et du
    début de FY2021. Le compte de résultat de Target vérifie exactement :
    CA − coût des ventes − SG&A − amortissements hors coût des ventes = résultat opérationnel
    (contrôle C2 du rapport). On en déduit le coût des ventes manquant (`derived_identity`).
    """
    parts = ["revenue", "sga", "da_opex", "operating_income"]
    wide = q[q["account"].isin([*parts, "cogs"])].pivot_table(
        index=["fiscal_year", "fiscal_quarter"], columns="account", values="value"
    )
    missing = wide[wide["cogs"].isna() & wide[parts].notna().all(axis=1)] if "cogs" in wide else wide.iloc[0:0]
    if missing.empty:
        return q
    ref = q[q["account"] == "operating_income"].set_index(["fiscal_year", "fiscal_quarter"])
    rows = []
    for (fy, fq), r in missing.iterrows():
        src = ref.loc[(fy, fq)]
        rows.append(
            {
                "account": "cogs",
                "fiscal_year": fy,
                "fiscal_quarter": fq,
                "period_start": src["period_start"],
                "period_end": src["period_end"],
                "value": r["revenue"] - r["sga"] - r["da_opex"] - r["operating_income"],
                "method": "derived_identity",
                "concept": None,
                "accn": None,
                "filed": None,
                "restated": False,
            }
        )
    return pd.concat([q, pd.DataFrame(rows)], ignore_index=True)


def build(bronze: Path = BRONZE_DIR, out: Path = SILVER_DIR, cik: str = TARGET_CIK) -> dict[str, pd.DataFrame]:
    mapping = load_mapping()
    facts_raw = json.loads(latest_snapshot(bronze, "sec", "companyfacts", cik).read_bytes())
    concepts = {c for cs in mapping["concepts"] for c in cs}

    facts = add_periods(latest_versions(flatten(facts_raw, concepts)))
    facts = facts[facts["fiscal_year"] >= FIRST_FISCAL_YEAR - 1].reset_index(drop=True)

    quarterly, annual = [], []
    for m in mapping.itertuples():
        if m.kind == "flow":
            quarterly.append(quarterly_flow(facts, m.account, m.concepts))
            annual.append(annual_flow(facts, m.account, m.concepts))
        elif m.kind == "stock":
            quarterly.append(quarterly_stock(facts, m.account, m.concepts))
        else:  # per_share, average : non additifs
            quarterly.append(reported_only(facts, m.account, m.concepts, ("Q",)))
            annual.append(annual_flow(facts, m.account, m.concepts))

    q = fill_cogs_by_identity(pd.concat(quarterly, ignore_index=True))
    q = q[q["fiscal_year"] >= FIRST_FISCAL_YEAR].sort_values(["account", "fiscal_year", "fiscal_quarter"])
    a = pd.concat(annual, ignore_index=True)
    a = a[a["fiscal_year"] >= FIRST_FISCAL_YEAR].sort_values(["account", "fiscal_year"])
    restatements = facts[facts["restated"]].sort_values(["concept", "end"])

    out.mkdir(parents=True, exist_ok=True)
    facts.to_parquet(out / "facts_latest.parquet", index=False)
    q.to_parquet(out / "financials_quarterly.parquet", index=False)
    a.to_parquet(out / "financials_annual.parquet", index=False)
    restatements.to_csv(out / "restatements.csv", index=False)
    return {
        "facts": facts,
        "quarterly": q.reset_index(drop=True),
        "annual": a.reset_index(drop=True),
        "restatements": restatements,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Construit la couche Silver.")
    parser.add_argument("--out", type=Path, default=SILVER_DIR)
    args = parser.parse_args(argv)
    res = build(out=args.out)
    q = res["quarterly"]
    print(
        f"{len(res['facts'])} faits, {len(q)} lignes trimestrielles, "
        f"{q['account'].nunique()} comptes, {len(res['restatements'])} retraitements -> {args.out}"
    )
    print(q.groupby("method").size().to_string())


if __name__ == "__main__":
    main()
