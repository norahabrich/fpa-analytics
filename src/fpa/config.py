"""Paramètres communs du projet."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
BRONZE_DIR = DATA_DIR / "bronze"
REFERENCE_DIR = DATA_DIR / "reference"

TARGET_CIK = "0000027419"  # Target Corporation
COMPANY_NAME = "Target Corporation"
# L'exercice fiscal de Target se termine le samedi le plus proche du 31 janvier :
# « FY2022 » couvre environ février 2022 à janvier 2023.
FISCAL_YEAR_END_MONTH = 1
