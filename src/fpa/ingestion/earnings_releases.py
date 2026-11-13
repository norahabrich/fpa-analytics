"""Communiqués de résultats trimestriels (8-K, item 2.02, pièce 99).

Target y publie ses objectifs (« guidance ») : ventes comparables, taux de marge
opérationnelle, BPA. Ces objectifs servent de référence « budget » dans le projet.

Le module :
1. repère les 8-K de résultats dans `filings.csv` ;
2. télécharge la pièce 99 (le communiqué) et l'archive telle quelle en Bronze ;
3. extrait les paragraphes qui parlent de perspectives dans `outlook_excerpts.csv`,
   pour faciliter la saisie sourcée de `data/reference/guidance.csv`.

Usage :
    python -m fpa.ingestion.earnings_releases --since 2019-01-01
    python -m fpa.ingestion.earnings_releases --offline   # réextraction depuis les archives
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd

from fpa.config import BRONZE_DIR, TARGET_CIK
from fpa.ingestion.bronze import archive, latest_snapshot
from fpa.ingestion.sec_client import SecClient, normalize_cik

INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/index.json"
DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{name}"
EXHIBIT_99 = re.compile(r"ex-?99", re.IGNORECASE)
OUTLOOK = re.compile(
    r"\b(guidance|outlook|expects?|expected|expecting|expectations?|anticipates?|forecast|plan(ning)? for)\b.*"
    r"\b(comparable sales|net sales|sales|revenue|operating (income )?margin|EPS|earnings per share|gross margin)",
    re.IGNORECASE,
)
OUTLOOK_HEADER = re.compile(r"has the following (updated )?expectations", re.IGNORECASE)
BOILERPLATE = re.compile(r"forward-looking statements", re.IGNORECASE)


def earnings_filings(filings: pd.DataFrame, since: str | None = None) -> pd.DataFrame:
    """8-K déposés au titre de l'item 2.02 (Results of Operations and Financial Condition)."""
    mask = filings["form"].eq("8-K") & filings["items"].fillna("").str.contains(r"\b2\.02\b")
    out = filings[mask]
    if since:
        out = out[out["filing_date"] >= since]
    return out.sort_values("filing_date", ignore_index=True)


def pick_exhibit_99(index: dict) -> str | None:
    """Nom du fichier HTML de la pièce 99 dans l'index d'un dépôt EDGAR."""
    names = [i["name"] for i in index.get("directory", {}).get("item", [])]
    candidates = [n for n in names if EXHIBIT_99.search(n) and n.lower().endswith((".htm", ".html"))]
    return sorted(candidates)[0] if candidates else None


class _TextExtractor(HTMLParser):
    BLOCKS = {"p", "div", "tr", "br", "li", "h1", "h2", "h3", "h4", "table"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self._skip += 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_paragraphs(html: str) -> list[str]:
    parser = _TextExtractor()
    parser.feed(html)
    text = "".join(parser.parts).replace("\xa0", " ")
    paragraphs = (re.sub(r"\s+", " ", block).strip() for block in text.split("\n"))
    return [p for p in paragraphs if len(p) > 40]


def outlook_paragraphs(html: str) -> list[str]:
    """Paragraphes de perspectives : phrases d'objectifs, et puces sous « the following expectations »."""
    out, in_list = [], False
    for p in html_to_paragraphs(html):
        if BOILERPLATE.search(p):
            in_list = False
            continue
        if OUTLOOK_HEADER.search(p):
            in_list = True
            out.append(p)
            continue
        if in_list and p.startswith("•"):
            out.append(p)
            continue
        in_list = False
        if OUTLOOK.search(p):
            out.append(p)
    return out


def run(cik: str, root: Path, client: SecClient, since: str | None, now: datetime | None = None) -> pd.DataFrame:
    cik = normalize_cik(cik)
    cik_int = int(cik)
    now = now or datetime.now(UTC)
    filings = pd.read_csv(latest_snapshot(root, "sec", "submissions", cik).with_name("filings.csv"))

    excerpts = []
    for row in earnings_filings(filings, since).itertuples():
        acc = row.accession_number.replace("-", "")
        index = json.loads(client.get(INDEX_URL.format(cik_int=cik_int, acc_nodash=acc)).content)
        name = pick_exhibit_99(index)
        if name is None:
            excerpts.append(
                {
                    "filing_date": row.filing_date,
                    "accession_number": row.accession_number,
                    "url": None,
                    "excerpt": "PIÈCE 99 INTROUVABLE",
                }
            )
            continue
        url = DOC_URL.format(cik_int=cik_int, acc_nodash=acc, name=name)
        resp = client.get(url)
        archive(
            resp.content,
            root=root,
            source="sec",
            dataset="earnings_releases",
            cik=cik,
            url=url,
            retrieved_at=now,
            filename=f"{row.filing_date}_{row.accession_number}_{name}",
        )
        for para in outlook_paragraphs(resp.content.decode("utf-8", errors="replace")):
            excerpts.append(
                {"filing_date": row.filing_date, "accession_number": row.accession_number, "url": url, "excerpt": para}
            )
    return pd.DataFrame(excerpts, columns=["filing_date", "accession_number", "url", "excerpt"])


def excerpts_from_archive(root: Path, cik: str) -> pd.DataFrame:
    """Recalcule les extraits à partir des communiqués déjà archivés, sans réseau."""
    base = root / "sec" / "earnings_releases" / f"CIK{normalize_cik(cik)}"
    excerpts = []
    for path in sorted(base.glob("*/*.htm")):
        filing_date, accession, _ = path.name.split("_", 2)
        for para in outlook_paragraphs(path.read_text(encoding="utf-8", errors="replace")):
            excerpts.append(
                {
                    "filing_date": filing_date,
                    "accession_number": accession,
                    "file": path.relative_to(root).as_posix(),
                    "excerpt": para,
                }
            )
    return pd.DataFrame(excerpts, columns=["filing_date", "accession_number", "file", "excerpt"])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Collecte des communiqués de résultats (pièce 99).")
    parser.add_argument("--cik", default=TARGET_CIK)
    parser.add_argument("--root", type=Path, default=BRONZE_DIR)
    parser.add_argument("--since", default="2019-01-01", help="Date de dépôt minimale (AAAA-MM-JJ)")
    parser.add_argument("--out", type=Path, default=None, help="CSV des extraits (défaut : à côté des archives)")
    parser.add_argument("--offline", action="store_true", help="Réextraire depuis les archives, sans réseau")
    args = parser.parse_args(argv)
    if args.offline:
        df = excerpts_from_archive(args.root, args.cik)
    else:
        df = run(args.cik, args.root, SecClient(), args.since)
    base = args.root / "sec" / "earnings_releases" / f"CIK{normalize_cik(args.cik)}"
    out = args.out or base / "outlook_excerpts.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"{df['accession_number'].nunique()} communiqués, {len(df)} extraits -> {out}")


if __name__ == "__main__":
    main()
