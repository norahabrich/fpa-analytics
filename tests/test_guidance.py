"""Contrôles du référentiel de guidance : chaque ligne doit être traçable jusqu'au communiqué archivé."""

import re

import pandas as pd
import pytest

from fpa.config import BRONZE_DIR, REFERENCE_DIR
from fpa.ingestion.earnings_releases import html_to_paragraphs

GUIDANCE = REFERENCE_DIR / "guidance.csv"
RELEASES = BRONZE_DIR / "sec" / "earnings_releases"
METRICS = {
    "comparable_sales_growth",
    "revenue_growth",
    "net_sales_growth",
    "operating_margin_rate",
    "operating_income_change",
    "eps_adjusted",
}


@pytest.fixture(scope="module")
def guidance() -> pd.DataFrame:
    return pd.read_csv(GUIDANCE)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("’", "'").replace("\xa0", " ")).strip().lower()


def test_schema_and_values(guidance):
    assert set(guidance["metric"]) <= METRICS
    assert set(guidance["period"]) <= {"Q1", "Q2", "Q3", "Q4", "H2", "FY"}
    assert guidance[["low", "high", "point"]].notna().any(axis=1).all(), "chaque ligne a au moins une valeur"
    both = guidance.dropna(subset=["low", "high"])
    assert (both["low"] <= both["high"]).all()
    assert guidance["source_url"].str.startswith("https://www.sec.gov/Archives/edgar/data/27419/").all()


@pytest.mark.skipif(not RELEASES.exists(), reason="communiqués non archivés")
def test_every_quote_is_in_its_archived_release(guidance):
    files = {p.name.split("_")[0]: p for p in RELEASES.glob("*/*/*.htm")}
    for row in guidance.itertuples():
        path = files[row.issued_date]
        html = path.read_text(encoding="utf-8", errors="replace")
        body = normalize(" ".join(html_to_paragraphs(html)) + " " + re.sub(r"<[^>]+>", " ", html))
        for fragment in row.quote_en.split("..."):
            assert normalize(fragment) in body, f"{row.issued_date} : citation introuvable « {fragment} »"
