"""Ventes comparables publiées : évolution, trafic et panier moyen, par trimestre.

Chaque communiqué de résultats contient un tableau « Comparable Sales » :

    Comparable sales change            2.7 %   12.7 %   2.9 %   14.4 %
    Number of transactions (traffic)   1.4     12.9     2.6     14.0
    Average transaction amount         1.3     (0.2)    0.2     0.3

Colonnes : trimestre courant, même trimestre N-1, cumul courant, cumul N-1.
On lit la colonne du trimestre courant. Les ventes comparables se décomposent en
(1 + comp) = (1 + trafic) × (1 + panier moyen) : c'est notre effet volume / prix réel.

Usage :
    python -m fpa.analysis.comparable_sales   # écrit data/reference/comparable_sales.csv
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from fpa.config import BRONZE_DIR, REFERENCE_DIR
from fpa.ingestion.earnings_releases import html_to_paragraphs

NUMBER = re.compile(r"\((\d+(?:\.\d+)?)\)|(-?\d+(?:\.\d+)?)")
ROWS = {
    "comparable_sales": re.compile(r"^Comparable sales change"),
    "traffic": re.compile(r"^Number of transactions( \(traffic\))?"),
    "average_ticket": re.compile(r"^Average transaction amount"),
}
# Mois de publication -> trimestre fiscal annoncé
QUARTER_BY_RELEASE_MONTH = {2: 4, 3: 4, 5: 1, 6: 1, 8: 2, 9: 2, 11: 3, 12: 3}


def parse_numbers(text: str) -> list[float]:
    """'1.3 (0.2)0.2 0.3' -> [1.3, -0.2, 0.2, 0.3] (parenthèses = négatif)."""
    return [-float(neg) if neg else float(pos) for neg, pos in NUMBER.findall(text)]


def release_period(filing_date: str) -> tuple[int, int]:
    year, month = int(filing_date[:4]), int(filing_date[5:7])
    quarter = QUARTER_BY_RELEASE_MONTH[month]
    return (year - 1, quarter) if quarter == 4 else (year, quarter)


def parse_release(html: str) -> dict[str, tuple[float, float | None, str]]:
    """(trimestre courant, cumul courant, ligne source) pour chaque ligne du tableau trouvée.

    Le cumul courant est la 3e colonne quand le tableau en a 4 (absent au T1).
    """
    out: dict[str, tuple[float, float | None, str]] = {}
    for p in html_to_paragraphs(html, min_length=1):
        for key, pattern in ROWS.items():
            if key not in out and pattern.match(p):
                values = parse_numbers(pattern.sub("", p))
                if len(values) >= 2:
                    out[key] = (values[0], values[2] if len(values) >= 4 else values[0], p)
    return out


def build(bronze: Path = BRONZE_DIR) -> pd.DataFrame:
    urls = {}
    for line in (bronze / "_ingestion_log.jsonl").read_text().splitlines():
        rec = json.loads(line)
        if rec["dataset"] == "earnings_releases":
            urls[Path(rec["path"]).name] = rec["url"]

    rows = []
    for path in sorted((bronze / "sec" / "earnings_releases").glob("*/*/*.htm")):
        filing_date = path.name[:10]
        parsed = parse_release(path.read_text(encoding="utf-8", errors="replace"))
        if "comparable_sales" not in parsed:
            continue
        fy, fq = release_period(filing_date)
        row = {"fiscal_year": fy, "fiscal_quarter": fq, "period_key": f"FY{fy}-Q{fq}", "issued_date": filing_date}
        for key in ROWS:
            quarter, ytd, source = parsed.get(key, (None, None, None))
            row[f"{key}_pct"] = quarter
            row[f"{key}_ytd_pct"] = ytd
            row[f"{key}_source_row"] = source
        row["source_url"] = urls.get(path.name)
        rows.append(row)
    df = pd.DataFrame(rows).sort_values(["fiscal_year", "fiscal_quarter"], ignore_index=True)
    # Écart de la décomposition multiplicative, dû aux arrondis à 0,1 point
    df["decomposition_gap_pts"] = (
        ((1 + df["traffic_pct"] / 100) * (1 + df["average_ticket_pct"] / 100) - 1) * 100 - df["comparable_sales_pct"]
    ).round(2)
    return df


def main() -> None:
    df = build()
    out = REFERENCE_DIR / "comparable_sales.csv"
    df.to_csv(out, index=False)
    print(f"{len(df)} trimestres -> {out}")
    print(
        df[
            ["period_key", "comparable_sales_pct", "traffic_pct", "average_ticket_pct", "decomposition_gap_pts"]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
