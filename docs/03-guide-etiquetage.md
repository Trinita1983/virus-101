# Guide d'étiquetage du jeu de référence (phase 3)

Vous étiquetez `tests/gold/don_gold.csv` ; je ne mets aucune étiquette. Les 5 DON de `fixtures/who_don_sample.json` ci-dessous servent **d'illustration seulement** : ils n'entrent pas dans le jeu de référence. Les règles marquées *(à confirmer)* sont des propositions, à corriger.

## Le fichier

`observatoire gold-sample` écrit `tests/gold/a_etiqueter.csv` (40 DON, split déjà calculé) et, pour chaque DON, un texte `tests/gold/textes/<Id>.txt`. **Étiquetez à partir de ce texte** : la citation doit en être un extrait exact.

Colonnes de `don_gold.csv` (UTF-8, séparateur `,`, une ligne par chiffre) :
`don_id, split, pays, maladie, type, valeur, qualificatif, cumule_ou_nouveau, date_reference, citation`

| Colonne | Contenu |
|---|---|
| `don_id` | l'`Id` du DON (colonne `don_id` de `a_etiqueter.csv`) ; `split` : recopié de `a_etiqueter.csv`, ne pas le changer |
| `pays` | code ISO 3166-1 alpha-3 (`SOM`) ; vide = ensemble du rapport |
| `maladie` | code de `diseases` dans `db/seed.sql` s'il existe (`cholera`, `mpox`...), sinon le nom anglais en minuscules |
| `type` | `cas` ou `deces` |
| `valeur` | entier sans séparateur : `2,027` et `2 027` → `2027` ; `two` → `2` ; `zero` → `0` |
| `qualificatif` | `confirme`, `probable`, `suspect`, ou `non_precise` si le texte ne le dit pas *(`non_precise` ajouté pour coller au schéma : à confirmer)* |
| `cumule_ou_nouveau` | `cumule`, `nouveau`, ou `indetermine` |
| `date_reference` | `AAAA-MM-JJ` de la date « au… » citée (« as of 17 August 2024 » → `2024-08-17`) ; vide si le texte n'en cite pas |
| `citation` | extrait **exact et d'une seule ligne** du texte, contenant le nombre et ses mots d'approximation ; ou `aucun chiffre` |

## Règles

1. **Une ligne par chiffre** : un nombre de cas et un nombre de décès dans la même phrase font deux lignes, avec la même citation si besoin.
2. **Seuls les nombres écrits comptent** (chiffres ou mots : `two`, `zero`). « a new case », « the death of an employee » n'ont pas de nombre : pas de ligne. « no deaths » : ligne `deces` = `0` *(à confirmer)*.
3. **Périmètre** : les chiffres de l'événement décrit par le DON. Les chiffres d'arrière-plan (années précédentes) et ceux d'autres maladies ne sont pas notés *(à confirmer)*.
4. **Pas de chiffre** : une seule ligne, `don_id` et `split` remplis, `citation` = `aucun chiffre`, le reste vide.
5. **Plusieurs pays** : une ligne par pays et par type ; un total régional éventuel est une ligne à `pays` vide. N'additionnez jamais vous-même.
6. **Cumulé avec mise à jour** : notez ce que dit ce DON. Un « update N » qui répète un cumul remplace l'ancien : on étiquette seulement les chiffres présents dans le texte, avec leur date.
7. **Approximation** (`about`, `at least`, `more than`, `nearly`) : `valeur` = le nombre écrit ; le mot d'approximation reste **dans la citation**. Il n'y a pas de colonne dédiée ; si vous en voulez une (`precision`), dites-le.
8. **Létalité en pourcentage** (`CFR 0.5%`, `case fatality ratio`) : pas de ligne, ce n'est ni un nombre de cas ni de décès.
9. **Pourcentages, dates, années, semaines, âges, numéros de cas** (« case 1 », « 33-year-old ») : pas de ligne.

## Exemples (DON de la fixture, hors jeu de référence)

| `e09a12f1-3ba4-4021-aa21-94e0ce0f1e8b` | `holdout` | `SOM` | `cholera` | `cas` | `7796` | `non_precise` | `cumule` | `2022-07-10` | `a cumulative number of 7796 cases of cholera` |
| `e09a12f1-3ba4-4021-aa21-94e0ce0f1e8b` | `holdout` | `SOM` | `cholera` | `deces` | `37` | `non_precise` | `cumule` | `2022-07-10` | `including 37 associated deaths` |
| `a2e9b557-fa1d-4427-bc25-b80d6684b14e` | `dev` | `BDI` | `mpox` | `cas` | `474` | `suspect` | `cumule` | `2024-08-17` | `of which 474 suspected cases (86.9%)` |
| `a2e9b557-fa1d-4427-bc25-b80d6684b14e` | `dev` | `RWA` | `mpox` | `cas` | `4` | `confirme` | `cumule` | `2024-08-07` | `four confirmed mpox cases and zero deaths had cumulatively been reported` |
| `a2e9b557-fa1d-4427-bc25-b80d6684b14e` | `dev` | `RWA` | `mpox` | `deces` | `0` | `non_precise` | `cumule` | `2024-08-07` | `four confirmed mpox cases and zero deaths had cumulatively been reported` |
| `202f9f50-fdb1-4f07-b54b-007046fb5b59` | `holdout` | `IDN` | `grippe_aviaire` | `cas` | `119` | `confirme` | `cumule` |   | `Of the 119 cases confirmed to date in Indonesia, 97 have been fatal.` |
| `202f9f50-fdb1-4f07-b54b-007046fb5b59` | `holdout` | `IDN` | `grippe_aviaire` | `deces` | `97` | `non_precise` | `cumule` |   | `Of the 119 cases confirmed to date in Indonesia, 97 have been fatal.` |
| `9cca163d-6ef3-4d3e-b149-2cd7acf408f6` | `holdout` |   |   |   |   |   |   |   | `aucun chiffre` |

- **Cumulé (Somalie)** : 2 lignes. La létalité de la même phrase, `(CFR: 0.5%)`, ne donne **aucune** ligne.
- **Plusieurs pays (Mpox, région Afrique)** : une ligne par pays et par type ; ici le Burundi et le Rwanda (les autres pays du DON restent à faire de la même façon). « four » s'écrit `4`, « zero deaths » `0`.
- **Cumulé avec mise à jour (Indonésie, update 32)** : « to date » sans date citée → `date_reference` vide. « a new case » n'a pas de nombre : pas de ligne.
- **Sans chiffre (Russie)** : le seul nombre lié aux cas, « only two cases of COVID-19 », concerne d'autres agents, pas l'événement : `aucun chiffre`.
- **Approximation** : dans la phrase « more than 78 000 suspected cholera cases » (Somalie, 2017, donc d'arrière-plan et non noté ici), on écrirait `78000`, `suspect`, avec `more than 78 000 suspected cholera cases` en citation.
- **Format** : « 2,027 cases and 150 deaths » (choléra 1996) → `2027` et `150`.

## Points à confirmer

(1) `non_precise` comme qualificatif ; (2) « no deaths » = `0` ; (3) chiffres d'arrière-plan non notés ; (4) colonne `precision` pour les approximations.
