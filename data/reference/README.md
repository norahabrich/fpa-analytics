# Référentiels

## `guidance.csv` : objectifs publiés par la direction de Target

Ce fichier remplace le budget interne, auquel on n'a pas accès : ce sont les objectifs que Target annonce dans ses communiqués de résultats trimestriels.

| Colonne | Sens |
|---|---|
| `issued_date` | Date de dépôt du communiqué à la SEC |
| `fiscal_year` | Exercice visé (FY2022 = février 2022 à janvier 2023) |
| `period` | `FY` exercice, `Q1`–`Q4` trimestre, `H2` second semestre |
| `metric` | `comparable_sales_growth`, `revenue_growth`, `net_sales_growth`, `operating_margin_rate`, `operating_income_change`, `eps_adjusted` |
| `low` / `high` | Bornes de la fourchette annoncée (une seule borne = plancher ou plafond) |
| `point` | Valeur centrale quand la direction annonce « autour de » |
| `unit` | `pct`, `usd_per_share`, `usd_millions` |
| `quote_en` | Citation exacte du communiqué (`...` sépare deux passages) |
| `source_url` | Lien vers le communiqué sur sec.gov |
| `note` | Révision, maintien, retraitement, ou conversion d'une fourchette qualitative |

### Conversion des fourchettes qualitatives

Target annonce souvent des fourchettes en mots. On les convertit avec la convention usuelle des analystes, signalée par la note « fourchette qualitative convertie » :

| Expression | Fourchette retenue |
|---|---|
| low-single digit | 1 à 3 % |
| mid-single digit | 4 à 6 % (point central 5 %) |
| high-single digit | 7 à 9 % |
| low-double digit | 10 à 12 % |
| low- to mid-single digit | 1 à 6 % |
| low-single digit decline to low-single digit increase | −3 à +3 % |

### Contrôle automatique

`tests/test_guidance.py` vérifie que chaque citation figure mot pour mot dans le communiqué archivé sous `data/bronze/sec/earnings_releases/`, que chaque ligne a une valeur, et que les bornes sont cohérentes.

### Trous connus

- FY2020 : guidance retirée à cause du Covid, et pas de guidance de CA ni de BPA pour FY2021 en mars 2021.
- Les communiqués ne donnent pas toujours un objectif de marge opérationnelle (par exemple FY2023 à FY2025, où l'objectif porte surtout sur le BPA).
