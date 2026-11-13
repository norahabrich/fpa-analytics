"""Inventaires produits à la collecte, pour savoir ce que contiennent les archives.

- `concepts_inventory` : un concept XBRL par ligne (libellé, unité, nombre
  d'observations, première et dernière période). Il sert à repérer les changements
  de libellés, par exemple `Revenues` remplacé par
  `RevenueFromContractWithCustomerExcludingAssessedTax` à partir de 2017.
- `filings_table` : la liste des dépôts (10-K, 10-Q, 8-K) avec leur lien, pour
  vérifier les chiffres à la main et retrouver les communiqués de guidance.
"""

from __future__ import annotations

import pandas as pd

ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{doc}"
KEPT_FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A"}


def concepts_inventory(facts: dict) -> pd.DataFrame:
    rows = []
    for taxonomy, concepts in facts.get("facts", {}).items():
        for concept, body in concepts.items():
            for unit, obs in body.get("units", {}).items():
                ends = [o["end"] for o in obs if "end" in o]
                rows.append(
                    {
                        "taxonomy": taxonomy,
                        "concept": concept,
                        "label": body.get("label"),
                        "unit": unit,
                        "n_obs": len(obs),
                        "first_end": min(ends) if ends else None,
                        "last_end": max(ends) if ends else None,
                        "forms": ",".join(sorted({o.get("form", "") for o in obs} - {""})),
                    }
                )
    cols = ["taxonomy", "concept", "label", "unit", "n_obs", "first_end", "last_end", "forms"]
    return pd.DataFrame(rows, columns=cols).sort_values(["taxonomy", "concept", "unit"], ignore_index=True)


def filings_table(submissions: dict) -> pd.DataFrame:
    recent = submissions.get("filings", {}).get("recent", {})
    df = pd.DataFrame(
        {
            "form": recent.get("form", []),
            "filing_date": recent.get("filingDate", []),
            "report_date": recent.get("reportDate", []),
            "accession_number": recent.get("accessionNumber", []),
            "primary_document": recent.get("primaryDocument", []),
            "items": recent.get("items", [""] * len(recent.get("form", []))),
        }
    )
    df = df[df["form"].isin(KEPT_FORMS)].copy()
    cik_int = int(submissions["cik"])
    df["url"] = [
        ARCHIVES_URL.format(cik_int=cik_int, acc_nodash=acc.replace("-", ""), doc=doc)
        for acc, doc in zip(df["accession_number"], df["primary_document"], strict=True)
    ]
    return df.sort_values("filing_date", ascending=False, kind="stable", ignore_index=True)
