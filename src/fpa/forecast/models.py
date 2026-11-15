"""Modèles de prévision trimestrielle et validation chronologique.

Cinq modèles, de la plus simple à la plus riche :

- `naive_seasonal` : même trimestre de l'an dernier (référence à battre) ;
- `naive_seasonal_growth` : même trimestre de l'an dernier × croissance des 4 derniers trimestres ;
- `ets` : lissage exponentiel de Holt-Winters (tendance amortie, saisonnalité multiplicative) ;
- `sarima` : SARIMA(0,1,1)(0,1,1)₄ sur le logarithme (« modèle airline ») ;
- `combo` : moyenne de la référence saisonnière et de l'ETS.

Le chiffre d'affaires est d'abord ramené à 13 semaines : les trimestres de 14 semaines
(T4 des exercices de 53 semaines) sont multipliés par 13/14, puis la prévision est remise
à la durée réelle du trimestre prévu.

Validation chronologique (« rolling origin ») : à chaque date d'origine, on entraîne le
modèle sur le passé seulement et on prévoit les 1 à 4 trimestres suivants. On compare
ensuite prévision et réel avec :

    MAE  = moyenne des |réel − prévision|                 (en MUSD)
    WAPE = Σ |réel − prévision| / Σ |réel|                (en %, comparable entre séries)
    biais = Σ (prévision − réel) / Σ |réel|               (> 0 : on surestime)
"""

from __future__ import annotations

import warnings
from collections.abc import Callable

import numpy as np
import pandas as pd

SEASON = 4


def naive_seasonal(y: np.ndarray, h: int) -> np.ndarray:
    return np.array([y[len(y) - SEASON + (i % SEASON)] for i in range(h)])


def naive_seasonal_growth(y: np.ndarray, h: int) -> np.ndarray:
    growth = y[-SEASON:].sum() / y[-2 * SEASON : -SEASON].sum()
    return np.array([y[len(y) - SEASON + (i % SEASON)] * growth ** (1 + i // SEASON) for i in range(h)])


def ets(y: np.ndarray, h: int) -> np.ndarray:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = ExponentialSmoothing(
            y,
            trend="add",
            damped_trend=True,
            seasonal="mul",
            seasonal_periods=SEASON,
            initialization_method="estimated",
        ).fit()
    return np.asarray(fit.forecast(h))


def sarima(y: np.ndarray, h: int) -> np.ndarray:
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = SARIMAX(np.log(y), order=(0, 1, 1), seasonal_order=(0, 1, 1, SEASON)).fit(disp=False)
    return np.exp(np.asarray(fit.forecast(h)))


def combo(y: np.ndarray, h: int) -> np.ndarray:
    """Moyenne simple de la référence saisonnière et de l'ETS (combinaison de prévisions)."""
    return (naive_seasonal(y, h) + ets(y, h)) / 2


MODELS: dict[str, Callable[[np.ndarray, int], np.ndarray]] = {
    "naive_seasonal": naive_seasonal,
    "naive_seasonal_growth": naive_seasonal_growth,
    "ets": ets,
    "sarima": sarima,
    "combo": combo,
}
MODEL_LABELS = {
    "naive_seasonal": "Référence saisonnière (N-1)",
    "naive_seasonal_growth": "N-1 × croissance récente",
    "ets": "ETS (Holt-Winters)",
    "sarima": "SARIMA (0,1,1)(0,1,1)₄",
    "combo": "Moyenne référence + ETS",
}


def to_13_weeks(values: pd.Series, weeks: pd.Series) -> pd.Series:
    return values * 13 / weeks


def backtest(
    y: pd.Series,
    weeks: pd.Series,
    models: dict[str, Callable] = MODELS,
    min_train: int = 20,
    horizon: int = 4,
    first_origin: int | None = None,
) -> pd.DataFrame:
    """Prévisions hors échantillon, une ligne par (modèle, origine, horizon).

    `y` et `weeks` sont indexés par period_key, dans l'ordre chronologique.
    """
    y13 = to_13_weeks(y, weeks).to_numpy(dtype=float)
    keys = list(y.index)
    start = first_origin if first_origin is not None else min_train
    rows = []
    for origin in range(start, len(y13)):
        train = y13[:origin]
        h = min(horizon, len(y13) - origin)
        for name, model in models.items():
            pred = model(train, h)
            for i in range(h):
                t = origin + i
                rows.append(
                    {
                        "model": name,
                        "origin": keys[origin - 1],
                        "period_key": keys[t],
                        "horizon": i + 1,
                        "actual": float(y.iloc[t]),
                        "forecast": float(pred[i] * weeks.iloc[t] / 13),
                    }
                )
    return pd.DataFrame(rows)


def scores(bt: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    by = by or ["model"]
    err = bt.assign(abs_err=(bt["forecast"] - bt["actual"]).abs(), err=bt["forecast"] - bt["actual"])
    g = err.groupby(by)
    out = pd.DataFrame(
        {
            "n": g.size(),
            "mae": g["abs_err"].mean(),
            "wape_pct": g["abs_err"].sum() / g["actual"].apply(lambda s: s.abs().sum()) * 100,
            "bias_pct": g["err"].sum() / g["actual"].apply(lambda s: s.abs().sum()) * 100,
        }
    )
    return out.reset_index()


def interval_from_backtest(bt: pd.DataFrame, model: str, level: float = 0.8) -> pd.DataFrame:
    """Intervalle empirique : quantiles de l'erreur relative (réel / prévision − 1) par horizon."""
    b = bt[bt["model"] == model].assign(rel=lambda d: d["actual"] / d["forecast"] - 1)
    lo, hi = (1 - level) / 2, 1 - (1 - level) / 2
    return b.groupby("horizon")["rel"].quantile([lo, hi]).unstack().rename(columns={lo: "rel_low", hi: "rel_high"})


def forecast(y: pd.Series, weeks: pd.Series, future_weeks: list[int], model: str) -> np.ndarray:
    """Prévision des trimestres suivants avec tout l'historique."""
    y13 = to_13_weeks(y, weeks).to_numpy(dtype=float)
    pred = MODELS[model](y13, len(future_weeks))
    return pred * np.array(future_weeks) / 13
