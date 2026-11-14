"""Tests de la couche Silver (règles de reconstruction) et Gold (contrôles sur les vraies données)."""

import re
from datetime import date

import pandas as pd
import pytest

from fpa.config import BRONZE_DIR, REFERENCE_DIR
from fpa.ingestion.earnings_releases import html_to_paragraphs
from fpa.silver.calendar import duration_class, fiscal_period
from fpa.silver.facts import add_periods, latest_versions
from fpa.silver.quarters import quarterly_flow, quarterly_stock

D = date.fromisoformat


# --- Calendrier fiscal -----------------------------------------------------------


@pytest.mark.parametrize(
    "end, expected",
    [
        ("2022-04-30", (2022, 1)),
        ("2022-07-30", (2022, 2)),
        ("2022-10-29", (2022, 3)),
        ("2023-01-28", (2022, 4)),
        ("2024-02-03", (2023, 4)),
    ],
)
def test_fiscal_period(end, expected):
    assert fiscal_period(D(end)) == expected


def test_fiscal_period_rejects_unexpected_month():
    with pytest.raises(ValueError):
        fiscal_period(D("2022-06-15"))


@pytest.mark.parametrize(
    "start, end, label",
    [
        ("2022-01-30", "2022-04-30", "Q"),
        ("2022-10-30", "2023-01-28", "Q"),
        ("2023-10-29", "2024-02-03", "Q"),  # T4 de 14 semaines
        ("2022-01-30", "2022-07-30", "6M"),
        ("2022-01-30", "2022-10-29", "9M"),
        ("2022-01-30", "2023-01-28", "FY"),
        ("2023-01-29", "2024-02-03", "FY"),  # 53 semaines
        ("2022-01-30", "2022-03-01", None),
    ],
)
def test_duration_class(start, end, label):
    assert duration_class(D(start), D(end)) == label


# --- Dernière version et retraitements -----------------------------------------------


def obs(concept, start, end, val, filed, accn="a"):
    return {
        "concept": concept,
        "unit": "USD",
        "start": D(start) if start else None,
        "end": D(end),
        "val": val,
        "accn": accn,
        "form": "10-Q",
        "filed": D(filed),
        "fp": None,
        "frame": None,
    }


def test_latest_versions_keeps_last_filed_and_flags_restatement():
    df = pd.DataFrame(
        [
            obs("X", "2017-01-29", "2017-04-29", 100.0, "2017-05-22", "old"),
            obs("X", "2017-01-29", "2017-04-29", 97.0, "2019-03-13", "new"),
            obs("X", "2017-04-30", "2017-07-29", 50.0, "2017-08-21"),
            obs("X", "2017-04-30", "2017-07-29", 50.0, "2018-08-27"),
        ]
    )
    out = latest_versions(df).set_index("end")
    assert out.loc[D("2017-04-29"), "val"] == 97.0
    assert out.loc[D("2017-04-29"), "accn"] == "new"
    assert bool(out.loc[D("2017-04-29"), "restated"]) is True
    assert bool(out.loc[D("2017-07-29"), "restated"]) is False
    assert out.loc[D("2017-07-29"), "n_filings"] == 2


# --- Reconstruction trimestrielle --------------------------------------------------


def year_of_ytd(concept="CF", values=(10.0, 25.0, 45.0, 70.0)):
    """Flux publié seulement en cumul : 3, 6, 9 mois et exercice."""
    ends = ["2022-04-30", "2022-07-30", "2022-10-29", "2023-01-28"]
    rows = [obs(concept, "2022-01-30", e, v, "2023-03-01") for e, v in zip(ends, values, strict=True)]
    return add_periods(latest_versions(pd.DataFrame(rows)))


def test_quarterly_flow_derives_quarters_from_ytd():
    q = quarterly_flow(year_of_ytd(), "cfo", ["CF"]).set_index("fiscal_quarter")
    assert q["value"].tolist() == [10.0, 15.0, 20.0, 25.0]
    assert q["method"].tolist() == ["reported", "derived_ytd", "derived_ytd", "derived_fy"]
    assert q.loc[4, "period_start"] == D("2022-10-29")


