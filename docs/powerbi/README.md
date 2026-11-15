# Rapport Power BI : guide de construction

Le fichier `.pbix` se construit dans **Power BI Desktop** (Windows), à partir des tables Gold du dépôt. Ce dossier contient tout ce qu'il faut pour le refaire à l'identique :

| Fichier | Rôle |
|---|---|
| [`mesures.dax`](mesures.dax) | Les mesures DAX, à copier une par une |
| [`theme-fpa.json`](theme-fpa.json) | Le thème (couleurs adaptées aux daltoniens, police, fonds) |
| `README.md` | Le modèle de données et la maquette des pages |

> Les mesures DAX ont été écrites et relues, mais **pas encore exécutées dans Power BI**. Si une mesure renvoie une erreur, vérifier d'abord le nom exact de la table et de la colonne après import.

## 1. Importer les tables

`Accueil > Obtenir les données > Texte/CSV`, puis choisir dans `data/gold/` :

| Table | Grain | Usage |
|---|---|---|
| `dim_period` | trimestre fiscal | dimension temps (clé `period_key`, ex. `FY2022-Q1`) |
| `dim_account` | compte | libellés français des comptes |
| `fact_financials` | trimestre × compte | P&L, bilan, flux en MUSD |
| `kpi_quarterly` | trimestre | marges, EBITDA, FCF, DIO, DPO, dette nette |
| `kpi_annual` | exercice | mêmes indicateurs par exercice |
| `fact_comparable_sales` | trimestre | ventes comparables, trafic, panier moyen |
| `bridge_operating_income` | période × étape | pont de résultat opérationnel |
| `guidance_vs_actual` | objectif publié | objectif, réel comparable, écart, verdict |

Dans Power Query, vérifier que les colonnes `*_rate`, `*_pct` et `value` sont en **Nombre décimal** et les dates en **Date**. Si les nombres arrivent en texte, choisir `Paramètres régionaux : Anglais (États-Unis)` dans l'étape « Type modifié » (le séparateur décimal des CSV est le point).

## 2. Modèle de données (schéma en étoile)

```
                       ┌──────────────┐
                       │  dim_account │
                       └──────┬───────┘
                              │ 1
                              │ *
┌──────────────┐ 1      * ┌───┴──────────────┐
│  dim_period  ├──────────┤  fact_financials │
│ (period_key) │          └──────────────────┘
│              │ 1      * ┌──────────────────┐
│              ├──────────┤  kpi_quarterly   │
│              │          └──────────────────┘
│              │ 1      * ┌───────────────────────┐
│              ├──────────┤ fact_comparable_sales │
└──────┬───────┘          └───────────────────────┘
       │ fiscal_year_label
       │ (via DimExercice)
┌──────┴───────┐ 1      * ┌────────────────────┐
│ DimExercice  ├──────────┤ guidance_vs_actual │
│ (FY2022...)  │ 1      * ├────────────────────┤
│              ├──────────┤ kpi_annual         │
└──────────────┘          └────────────────────┘

bridge_operating_income : sans relation (segments propres sur grain et period_key)
```

Relations à créer (`Modélisation > Gérer les relations`), toutes **un-à-plusieurs, filtre unidirectionnel** :

| De (côté 1) | Vers (côté plusieurs) |
|---|---|
| `dim_period[period_key]` | `fact_financials[period_key]` |
| `dim_period[period_key]` | `kpi_quarterly[period_key]` |
| `dim_period[period_key]` | `fact_comparable_sales[period_key]` |
| `dim_account[account]` | `fact_financials[account]` |
| `DimExercice[fiscal_year_label]` | `dim_period[fiscal_year_label]` |
| `DimExercice[fiscal_year_label]` | `guidance_vs_actual[fiscal_year]` |

`DimExercice` est une table calculée (`Modélisation > Nouvelle table`) :

```dax
DimExercice = DISTINCT ( SELECTCOLUMNS ( dim_period, "fiscal_year_label", dim_period[fiscal_year_label], "fiscal_year", dim_period[fiscal_year] ) )
```

Pour `kpi_annual`, ajouter dans Power Query une colonne `fiscal_year_label = "FY" & Text.From([fiscal_year])`, puis la relier à `DimExercice`. Marquer `dim_period` comme table de dates n'est pas utile ici : le calendrier est fiscal (exercice décalé, 53e semaine), et les comparaisons N-1 sont écrites à la main dans `mesures.dax`.

Trier `dim_period[period_key]` par `period_end` (`Outils de colonne > Trier par colonne`) pour que les axes suivent l'ordre chronologique.

## 3. Mesures et thème

1. `Accueil > Entrer des données`, nommer la table `_Mesures`, valider.
2. Pour chaque bloc de [`mesures.dax`](mesures.dax) : `Nouvelle mesure`, coller, valider. Format : `MUSD` en nombre entier avec séparateur de milliers, taux en pourcentage à 1 décimale.
3. `Affichage > Thèmes > Parcourir les thèmes` et choisir `theme-fpa.json`.

