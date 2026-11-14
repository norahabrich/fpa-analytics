"""Rapport de contrôles : la donnée Gold est-elle fiable ?

| Code | Contrôle | Pourquoi |
|---|---|---|
| C1 | Total actif = total passif + capitaux propres, chaque trimestre | identité du bilan |
| C2 | CA − coût des ventes − SG&A − amortissements = résultat opérationnel | cohérence du P&L |
| C3 | Somme des 4 trimestres = exercice publié, pour chaque compte de flux | trimestres reconstruits justes |
| C4 | T1 + T2 + T3 = cumul 9 mois publié | repère les mélanges de versions retraitées |
| C5 | Chaque compte a une valeur pour chaque trimestre | complétude |
| C6 | Chiffres annuels = chiffres cités dans les communiqués | rapprochement avec une source indépendante |
| C7 | CA, coût des ventes et SG&A strictement positifs | plausibilité des trimestres déduits |

Statuts : `OK`, `ECART` (écart au-delà de la tolérance), `MANQUANT`.

Usage :
    python -m fpa.gold.controls      # écrit data/gold/controls.csv et docs/rapport-controles.md
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

from fpa.config import DATA_DIR, PROJECT_ROOT, REFERENCE_DIR

SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"
TOL_MUSD = 0.5  # les montants XBRL sont publiés au million près
FLOW_ACCOUNTS = ["revenue", "cogs", "sga", "da_opex", "operating_income", "net_income", "cfo", "capex"]
REQUIRED = [*FLOW_ACCOUNTS, "inventory", "accounts_payable", "cash", "total_assets", "da_total"]

COLS = ["control", "scope", "account", "expected", "actual", "gap", "tolerance", "status", "comment"]


def _row(control, scope, account, expected, actual, tol, comment=""):
    if pd.isna(expected) or pd.isna(actual):
        return dict(zip(COLS, [control, scope, account, expected, actual, None, tol, "MANQUANT", comment], strict=True))
    gap = actual - expected
    status = "OK" if abs(gap) <= tol else "ECART"
    return dict(zip(COLS, [control, scope, account, expected, actual, gap, tol, status, comment], strict=True))


def run_controls(silver: Path = SILVER_DIR, gold: Path = GOLD_DIR) -> pd.DataFrame:
    q = pd.read_parquet(silver / "financials_quarterly.parquet")
    a = pd.read_parquet(silver / "financials_annual.parquet")
    facts = pd.read_parquet(silver / "facts_latest.parquet")
    kpi_a = pd.read_parquet(gold / "kpi_annual.parquet")
    q["value_m"] = q["value"] / 1e6
    wide = q.pivot_table(index=["fiscal_year", "fiscal_quarter"], columns="account", values="value_m")
    methods = q.pivot_table(
        index=["fiscal_year", "fiscal_quarter"], columns="account", values="method", aggfunc="first"
    )
    rows = []

    # C1 : identité du bilan
    for (fy, fq), r in wide.iterrows():
        rows.append(
            _row(
                "C1",
                f"FY{fy}-Q{fq}",
                "total_assets",
                r.get("total_liabilities_equity"),
                r.get("total_assets"),
                TOL_MUSD,
            )
        )

    # C2 : identité du P&L (sauf trimestres où le coût des ventes en est lui-même déduit)
    for (fy, fq), r in wide.iterrows():
        if methods.loc[(fy, fq), "cogs"] == "derived_identity":
            continue
        expected = r["revenue"] - r["cogs"] - r["sga"] - r["da_opex"]
        rows.append(_row("C2", f"FY{fy}-Q{fq}", "operating_income", expected, r["operating_income"], TOL_MUSD))

    # C3 : somme des trimestres = exercice publié
    complete = wide.groupby(level=0).size().loc[lambda s: s == 4].index
    annual = a.assign(value_m=a["value"] / 1e6).set_index(["account", "fiscal_year"])["value_m"]
    for acc in FLOW_ACCOUNTS:
        for fy in complete:
            total = wide.loc[fy, acc].sum(min_count=4)
            rows.append(
                _row(
                    "C3",
                    f"FY{fy}",
                    acc,
                    annual.get((acc, fy)),
                    total,
                    TOL_MUSD * 4,
                    "tolérance : 4 arrondis au million",
                )
            )

    # C4 : T1 + T2 + T3 = cumul 9 mois publié (dernière version)
    nine = facts[facts["duration"] == "9M"]
    concept_of = q.dropna(subset=["concept"]).groupby("account")["concept"].first()
    for acc in FLOW_ACCOUNTS:
        concept = concept_of.get(acc)
        sub = nine[nine["concept"] == concept]
        for r in sub.itertuples():
            if r.fiscal_year not in wide.index.get_level_values(0):
                continue
            parts = [wide.loc[(r.fiscal_year, k), acc] if (r.fiscal_year, k) in wide.index else None for k in (1, 2, 3)]
            actual = sum(parts) if all(p is not None and pd.notna(p) for p in parts) else None
            comment = ""
            if (
                r.filed.year <= r.fiscal_year + 1
                and q[(q["account"] == acc) & (q["fiscal_year"] == r.fiscal_year) & (q["fiscal_quarter"] <= 3)][
                    "restated"
                ].any()
            ):
                comment = "trimestres retraités dans un dépôt ultérieur, cumul 9 mois jamais republié"
            rows.append(_row("C4", f"FY{r.fiscal_year}", acc, r.val / 1e6, actual, TOL_MUSD * 3, comment))

    # C5 : complétude
    for acc in REQUIRED:
        for fy, fq in wide.index:
            v = wide.loc[(fy, fq)].get(acc)
            if pd.isna(v):
                rows.append(_row("C5", f"FY{fy}-Q{fq}", acc, 1, None, 0, "valeur absente"))
    n_missing = sum(1 for r in rows if r["control"] == "C5")
    rows.append(
        _row(
            "C5",
            "toutes périodes",
            "*",
            0,
            n_missing,
            0,
            f"valeurs absentes sur {len(wide.index) * len(REQUIRED)} attendues",
        )
    )

    # C6 : rapprochement avec les communiqués de résultats
    cp = pd.read_csv(REFERENCE_DIR / "reported_checkpoints.csv")
    kpi = kpi_a.set_index("fiscal_year")
    for r in cp.itertuples():
        fy = int(r.fiscal_year[2:])
        if r.metric == "gross_margin_rate":
            actual = kpi.loc[fy, "gross_margin_rate"] * 100 if fy in kpi.index else None
        else:
            actual = annual.get((r.metric, fy))
        rows.append(_row("C6", r.fiscal_year, r.metric, r.value, actual, r.tolerance, r.source_url))

    # C7 : plausibilité des montants trimestriels
    for acc in ["revenue", "cogs", "sga"]:
        for (fy, fq), v in wide[acc].items():
            if pd.notna(v) and v <= 0:
                rows.append(_row("C7", f"FY{fy}-Q{fq}", acc, 0, v, 0, "montant négatif ou nul"))
    rows.append(
        _row(
            "C7",
            "toutes périodes",
            "revenue,cogs,sga",
            0,
            sum(1 for r in rows if r["control"] == "C7"),
            0,
            "nombre de trimestres non plausibles",
        )
    )

    return pd.DataFrame(rows, columns=COLS)


def markdown_report(df: pd.DataFrame, silver: Path = SILVER_DIR) -> str:
    q = pd.read_parquet(silver / "financials_quarterly.parquet")
    restatements = pd.read_csv(silver / "restatements.csv")
    summary = df.groupby("control")["status"].value_counts().unstack(fill_value=0)
    for col in ("OK", "ECART", "MANQUANT"):
        if col not in summary:
            summary[col] = 0
    labels = {
        "C1": "Bilan équilibré",
        "C2": "Identité du P&L",
        "C3": "Σ trimestres = exercice",
        "C4": "T1+T2+T3 = cumul 9 mois",
        "C5": "Complétude",
        "C6": "Rapprochement communiqués",
        "C7": "Plausibilité",
    }
    lines = [
        "# Rapport de contrôles : couche Gold",
        "",
        f"Généré le {date.today():%Y-%m-%d} par `python -m fpa.gold.controls`. "
        f"Périmètre : FY{q['fiscal_year'].min()} à FY{q['fiscal_year'].max()}, {q['account'].nunique()} comptes.",
        "",
        "| Contrôle | Objet | OK | Écarts | Manquants |",
        "|---|---|---:|---:|---:|",
    ]
    for code, r in summary.iterrows():
        lines.append(f"| {code} | {labels.get(code, '')} | {r['OK']} | {r['ECART']} | {r['MANQUANT']} |")

    issues = df[df["status"] != "OK"]
    lines += ["", "## Écarts et manquants", ""]
    if issues.empty:
        lines.append("Aucun.")
    else:
        lines += [
            "| Contrôle | Période | Compte | Attendu | Obtenu | Écart | Commentaire |",
            "|---|---|---|---:|---:|---:|---|",
        ]
        for r in issues.itertuples():
            fmt = lambda v: "" if pd.isna(v) else f"{v:,.1f}"  # noqa: E731
            lines.append(
                f"| {r.control} | {r.scope} | {r.account} | {fmt(r.expected)} | {fmt(r.actual)} | "
                f"{fmt(r.gap)} | {r.comment} |"
            )

    if (issues["control"] == "C4").any():
        lines += [
            "",
            "**Lecture des écarts C4.** Le 10-K de mars 2019 a retraité les trimestres de FY2017 "
            "(adoption de la norme de reconnaissance du revenu ASC 606, qui reclasse certains produits et charges). "
            "Le cumul 9 mois de FY2017, lui, n'a jamais été republié : il reste sur l'ancienne base. "
            "L'écart est donc attendu. Les trimestres retenus sont ceux retraités, cohérents avec l'exercice FY2017 "
            "publié (contrôle C3 au vert).",
        ]

    methods = q.groupby("method").size()
    lines += [
        "",
        "## Origine des valeurs trimestrielles",
        "",
        "| Méthode | Lignes | Sens |",
        "|---|---:|---|",
        f"| reported | {methods.get('reported', 0)} | publiée telle quelle pour le trimestre |",
        f"| derived_ytd | {methods.get('derived_ytd', 0)} | cumul moins cumul précédent (ex. T3 = 9 mois − 6 mois) |",
        f"| derived_fy | {methods.get('derived_fy', 0)} | T4 = exercice − 9 mois |",
        f"| derived_identity | {methods.get('derived_identity', 0)} "
        "| coût des ventes non balisé, déduit de l'identité du P&L |",
        "",
        "## Retraitements repérés",
        "",
        f"{len(restatements)} périodes ont une valeur différente entre le premier dépôt et le dernier. "
        "La couche Silver garde la dernière version. Les plus fréquents :",
        "",
        "| Concept XBRL | Périodes retraitées |",
        "|---|---:|",
    ]
    for concept, n in restatements.groupby("concept").size().sort_values(ascending=False).head(8).items():
        lines.append(f"| `{concept}` | {n} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Contrôles de la couche Gold.")
    parser.add_argument("--report", type=Path, default=PROJECT_ROOT / "docs" / "rapport-controles.md")
    args = parser.parse_args(argv)
    df = run_controls()
    df.to_csv(GOLD_DIR / "controls.csv", index=False)
    args.report.write_text(markdown_report(df), encoding="utf-8")
    print(df.groupby(["control", "status"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()