def test_quarterly_flow_prefers_reported_quarter_and_first_concept():
    facts = year_of_ytd("OLD")
    extra = add_periods(
        latest_versions(
            pd.DataFrame(
                [
                    obs("NEW", "2022-05-01", "2022-07-30", 14.0, "2022-08-20"),
                    obs("NEW", "2022-01-30", "2022-04-30", 10.0, "2022-05-20"),
                ]
            )
        )
    )
    q = quarterly_flow(pd.concat([facts, extra]), "x", ["NEW", "OLD"]).set_index("fiscal_quarter")
    assert q.loc[2, "value"] == 14.0 and q.loc[2, "method"] == "reported" and q.loc[2, "concept"] == "NEW"
    assert q.loc[3, "value"] == 20.0 and q.loc[3, "concept"] == "OLD"


def test_quarterly_stock_takes_period_end_balance():
    df = add_periods(
        latest_versions(
            pd.DataFrame(
                [
                    obs("Inv", None, "2022-04-30", 5.0, "2022-05-20"),
                    obs("Inv", None, "2023-01-28", 7.0, "2023-03-01"),
                ]
            )
        )
    )
    q = quarterly_stock(df, "inventory", ["Inv"]).set_index("fiscal_quarter")
    assert q.loc[1, "value"] == 5.0 and q.loc[4, "value"] == 7.0


# --- Référentiel de rapprochement -----------------------------------------------------


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("’", "'").replace("\xa0", " ")).strip().lower()


def test_checkpoint_quotes_are_in_archived_releases():
    cp = pd.read_csv(REFERENCE_DIR / "reported_checkpoints.csv")
    files = {p.name.split("_")[0]: p for p in (BRONZE_DIR / "sec" / "earnings_releases").glob("*/*/*.htm")}
    for r in cp.itertuples():
        html = files[r.issued_date].read_text(encoding="utf-8", errors="replace")
        assert normalize(r.quote_en) in normalize(" ".join(html_to_paragraphs(html))), r.quote_en


# --- Chaîne complète sur les vraies données -----------------------------------------


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    from fpa.gold.build import connect, export
    from fpa.gold.controls import run_controls
    from fpa.silver.build import build

    silver = tmp_path_factory.mktemp("silver")
    gold = tmp_path_factory.mktemp("gold")
    build(out=silver)
    con = connect(silver)
    export(con, gold)
    return {"con": con, "controls": run_controls(silver, gold), "silver": silver}


def test_controls_have_no_unexplained_gap(pipeline):
    issues = pipeline["controls"].query("status != 'OK'")
    unexplained = issues[~((issues["control"] == "C4") & (issues["scope"] == "FY2017"))]
    assert unexplained.empty, unexplained.to_string()


def test_every_period_has_a_full_pnl(pipeline):
    missing = (
        pipeline["con"]
        .execute(
            "SELECT period_key FROM kpi_quarterly WHERE revenue IS NULL OR cogs IS NULL OR operating_income IS NULL"
        )
        .fetchall()
    )
    assert missing == []


def test_fy2022_margin_collapse_is_visible(pipeline):
    rates = dict(
        pipeline["con"]
        .execute("SELECT fiscal_year, operating_margin_rate FROM kpi_annual WHERE fiscal_year IN (2021, 2022)")
        .fetchall()
    )
    assert rates[2021] == pytest.approx(8946 / 106005)
    assert rates[2022] == pytest.approx(3848 / 109120)


def test_53_week_years(pipeline):
    weeks = dict(pipeline["con"].execute("SELECT fiscal_year, weeks FROM kpi_annual").fetchall())
    assert weeks[2017] == 53 and weeks[2023] == 53 and weeks[2022] == 52