## 4. Page « Performance »

Question : *comment évoluent le chiffre d'affaires, les marges et le cash ?*

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Segment : Exercice [FY2019 … FY2026]               Segment : Trimestre    │
├──────────────┬──────────────┬──────────────┬─────────────────────────────┤
│ CA           │ Taux de      │ Taux de marge│ Free cash-flow              │
│ 109 120 MUSD │ marge brute  │ opérationnelle│ −1 510 MUSD                │
│ +2,9 % vs N-1│ 24,6 %       │ 3,5 %        │                             │
├──────────────┴──────────────┴──────────────┴─────────────────────────────┤
│ Courbes : taux de marge brute et taux de marge opérationnelle            │
│ par trimestre (axe : period_key)                                         │
├─────────────────────────────────────┬────────────────────────────────────┤
│ Histogramme : CA par trimestre      │ Courbe : stocks et DIO (jours)     │
│ (info-bulle : croissance vs N-1)    │ (deux visuels, jamais deux axes)   │
├─────────────────────────────────────┴────────────────────────────────────┤
│ Matrice P&L : lignes = dim_account[label_fr] (comptes de résultat),      │
│ colonnes = exercice, valeurs = SUM(fact_financials[value])               │
└──────────────────────────────────────────────────────────────────────────┘
```

| Visuel | Champs |
|---|---|
| 4 cartes | `[CA]`, `[Taux de marge brute]`, `[Taux de marge opérationnelle]`, `[Free cash-flow]` ; sous le CA, `[Croissance du CA]` |
| Courbes des taux | axe `dim_period[period_key]`, valeurs `[Taux de marge brute]`, `[Taux de marge opérationnelle]` |
| Histogramme CA | axe `period_key`, valeur `[CA]`, info-bulle `[CA N-1]`, `[Croissance du CA]` |
| Stocks | axe `period_key`, valeur `[Stocks]` ; un second visuel pour `[DIO (jours)]` |
| Matrice P&L | filtre `dim_account[statement] = "IS"` |

## 5. Page « Écarts »

Question : *d'où vient la baisse du résultat, et à quel point l'année s'est-elle écartée des objectifs ?*

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Segment : grain [annual | quarterly]     Segment : période [FY2022 …]    │
├──────────────────────────────────────────┬───────────────────────────────┤
│ Cascade : pont de résultat opérationnel  │ Tableau réel vs objectif      │
│ EBIT N-1 → trafic → panier → autres →    │ date | indicateur | objectif  │
│ taux de marge brute → SG&A → amort.      │ | réel | écart | verdict      │
│ → EBIT N (total calculé par Power BI)    │ (mise en forme sur verdict)   │
├──────────────────────────────────────────┴───────────────────────────────┤
│ Histogramme groupé : trafic et panier moyen par trimestre                │
│ + marqueur ventes comparables                                            │
└──────────────────────────────────────────────────────────────────────────┘
```

| Visuel | Champs |
|---|---|
| Cascade | catégorie `bridge_operating_income[label_fr]` (triée par `step_order`), valeur `[Effet sur l'EBIT]`, filtre `step` différent de `end` : le visuel calcule lui-même le total final. Segments sur `grain` et `period_key` de la même table. |
| Tableau objectifs | `issued_date`, `period`, `metric`, `guidance_low`, `guidance_high`, `actual`, `variance_vs_mid`, `verdict` ; segment `DimExercice` |
| Ventes comparables | axe `period_key`, valeurs `[Trafic]`, `[Panier moyen]` ; courbe `[Ventes comparables]` |

Le verdict est en texte (« sous l'objectif », « dans la fourchette », « au-dessus de l'objectif ») : la couleur n'est jamais le seul moyen de le lire.

## 6. Pages « Forecast » et « Cash » (phase 4)

Importer aussi `forecast_quarterly`, `forecast_scores`, `forecast_landing` et `cash_scenarios`. Relier `forecast_quarterly[period_key]` à `dim_period[period_key]` : les trimestres prévus (FY2026-Q3 et suivants) n'existent pas dans `dim_period`, donc pour cette page utiliser directement `forecast_quarterly[period_key]` en axe, sans relation.

| Page | Visuels |
|---|---|
| Forecast | courbe `value` par `period_key`, légende `kind` (réel / prévision), bande `low`–`high` (courbe d'erreur) ; filtre `series = "revenue"` ; tableau `forecast_landing` (atterrissage, intervalle, guidance, écart) ; courbes `wape_pct` par `horizon` et `model_label` depuis `forecast_scores` |
| Cash | barres horizontales `free_cash_flow` par `scenario` ; cartes `net_debt_end` et `cash_per_day` pour le scénario « Base » |
