"""Construit la couche Gold (modèle en étoile) avec DuckDB et l'exporte pour Power BI.

Tables produites dans `data/gold/` (Parquet et CSV) :
- `dim_period`, `dim_account` : dimensions ;
- `fact_financials` : une valeur par (trimestre, compte), en MUSD, avec la méthode d'obtention ;
- `fact_guidance` : objectifs de la direction ;
- `kpi_quarterly`, `kpi_annual` : indicateurs réconciliés (marges, EBITDA, BFR, free cash-flow).

Usage :
    python -m fpa.silver.build && python -m fpa.gold.build
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from fpa.config import DATA_DIR, REFERENCE_DIR

SQL_DIR = Path(__file__).parent / "sql"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"
TABLES = ["dim_period", "dim_account", "fact_financials", "fact_guidance", "kpi_quarterly", "kpi_annual"]


def connect(silver: Path = SILVER_DIR) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    for view, name in [("silver_quarterly", "financials_quarterly"), ("silver_annual", "financials_annual")]:
        con.execute(f"CREATE VIEW {view} AS SELECT * FROM read_parquet('{silver / (name + '.parquet')}')")
    con.execute(f"CREATE VIEW account_mapping AS SELECT * FROM read_csv('{REFERENCE_DIR / 'account_mapping.csv'}')")
    con.execute(f"CREATE VIEW guidance AS SELECT * FROM read_csv('{REFERENCE_DIR / 'guidance.csv'}')")
    for script in sorted(SQL_DIR.glob("*.sql")):
        con.execute(script.read_text(encoding="utf-8"))
    return con


def export(con: duckdb.DuckDBPyConnection, out: Path = GOLD_DIR) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for table in TABLES:
        con.execute(f"COPY {table} TO '{out / (table + '.parquet')}' (FORMAT parquet)")
        con.execute(f"COPY {table} TO '{out / (table + '.csv')}' (HEADER, DELIMITER ',')")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Construit la couche Gold.")
    parser.add_argument("--out", type=Path, default=GOLD_DIR)
    args = parser.parse_args(argv)
    con = connect()
    export(con, args.out)
    for table in TABLES:
        n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        print(f"{table:16s} {n:5d} lignes")


if __name__ == "__main__":
    main()
