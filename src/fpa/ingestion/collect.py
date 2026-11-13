"""Collecte Phase 1 : télécharge et archive les données SEC de l'entreprise suivie.

Usage :
    export SEC_USER_AGENT="Prénom Nom prenom.nom@exemple.com"
    python -m fpa.ingestion.collect                 # Target par défaut
    python -m fpa.ingestion.collect --cik 764478    # une autre entreprise
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from fpa.config import BRONZE_DIR, TARGET_CIK
from fpa.ingestion.bronze import archive
from fpa.ingestion.inventory import concepts_inventory, filings_table
from fpa.ingestion.sec_client import SecClient, normalize_cik


def run(cik: str, root: Path, client: SecClient, now: datetime | None = None) -> dict:
    cik = normalize_cik(cik)
    now = now or datetime.now(UTC)
    summary: dict = {"cik": cik, "retrieved_at": now.isoformat(timespec="seconds")}

    facts_resp = client.company_facts(cik)
    rec = archive(
        facts_resp.content,
        root=root,
        source="sec",
        dataset="companyfacts",
        cik=cik,
        url=facts_resp.url,
        retrieved_at=now,
    )
    facts = json.loads(facts_resp.content)
    inv = concepts_inventory(facts)
    inv.to_csv((root / rec.path).with_name("concepts_inventory.csv"), index=False)
    summary.update(entity=facts.get("entityName"), concepts=len(inv), companyfacts=rec.status)

    sub_resp = client.submissions(cik)
    rec = archive(
        sub_resp.content, root=root, source="sec", dataset="submissions", cik=cik, url=sub_resp.url, retrieved_at=now
    )
    filings = filings_table(json.loads(sub_resp.content))
    filings.to_csv((root / rec.path).with_name("filings.csv"), index=False)
    summary.update(filings=len(filings), submissions=rec.status)
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Collecte des données SEC EDGAR (couche Bronze).")
    parser.add_argument("--cik", default=TARGET_CIK, help="CIK de l'entreprise (Target par défaut)")
    parser.add_argument("--root", type=Path, default=BRONZE_DIR, help="Dossier de la couche Bronze")
    args = parser.parse_args(argv)
    summary = run(args.cik, args.root, SecClient())
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
