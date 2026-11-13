# FP&A Analytics : Target Corporation

> Analyse FP&A de **Target Corporation** (NYSE : TGT) sur ses **comptes réels publiés à la SEC** : pourquoi la marge s'est dégradée, où l'exercice va atterrir, et quels leviers préservent la trésorerie.

[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)

## La question métier

En mars 2022, Target annonçait pour l'exercice FY2022 un **taux de marge opérationnelle de 8 % ou plus**. En mai, l'objectif tombait à **environ 6 %**. Au final, le résultat opérationnel est passé de **8,9 Md$ (8,4 % du CA) en FY2021 à 3,8 Md$ (3,5 %) en FY2022**, pour un chiffre d'affaires en hausse à 109,1 Md$.

Ce projet reconstruit l'analyse qu'aurait menée une équipe FP&A :

1. **Pourquoi la marge s'est-elle dégradée ?** Effets volume, panier moyen, mix, démarques et coûts logistiques, avec le lien stocks → marge → cash.
2. **Où l'exercice va-t-il atterrir ?** Rolling forecast trimestriel du CA, de la marge et du cash.
3. **Quels leviers préservent la trésorerie ?** Scénarios sur les stocks, les délais fournisseurs et les investissements.

Les comptes historiques et les objectifs de la direction sont réels et sourcés ; les prévisions et les scénarios sont des calculs propres au projet.

## Architecture

```mermaid
flowchart LR
    A["SEC EDGAR<br/>API XBRL + communiqués"] --> B["Bronze<br/>JSON/HTML bruts, datés, hachés"]
    B --> C["Silver<br/>faits normalisés, trimestres reconstruits"]
    C --> D["Gold<br/>modèle en étoile, KPI réconciliés"]
    D --> E["Power BI<br/>performance, écarts, forecast, cash"]
    D --> F["Python<br/>prévision et scénarios"]
    F --> G["Streamlit<br/>simulateur d'hypothèses"]
    H["Contrôles qualité<br/>tests + rapprochements 10-K"] -.-> C
    H -.-> D
```

| Couche | Contenu | Outils |
|---|---|---|
| **Bronze** | Réponses brutes de la SEC, archivées sans modification, avec journal (URL, date, SHA-256) | Python, requests |
| **Silver** | Une ligne par indicateur et période, libellés harmonisés, trimestres reconstruits à partir des cumuls | pandas, DuckDB, Parquet |
| **Gold** | Faits `financials`, `guidance`, `category_sales` et dimensions `period`, `account` | SQL (DuckDB) |
| **Restitution** | Dashboard 4 pages, simulateur, note de gestion | Power BI, DAX, Streamlit |

## Avancement

- [x] **Phase 1 : collecte.** Comptes XBRL, liste des dépôts, 31 communiqués de résultats, référentiel de guidance sourcé
- [ ] **Phase 2 : fiabilisation.** Couche Silver/Gold, trimestres, rapport de contrôles vs 10-K
- [ ] **Phase 3 : analyse et dashboard V1.** P&L de gestion, réel vs N-1 et vs guidance, effets prix/volume, BFR, free cash-flow
- [ ] **Phase 4 : prévision et scénarios.** ETS/SARIMA vs référence saisonnière (MAE, WAPE), cash projeté, Streamlit, note de gestion

## Données

| Source | Contenu | Emplacement |
|---|---|---|
| [API Company Facts](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | 543 concepts XBRL publiés par Target depuis 2008 | `data/bronze/sec/companyfacts/` |
| [API Submissions](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | Liste des 10-K, 10-Q et 8-K avec liens | `data/bronze/sec/submissions/` |
| Communiqués de résultats (8-K, pièce 99) | Résultats trimestriels et objectifs de la direction | `data/bronze/sec/earnings_releases/` |
| Référentiel de guidance | 58 objectifs chiffrés FY2021–FY2026, chacun cité et lié à sa source | [`data/reference/guidance.csv`](data/reference/guidance.csv) |

Chaque collecte est tracée dans `data/bronze/_ingestion_log.jsonl`. Les instantanés sont versionnés dans le dépôt pour que les analyses soient reproductibles même si la SEC republie des chiffres.

### Points d'attention déjà identifiés

- **Exercice décalé.** L'exercice de Target se termine le samedi le plus proche du 31 janvier : FY2022 couvre février 2022 à janvier 2023. FY2023 compte 53 semaines.
- **Changements de libellés XBRL.** Le chiffre d'affaires passe de `Revenues` (jusqu'en 2015) à `RevenueFromContractWithCustomerExcludingAssessedTax` (à partir de 2017).
- **Changement de présentation au T4 2024.** Le CA devient une seule ligne « Net Sales », et le taux de marge brute est recalculé sur cette base.
- **Montants cumulés.** Les 10-Q publient des cumuls depuis le début de l'exercice. Le T4 se déduit de l'exercice moins les 9 mois.

## Installation

```bash
git clone https://github.com/norahabrich/fpa-analytics.git
cd fpa-analytics
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Utilisation

La SEC exige un User-Agent avec un contact pour chaque requête :

```bash
export SEC_USER_AGENT="Prénom Nom prenom.nom@exemple.com"

python -m fpa.ingestion.collect                       # comptes + liste des dépôts
python -m fpa.ingestion.earnings_releases             # communiqués de résultats
python -m fpa.ingestion.earnings_releases --offline   # réextraction depuis les archives
```

## Structure

```
├── data/
│   ├── bronze/          # données brutes SEC, datées et journalisées
│   └── reference/       # référentiels saisis à la main et sourcés (guidance)
├── docs/                # méthodologie et décisions
├── src/fpa/
│   └── ingestion/       # client SEC, archivage Bronze, inventaires, communiqués
└── tests/               # tests unitaires et contrôles de traçabilité
```

## Limites

- Les comptes publiés ne donnent ni le détail par produit ou par magasin, ni les factures. L'analyse se fait au niveau du groupe, des catégories et des indicateurs publiés (transactions, panier moyen).
- La guidance de la direction sert de référence « budget ». Elle n'est pas le budget interne de l'entreprise.
- Projet personnel, sans lien avec Target Corporation.

## Licence

Code sous licence MIT. Les données proviennent de documents publics déposés à la SEC.
