"""Tests de la phase 3 : ventes comparables, pont de résultat opérationnel, réel vs guidance."""

import pandas as pd
import pytest

from fpa.analysis.comparable_sales import parse_numbers, parse_release, release_period
from fpa.analysis.variance import BRIDGE_STEPS, guidance_vs_actual, operating_income_bridge
from fpa.config import BRONZE_DIR, DATA_DIR, REFERENCE_DIR

GOLD = DATA_DIR / "gold"
RELEASES = BRONZE_DIR / "sec" / "earnings_releases"


# ---------- Ventes comparables ----------


def test_parse_numbers_reads_parentheses_as_negative():
    assert parse_numbers("1.3 % (0.2)0.2 0.3") == [1.3, -0.2, 0.2, 0.3]
    assert parse_numbers("(5.4) %") == [-5.4]


def test_release_period_maps_filing_month_to_fiscal_quarter():
    assert release_period("2022-05-18") == (2022, 1)
    assert release_period("2022-11-16") == (2022, 3)
    assert release_period("2023-02-28") == (2022, 4)  # T4 publié l'année civile suivante


def test_parse_release_handles_q1_two_column_table():
    html = """<table>
    <tr><td>Comparable sales change</td> <td>3.3 %</td> <td>22.9 %</td></tr>
    <tr><td>Number of transactions</td> <td>3.9</td> <td>17.1</td></tr>
    <tr><td>Average transaction amount</td> <td>(0.6)</td> <td>5.0</td></tr>
    </table>"""
    parsed = parse_release(html)
    assert parsed["comparable_sales"][:2] == (3.3, 3.3)
    assert parsed["traffic"][0] == 3.9
    assert parsed["average_ticket"][0] == -0.6


@pytest.fixture(scope="module")
def comps() -> pd.DataFrame:
    return pd.read_csv(REFERENCE_DIR / "comparable_sales.csv")


def test_comparable_sales_decompose_into_traffic_and_ticket(comps):
    assert len(comps) >= 27
    assert comps["period_key"].is_unique
    assert comps["decomposition_gap_pts"].abs().max() <= 0.15, "(1+comp) = (1+trafic)(1+panier), aux arrondis près"


@pytest.mark.skipif(not RELEASES.exists(), reason="communiqués non archivés")
def test_comparable_sales_reproducible_from_archived_releases(comps):
    files = {p.name[:10]: p for p in RELEASES.glob("*/*/*.htm")}
    for row in comps.itertuples():
        parsed = parse_release(files[row.issued_date].read_text(encoding="utf-8", errors="replace"))
        assert parsed["comparable_sales"][0] == row.comparable_sales_pct, row.period_key
        assert parsed["comparable_sales"][2] == row.comparable_sales_source_row, row.period_key
        assert parsed["traffic"][0] == row.traffic_pct, row.period_key


# ---------- Pont de résultat opérationnel ----------


def period(revenue, cogs, sga, da):
    return pd.Series(
        {"revenue": revenue, "cogs": cogs, "sga": sga, "da_opex": da, "operating_income": revenue - cogs - sga - da}
    )


def test_bridge_effects_sum_exactly_to_the_change():
    p0, p1 = period(1000, 700, 200, 30), period(1100, 820, 210, 32)
    b = operating_income_bridge(p0, p1, traffic_pct=4.0, ticket_pct=2.0)
    assert list(b["step"]) == [s for s, _ in BRIDGE_STEPS]
    effects = b.loc[~b["is_total"], "value"].sum()
    assert effects == pytest.approx(p1["operating_income"] - p0["operating_income"])
    # Trafic et panier : 1000 × 4 % = 40 ; 1000 × 1,04 × 2 % = 20,8 de CA, au taux de marge N-1 (7 %)
    v = b.set_index("step")["value"]
    assert v["volume_traffic"] == pytest.approx(40 * 0.07)
    assert v["volume_ticket"] == pytest.approx(20.8 * 0.07)


def test_bridge_without_comparable_sales_puts_all_volume_in_other():
    b = operating_income_bridge(period(1000, 700, 200, 30), period(1100, 770, 220, 33)).set_index("step")
    assert b.loc["volume_traffic", "value"] == 0
    assert b.loc["volume_other", "revenue_effect"] == pytest.approx(100)
    assert b.loc["gross_margin_rate", "value"] == pytest.approx(0)  # taux inchangés


@pytest.fixture(scope="module")
def bridge() -> pd.DataFrame:
    return pd.read_parquet(GOLD / "bridge_operating_income.parquet")


def test_gold_bridges_close_for_every_period(bridge):
    for (_, _), b in bridge.groupby(["grain", "period_key"]):
        b = b.sort_values("step_order")
        start, end = b["value"].iloc[0], b["value"].iloc[-1]
        assert start + b.loc[~b["is_total"], "value"].sum() == pytest.approx(end, abs=0.01)


def test_fy2022_story(bridge):
    b = bridge[(bridge["grain"] == "annual") & (bridge["period_key"] == "FY2022")].set_index("step")["value"]
    assert b["start"] == 8946 and b["end"] == 3848
    assert b["gross_margin_rate"] == pytest.approx(-5140, abs=5)
    assert b[["volume_traffic", "volume_ticket", "volume_other"]].sum() > 0


# ---------- Réel vs guidance ----------


def test_guidance_verdicts():
    kpi_q = pd.DataFrame(
        {
            "fiscal_year": [2022] * 4,
            "fiscal_quarter": [1, 2, 3, 4],
            "revenue": [100.0] * 4,
            "operating_income": [5.0, 1.0, 4.0, 4.0],
        }
    )
    guidance = pd.DataFrame(
        {
            "issued_date": ["2022-03-01", "2022-05-18", "2022-08-17"],
            "fiscal_year": ["FY2022"] * 3,
            "period": ["FY", "Q2", "H2"],
            "metric": ["operating_margin_rate"] * 3,
            "low": [8.0, None, 3.0],
            "high": [None, None, 5.0],
            "point": [None, 1.05, None],
            "unit": ["pct"] * 3,
            "note": [""] * 3,
            "source_url": [""] * 3,
        }
    )
    out = guidance_vs_actual(guidance, kpi_q, pd.DataFrame(), pd.DataFrame())
    assert list(out["actual"]) == pytest.approx([3.5, 1.0, 4.0])
    assert list(out["verdict"]) == ["sous l'objectif", "proche du point visé", "dans la fourchette"]


def test_gold_guidance_fy2022_margin_missed():
    g = pd.read_parquet(GOLD / "guidance_vs_actual.parquet")
    fy = g[(g["fiscal_year"] == "FY2022") & (g["period"] == "FY") & (g["metric"] == "operating_margin_rate")]
    assert len(fy) == 2
    assert (fy["verdict"] == "sous l'objectif").all()
    assert fy["actual"].iloc[0] == pytest.approx(3.53, abs=0.01)
