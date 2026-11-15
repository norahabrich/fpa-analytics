"""Tests de la phase 4 : modèles de prévision, validation chronologique, modèle de cash."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from fpa.config import DATA_DIR, PROJECT_ROOT
from fpa.forecast import cash
from fpa.forecast.build import next_keys
from fpa.forecast.models import MODELS, backtest, naive_seasonal, naive_seasonal_growth, scores, to_13_weeks

GOLD = DATA_DIR / "gold"


def seasonal_series(n=24, growth=0.0):
    pattern = np.array([100.0, 105.0, 110.0, 140.0])
    return np.array([pattern[i % 4] * (1 + growth) ** (i // 4) for i in range(n)])


# ---------- Modèles ----------


def test_naive_seasonal_repeats_last_year():
    y = seasonal_series(8)
    assert list(naive_seasonal(y, 6)) == [100, 105, 110, 140, 100, 105]


def test_naive_seasonal_growth_compounds_by_year():
    y = seasonal_series(12, growth=0.10)
    pred = naive_seasonal_growth(y, 8)
    assert pred[:4] == pytest.approx(y[-4:] * 1.10)
    assert pred[4:] == pytest.approx(y[-4:] * 1.10**2)


@pytest.mark.parametrize("name", list(MODELS))
def test_every_model_fits_a_clean_seasonal_series(name):
    y = seasonal_series(28, growth=0.03)
    truth = seasonal_series(32, growth=0.03)[-4:]
    pred = MODELS[name](y, 4)
    assert pred.shape == (4,)
    assert np.abs(pred / truth - 1).max() < 0.05


def test_53_week_quarter_is_normalised():
    assert to_13_weeks(pd.Series([140.0]), pd.Series([14])).iloc[0] == pytest.approx(130.0)


def test_backtest_never_uses_the_future():
    y = pd.Series(seasonal_series(24), index=[f"P{i:02d}" for i in range(24)])
    seen = []

    def spy(train, h):
        seen.append(len(train))
        return np.repeat(train[-1], h)

    bt = backtest(y, pd.Series(13, index=y.index), models={"spy": spy}, min_train=20)
    assert seen == [20, 21, 22, 23]
    # la prévision faite à l'origine P19 pour P20 n'a vu que P00..P19
    first = bt[(bt["origin"] == "P19") & (bt["horizon"] == 1)].iloc[0]
    assert first["period_key"] == "P20" and first["forecast"] == y["P19"]


def test_scores_wape_and_bias():
    bt = pd.DataFrame({"model": ["m"] * 2, "actual": [100.0, 100.0], "forecast": [110.0, 100.0]})
    s = scores(bt).iloc[0]
    assert s["mae"] == 5 and s["wape_pct"] == pytest.approx(5) and s["bias_pct"] == pytest.approx(5)


def test_next_keys_rolls_over_fiscal_year():
    assert next_keys("FY2026-Q2", 4) == ["FY2026-Q3", "FY2026-Q4", "FY2027-Q1", "FY2027-Q2"]


# ---------- Modèle de cash ----------

BASE = cash.Hypotheses(
    revenue=100_000,
    operating_margin=0.05,
    gross_margin=0.28,
    da_rate=0.03,
    interest=400,
    tax_rate=0.22,
    q4_cogs_share=0.30,
    dio_end=50,
    dpo_end=50,
    capex=3_500,
    dividends=2_000,
    buybacks=500,
    inventory_start=12_000,
    payables_start=12_000,
    net_debt_start=11_000,
)


def test_cash_projection_identities():
    r = cash.project(BASE)
    assert r["operating_income"] == pytest.approx(5_000)
    assert r["net_income"] == pytest.approx((5_000 - 400) * 0.78)
    assert r["free_cash_flow"] == pytest.approx(r["cfo"] - 3_500)
    assert r["net_debt_end"] == pytest.approx(11_000 - (r["free_cash_flow"] - 2_500))


def test_one_day_of_inventory_is_worth_cash_per_day():
    day = cash.cash_per_day(BASE)
    assert day == pytest.approx(100_000 * 0.72 * 0.30 / 91)
    gain = cash.project(replace(BASE, dio_end=49))["free_cash_flow"] - cash.project(BASE)["free_cash_flow"]
    assert gain == pytest.approx(day)
    # Un jour fournisseur de plus libère autant qu'un jour de stock de moins
    gain_dpo = cash.project(replace(BASE, dpo_end=51))["free_cash_flow"] - cash.project(BASE)["free_cash_flow"]
    assert gain_dpo == pytest.approx(day)


def test_scenarios_table():
    s = cash.scenarios(BASE).set_index("scenario")
    assert s.loc["Base", "fcf_vs_base"] == 0
    assert s.loc["Capex : +1 Md$", "fcf_vs_base"] == pytest.approx(-1_000)
    assert s.filter(like="Choc", axis=0)["fcf_vs_base"].iloc[0] < s.loc["Stocks : +5 jours (DIO)", "fcf_vs_base"]


# ---------- Tables Gold ----------


def test_cash_proxy_tracks_reported_cash_flow():
    p = pd.read_parquet(GOLD / "cash_proxy_check.parquet")
    assert len(p) >= 8
    assert (p["gap_pct_revenue"].abs() <= 3).all()
    assert (p["gap_pct_revenue"].abs() <= 0.75).mean() >= 0.75


def test_combination_beats_the_seasonal_benchmark_on_revenue():
    s = pd.read_parquet(GOLD / "forecast_scores.parquet")
    s = s[(s["series"] == "revenue") & (s["horizon"] == "tous")].set_index("model")
    assert (s["n"] == 66).all()
    assert s.loc["combo", "wape_pct"] < s.loc["naive_seasonal", "wape_pct"] < 4


def test_landing_is_consistent():
    land = pd.read_parquet(GOLD / "forecast_landing.parquet").set_index("metric")
    for _, r in land.iterrows():
        assert r["low_80"] <= r["landing"] <= r["high_80"]
    assert land.loc["net_sales_growth", "quarters_actual"] == 2


def test_streamlit_app_runs():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(PROJECT_ROOT / "app" / "simulateur.py"), default_timeout=60).run()
    assert not at.exception
    assert [m.label for m in at.metric][2] == "Free cash-flow"
