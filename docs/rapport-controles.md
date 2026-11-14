# Rapport de contrôles : couche Gold

Généré le 2026-11-14 par `python -m fpa.gold.controls`. Périmètre : FY2017 à FY2026, 25 comptes.

| Contrôle | Objet | OK | Écarts | Manquants |
|---|---|---:|---:|---:|
| C1 | Bilan équilibré | 38 | 0 | 0 |
| C2 | Identité du P&L | 32 | 0 | 0 |
| C3 | Σ trimestres = exercice | 72 | 0 | 0 |
| C4 | T1+T2+T3 = cumul 9 mois | 63 | 1 | 0 |
| C5 | Complétude | 1 | 0 | 0 |
| C6 | Rapprochement communiqués | 17 | 0 | 0 |
| C7 | Plausibilité | 1 | 0 | 0 |

## Écarts et manquants

| Contrôle | Période | Compte | Attendu | Obtenu | Écart | Commentaire |
|---|---|---|---:|---:|---:|---|
| C4 | FY2017 | operating_income | 3,160.0 | 3,095.0 | -65.0 | trimestres retraités dans un dépôt ultérieur, cumul 9 mois jamais republié |

**Lecture des écarts C4.** Le 10-K de mars 2019 a retraité les trimestres de FY2017 (adoption de la norme de reconnaissance du revenu ASC 606, qui reclasse certains produits et charges). Le cumul 9 mois de FY2017, lui, n'a jamais été republié : il reste sur l'ancienne base. L'écart est donc attendu. Les trimestres retenus sont ceux retraités, cohérents avec l'exercice FY2017 publié (contrôle C3 au vert).

## Origine des valeurs trimestrielles

| Méthode | Lignes | Sens |
|---|---:|---|
| reported | 748 | publiée telle quelle pour le trimestre |
| derived_ytd | 95 | cumul moins cumul précédent (ex. T3 = 9 mois − 6 mois) |
| derived_fy | 86 | T4 = exercice − 9 mois |
| derived_identity | 6 | coût des ventes non balisé, déduit de l'identité du P&L |

## Retraitements repérés

115 périodes ont une valeur différente entre le premier dépôt et le dernier. La couche Silver garde la dernière version. Les plus fréquents :

| Concept XBRL | Périodes retraitées |
|---|---:|
| `CostOfGoodsAndServicesSold` | 15 |
| `SellingGeneralAndAdministrativeExpense` | 15 |
| `DepreciationAndAmortization` | 8 |
| `NetIncomeLossAvailableToCommonStockholdersBasic` | 8 |
| `IncomeTaxExpenseBenefit` | 8 |
| `InterestExpense` | 8 |
| `PaymentsForRepurchaseOfCommonStock` | 6 |
| `LiabilitiesCurrent` | 6 |
