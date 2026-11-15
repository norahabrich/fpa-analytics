"""Phase 4 : prévision trimestrielle, atterrissage de l'exercice en cours et scénarios de cash.

Tables ajoutées à la couche Gold :

- `forecast_scores` : précision hors échantillon de chaque modèle (MAE, WAPE, biais) par horizon ;
- `forecast_backtest` : chaque prévision de la validation chronologique et le réel correspondant ;
- `forecast_quarterly` : réel et prévision du CA sur les 4 prochains trimestres, avec intervalle à 80 % ;
- `forecast_landing` : atterrissage de l'exercice en cours (réel + prévision) contre la dernière guidance ;
- `cash_scenarios` : free cash-flow et dette nette de fin d'exercice selon les leviers ;
- `cash_proxy_check` : contrôle du modèle de cash sur les exercices passés.

Usage :
    python -m fpa.forecast.build
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from fpa.config import DATA_DIR, REFERENCE_DIR
from fpa.forecast import cash
from fpa.forecast.models import MODEL_LABELS, backtest, forecast, interval_from_backtest, scores

GOLD_DIR = DATA_DIR / "gold"
REVENUE_MODEL = "combo"  # meilleur WAPE global en validation chronologique
MARGIN_MODEL = (
    "naive_seasonal"  # l'ETS propagerait l'effet ponctuel des remboursements de droits de douane du T2 FY2026
)
HORIZON = 4


def next_keys(last_key: str, n: int) -> list[str]:
    fy, q = int(last_key[2:6]), int(last_key[-1])
    out = []
    for _ in range(n):
        fy, q = (fy + 1, 1) if q == 4 else (fy, q + 1)
        out.append(f"FY{fy}-Q{q}")
    return out


def latest_guidance(guidance: pd.DataFrame, fy: int, metric: str) -> pd.Series | None:
    g = guidance[(guidance["fiscal_year"] == f"FY{fy}") & (guidance["period"] == "FY") & (guidance["metric"] == metric)]
    return g.sort_values("issued_date").iloc[-1] if len(g) else None


def guidance_mid(row: pd.Series) -> float:
    if pd.notna(row["point"]):
        return float(row["point"])
    if pd.notna(row["low"]) and pd.notna(row["high"]):
        return (row["low"] + row["high"]) / 2
    return float(row["low"] if pd.notna(row["low"]) else row["high"])


def build(gold=GOLD_DIR) -> dict[str, pd.DataFrame]:
    kpi_q = pd.read_parquet(gold / "kpi_quarterly.parquet")
    facts = pd.read_parquet(gold / "fact_financials.parquet")
    guidance = pd.read_csv(REFERENCE_DIR / "guidance.csv")
    q = kpi_q.set_index("period_key")
    thirteen = pd.Series(13, index=q.index)

    # 1. Validation chronologique
    bt_rev = backtest(q["revenue"], q["weeks"]).assign(series="revenue")
    bt_margin = backtest(q["operating_margin_rate"], thirteen).assign(series="operating_margin_rate")
    bt = pd.concat([bt_rev, bt_margin], ignore_index=True)
    sc = pd.concat(
        [
            scores(bt, ["series", "model"]).assign(horizon="tous"),
            scores(bt, ["series", "model", "horizon"]).assign(horizon=lambda d: d["horizon"].astype(str)),
        ],
        ignore_index=True,
    )
    sc["model_label"] = sc["model"].map(MODEL_LABELS)

    # 2. Prévision des 4 prochains trimestres (tous les trimestres futurs font 13 semaines jusqu'à FY2027)
    future = next_keys(q.index[-1], HORIZON)
    weeks = [13] * HORIZON
    rev_f = forecast(q["revenue"], q["weeks"], weeks, REVENUE_MODEL)
    rev_iv = interval_from_backtest(bt_rev, REVENUE_MODEL)
    margin_f = forecast(q["operating_margin_rate"], thirteen, weeks, MARGIN_MODEL)
    m_err = bt_margin[bt_margin["model"] == MARGIN_MODEL].assign(err=lambda d: d["actual"] - d["forecast"])
    m_iv = m_err.groupby("horizon")["err"].quantile([0.1, 0.9]).unstack()

    rows = [
        {"period_key": k, "series": s, "kind": "réel", "value": q.loc[k, s], "low": np.nan, "high": np.nan}
        for k in q.index
        for s in ("revenue", "operating_margin_rate")
    ]
    for i, k in enumerate(future, start=1):
        rows.append(
            {
                "period_key": k,
                "series": "revenue",
                "kind": "prévision",
                "value": rev_f[i - 1],
                "low": rev_f[i - 1] * (1 + rev_iv.loc[i, "rel_low"]),
                "high": rev_f[i - 1] * (1 + rev_iv.loc[i, "rel_high"]),
            }
        )
        rows.append(
            {
                "period_key": k,
                "series": "operating_margin_rate",
                "kind": "prévision",
                "value": margin_f[i - 1],
                "low": margin_f[i - 1] + m_iv.loc[i, 0.1],
                "high": margin_f[i - 1] + m_iv.loc[i, 0.9],
            }
        )
    fq = pd.DataFrame(rows).assign(
        model=lambda d: np.where(
            d["kind"] == "réel", None, np.where(d["series"] == "revenue", REVENUE_MODEL, MARGIN_MODEL)
        )
    )

    # 3. Atterrissage de l'exercice en cours
    fy = int(q.index[-1][2:6])
    done = q[q["fiscal_year"] == fy]
    rest = [k for k in future if k.startswith(f"FY{fy}")]
    fc = fq[(fq["kind"] == "prévision") & fq["period_key"].isin(rest)].pivot(
        index="period_key", columns="series", values=["value", "low", "high"]
    )
    rev_rest = fc[("value", "revenue")]
    oi_rest = rev_rest * fc[("value", "operating_margin_rate")]
    revenue = done["revenue"].sum() + rev_rest.sum()
    oi = done["operating_income"].sum() + oi_rest.sum()
    prev_revenue = q[q["fiscal_year"] == fy - 1]["revenue"].sum()

    def margin_at(rev_col: str, m_col: str) -> float:
        r = fc[(rev_col, "revenue")]
        return (done["operating_income"].sum() + (r * fc[(m_col, "operating_margin_rate")]).sum()) / (
            done["revenue"].sum() + r.sum()
        )

    landing_rows = []
    for metric, value, low, high in [
        (
            "net_sales_growth",
            (revenue / prev_revenue - 1) * 100,
            ((done["revenue"].sum() + fc[("low", "revenue")].sum()) / prev_revenue - 1) * 100,
            ((done["revenue"].sum() + fc[("high", "revenue")].sum()) / prev_revenue - 1) * 100,
        ),
        (
            "operating_margin_rate",
            oi / revenue * 100,
            margin_at("value", "low") * 100,
            margin_at("value", "high") * 100,
        ),
    ]:
        g = latest_guidance(guidance, fy, metric)
        mid = guidance_mid(g) if g is not None else np.nan
        landing_rows.append(
            {
                "fiscal_year": f"FY{fy}",
                "metric": metric,
                "quarters_actual": len(done),
                "landing": value,
                "low_80": low,
                "high_80": high,
                "guidance_issued": None if g is None else g["issued_date"],
                "guidance_mid": mid,
                "gap_vs_guidance": value - mid,
                "guidance_in_interval": bool(low <= mid <= high) if g is not None else None,
                "guidance_quote": None if g is None else g["quote_en"],
            }
        )
    landing = pd.DataFrame(landing_rows)

    # 4. Cash de fin d'exercice
    base = cash.base_hypotheses(kpi_q, facts, {"revenue": revenue, "operating_margin": oi / revenue}, fy)
    scen = cash.scenarios(base).assign(fiscal_year=f"FY{fy}", cash_per_day=cash.cash_per_day(base))
    proxy = cash.proxy_check(facts)

    tables = {
        "forecast_scores": sc,
        "forecast_backtest": bt,
        "forecast_quarterly": fq,
        "forecast_landing": landing,
        "cash_scenarios": scen,
        "cash_proxy_check": proxy,
    }
    for name, df in tables.items():
        df.to_parquet(gold / f"{name}.parquet", index=False)
        df.to_csv(gold / f"{name}.csv", index=False)
    return tables


def main() -> None:
    t = build()
    s = t["forecast_scores"]
    print(s[s["horizon"] == "tous"][["series", "model_label", "n", "mae", "wape_pct", "bias_pct"]].round(3).to_string())
    print(t["forecast_landing"].drop(columns=["guidance_quote"]).round(2).to_string())
    cols = ["scenario", "free_cash_flow", "fcf_vs_base", "net_debt_end"]
    print(t["cash_scenarios"][cols].round(0).to_string(index=False))
    print(t["cash_proxy_check"].round(1).to_string(index=False))


if __name__ == "__main__":
    main()
