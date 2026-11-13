# Phase 1 : collecte

## Ce qui est collecté

| Jeu | Requête | Fichiers produits |
|---|---|---|
| Company Facts | `data.sec.gov/api/xbrl/companyfacts/CIK0000027419.json` | `companyfacts.json`, `concepts_inventory.csv` |
| Submissions | `data.sec.gov/submissions/CIK0000027419.json` | `submissions.json`, `filings.csv` |
| Communiqués de résultats | 8-K item 2.02, pièce 99, depuis 2019 | `*.htm`, `outlook_excerpts.csv` |

## Règles de la couche Bronze

1. **Aucune modification** : on écrit les octets reçus tels quels.
2. **Rangement daté** : `source/jeu/CIK/AAAA-MM-JJ/fichier`.
3. **Journal** : une ligne par collecte dans `_ingestion_log.jsonl` (URL, date UTC, taille, SHA-256, statut `new` ou `unchanged`).
4. **Validation minimale** : un JSON invalide (page d'erreur, réponse coupée) est refusé.
5. **Respect de la SEC** : User-Agent avec contact, au plus 10 requêtes par seconde, reprises exponentielles sur les erreurs 429 et 5xx.

## Du communiqué au référentiel de guidance

1. `earnings_releases.py` télécharge les communiqués et isole les paragraphes de perspectives (`outlook_excerpts.csv`).
2. Les objectifs sont saisis dans `data/reference/guidance.csv`, avec la citation exacte et le lien.
3. `tests/test_guidance.py` vérifie que chaque citation figure bien dans le communiqué archivé.

L'extraction automatique sert d'aide à la lecture. La saisie reste manuelle, parce que les objectifs sont rédigés en langage naturel (« low-single digit decline ») et parfois dans des tableaux.

## Premiers constats pour la phase 2

- Exercice terminé fin janvier ou début février ; FY2023 compte 53 semaines.
- Le libellé XBRL du CA change entre 2015 et 2017.
- Au T4 2024, Target fusionne Sales, Other Revenue et Total Revenue en une seule ligne « Net Sales » et redéfinit le taux de marge brute.
- Les 10-Q publient des cumuls : il faut reconstruire chaque trimestre.
