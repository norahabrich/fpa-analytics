# Phase 2 : fiabilisation (Silver et Gold)

## Résultat

38 trimestres fiscaux (FY2017-T1 à FY2026-T2) et 9 exercices complets, pour 25 comptes du compte de résultat, du bilan et du tableau de flux. Sur 225 contrôles, un seul écart, expliqué ([rapport](rapport-controles.md)).

## Silver : de 543 concepts XBRL à 25 comptes

1. **Sélection.** `data/reference/account_mapping.csv` associe chaque compte de gestion à une liste ordonnée de concepts XBRL. Exemple : `net_income` = `NetIncomeLoss`, sinon `NetIncomeLossAvailableToCommonStockholdersBasic` (le libellé utilisé jusqu'en 2018).
2. **Dernière version.** Une période publiée plusieurs fois (10-Q d'origine, comparatif de l'année suivante, 10-K retraité) garde sa dernière valeur déposée. Les écarts sont listés dans `data/silver/restatements.csv`.
3. **Calendrier fiscal.** Chaque période est rattachée à son exercice et à son trimestre fiscaux à partir de sa date de clôture. Les exercices FY2017 et FY2023 comptent 53 semaines.
4. **Trimestres.** Pour un flux : valeur publiée du trimestre, sinon cumul moins cumul précédent, sinon exercice moins 9 mois. Pour le bilan : solde à la clôture. Le BPA n'est jamais additionné.

## Gold : modèle en étoile

```
                 dim_period ──┐
                              ├── fact_financials ── kpi_quarterly ── kpi_annual
                 dim_account ─┘
                 dim_period ───── fact_guidance
```

Les indicateurs sont calculés en SQL (`src/fpa/gold/sql/`) :

| Indicateur | Formule |
|---|---|
| Marge brute | CA − coût des ventes |
| EBITDA | résultat opérationnel + amortissements totaux (tableau de flux) |
| Free cash-flow | flux opérationnels − capex |
| DIO | stocks / coût des ventes du trimestre × nombre de jours |
| DPO | dettes fournisseurs / coût des ventes du trimestre × nombre de jours |
| Dette nette | dette financière (court + long terme, y compris locations-financement) − trésorerie |

## Points d'attention pour l'analyse

- **Taux de marge brute.** Jusqu'au T4 2024, Target calculait ce taux sur les seules ventes de marchandises. Notre taux est calculé sur le CA total, comme Target depuis le T4 2024 : il peut différer des taux publiés avant cette date.
- **Semaine supplémentaire.** Le T4 FY2023 dure 98 jours. Les comparaisons avec N-1 doivent en tenir compte.
- **FY2026-T2.** La marge brute bondit à 33,7 % : Target y comptabilise des remboursements de droits de douane (voir `guidance.csv`).
