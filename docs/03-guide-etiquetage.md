# Guide d'étiquetage du jeu de référence (phase 3)

Vous étiquetez `tests/gold/don_gold.csv` ; je ne mets aucune étiquette. Les 5 DON de `fixtures/who_don_sample.json` cités ici servent **d'illustration seulement** : ils n'entrent pas dans le jeu de référence. Les règles marquées *(à confirmer)* sont des propositions.

## Le fichier

`observatoire gold-sample` écrit `tests/gold/a_etiqueter.csv` (40 DON, dont 10 tirés au hasard : colonne `origine` = `aleatoire`, les autres `strate`) et, pour chaque DON, un texte `tests/gold/textes/<Id>.txt`. **Étiquetez à partir de ce texte** : la citation doit en être un extrait exact.

Colonnes de `don_gold.csv` (UTF-8, séparateur `,`, une ligne par chiffre) :
`don_id, split, pays, maladie, type, valeur, qualificatif, precision, cumule_ou_nouveau, date_reference, citation`

| Colonne | Contenu |
|---|---|
| `don_id`, `split` | recopiés de `a_etiqueter.csv` ; ne pas changer le split |
| `pays` | code ISO 3166-1 alpha-3 (`SOM`) ; vide = ensemble du rapport |
| `maladie` | code de `diseases` dans `db/seed.sql` s'il existe (`cholera`, `mpox`...), sinon le nom anglais en minuscules |
| `type` | `cas` ou `deces` |
| `valeur` | entier sans séparateur : `2,027` et `2 027` → `2027` ; `two` → `2` ; `zero` → `0` |
| `qualificatif` | `confirme`, `probable`, `suspect`, ou `non_precise` si le texte ne le dit pas *(à confirmer)* |
| `precision` | `exact`, `environ`, `au_moins`, `au_plus`, `fourchette_basse`, `fourchette_haute` (définitions ci-dessous) |
| `cumule_ou_nouveau` | `cumule`, `nouveau`, ou `indetermine` |
| `date_reference` | `AAAA-MM-JJ` de la date « au… » citée (« as of 17 August 2024 » → `2024-08-17`) ; vide si le texte n'en cite pas |
| `citation` | extrait **exact et d'une seule ligne** du texte, contenant le nombre **et ses mots d'approximation** ; ou `aucun chiffre` |

## Chiffre de l'événement en cours, chiffre d'arrière-plan

**Chiffre de l'événement en cours** : un nombre de cas ou de décès qui répond oui aux deux questions :
1. *Même événement ?* Il compte les cas ou décès de la maladie et du lieu (pays, région) que désigne le titre du DON.
2. *Même période ?* Il porte sur la période de cet événement telle que le DON la décrit : cumul depuis le début déclaré de l'événement (même s'il remonte à plusieurs années, comme l'épidémie multi-pays de mpox ouverte en 2022) ou nombre de nouveaux cas d'une période récente, jusqu'à la date du DON.

**Chiffre d'arrière-plan** : tout autre nombre de cas ou de décès, c'est-à-dire :
- (a) une période terminée avant le début de l'événement : années ou saisons précédentes, flambées antérieures du même pays ;
- (b) une autre maladie, un autre agent ou un autre événement que celui du titre (comparaisons, autres agents testés) ;
- (c) un historique ou une statistique générale (totaux de plusieurs années, endémie de fond).

Si le texte ne permet pas de répondre oui à 1 et à 2, le chiffre est d'arrière-plan *(à confirmer)*.

**Les chiffres d'arrière-plan ne sont pas étiquetés.** Un extracteur qui en retrouve un produit un **faux positif** : il compte contre sa précision, et contre le taux de faux chiffres sur les DON sans chiffre.

| | Exemple (fixture) | Pourquoi |
|---|---|---|
| En cours | Somalie : « a cumulative number of 7796 cases of cholera including 37 associated deaths », du 1er janvier au 10 juillet 2022 | choléra en Somalie, période de l'événement du titre |
| En cours | Rwanda (mpox, région Afrique) : « four confirmed mpox cases and zero deaths had cumulatively been reported » | épidémie de mpox du titre, cumul au 7 août 2024 |
| Arrière-plan | Somalie : « In 2017, more than 78 000 suspected cholera cases including 1159 deaths » (de même, 2021 : « a total of 6205 acute watery diarrhoea (AWD)/suspected cholera cases including 39 deaths ») | années précédentes (a) |
| Arrière-plan | Russie : « only two cases of COVID-19, three cases of rhinovirus » | autres agents que celui de l'événement (b) |

## Règles

1. **Une ligne par chiffre** : un nombre de cas et un nombre de décès dans la même phrase font deux lignes, avec la même citation si besoin.
2. **Seuls les nombres écrits comptent** (chiffres ou mots : `two`, `zero`). « a new case », « the death of an employee » n'ont pas de nombre : pas de ligne. « no deaths » : ligne `deces` = `0` *(à confirmer)*.
3. **Périmètre** : uniquement les chiffres de l'événement en cours (section précédente).
4. **Pas de chiffre** : une seule ligne, `don_id` et `split` remplis, `citation` = `aucun chiffre`, le reste vide. Un DON qui n'a que des chiffres d'arrière-plan est aussi « aucun chiffre ».
5. **Plusieurs pays** : une ligne par pays et par type ; un total régional éventuel est une ligne à `pays` vide. N'additionnez jamais vous-même.
6. **Cumulé avec mise à jour** : on étiquette ce que dit ce DON, avec sa date. Le cumul d'un DON « update N » est un chiffre à part entière, pas la différence avec l'update précédent.
7. **Létalité en pourcentage** (`CFR 0.5%`, `case fatality ratio`) : pas de ligne, ce n'est ni un nombre de cas ni de décès.
8. **Pourcentages, dates, années, semaines, âges, numéros de cas** (« case 1 », « 33-year-old »), et nombres qui ne comptent pas des cas ou des décès (« At least four countries », « Over half of the cases (53.5%) ») : pas de ligne.

## Précision (`precision`)

La `valeur` est toujours le nombre écrit dans le texte, sans le corriger ; le mot d'approximation reste dans la `citation`.

| Valeur | Quand | Mots typiques |
|---|---|---|
| `exact` | nombre donné sans réserve | « 7796 cases », « four confirmed » |
| `environ` | ordre de grandeur, ni borne ni fourchette | about, approximately, around, nearly, almost, estimated, « ~ » |
| `au_moins` | le vrai nombre est supérieur ou égal | at least, more than, over, « ≥ » (« more than X » : `valeur` = X, la stricte supériorité n'est pas notée) *(à confirmer)* |
| `au_plus` | le vrai nombre est inférieur ou égal | up to, no more than, fewer than, less than, at most |
| `fourchette_basse`, `fourchette_haute` | « de X à Y » : **une ligne par borne**, mêmes colonnes, même citation (la phrase qui contient les deux nombres) | between X and Y, X to Y, X–Y |

Exemples. Aucune approximation d'un chiffre de l'événement en cours n'existe dans la fixture ; la seule phrase approchante est d'arrière-plan (« more than 78 000 suspected cholera cases », non étiquetée). Les autres sont des **exemples fictifs** :

| | Phrase | Lignes |
|---|---|---|
| exact (fixture) | « a cumulative number of 7796 cases of cholera » | `7796`, `exact` |
| au_moins (exemple fictif) | « At least 40 confirmed cases have been reported. » | `40`, `confirme`, `au_moins` |
| environ (exemple fictif) | « About 200 cases were reported. » | `200`, `environ` |
| au_plus (exemple fictif) | « Up to 30 deaths may be linked to the event. » | `30`, `deces`, `au_plus` |
| fourchette (exemple fictif) | « Between 120 and 150 suspected cases were reported. » | deux lignes : `120` `fourchette_basse` et `150` `fourchette_haute`, `suspect` |

## Exemples d'étiquettes (DON de la fixture, hors jeu de référence)

| `e09a12f1-3ba4-4021-aa21-94e0ce0f1e8b` | `holdout` | `SOM` | `cholera` | `cas` | `7796` | `non_precise` | `exact` | `cumule` | `2022-07-10` | `a cumulative number of 7796 cases of cholera` |
| `e09a12f1-3ba4-4021-aa21-94e0ce0f1e8b` | `holdout` | `SOM` | `cholera` | `deces` | `37` | `non_precise` | `exact` | `cumule` | `2022-07-10` | `including 37 associated deaths` |
| `a2e9b557-fa1d-4427-bc25-b80d6684b14e` | `dev` | `BDI` | `mpox` | `cas` | `474` | `suspect` | `exact` | `cumule` | `2024-08-17` | `of which 474 suspected cases (86.9%)` |
| `a2e9b557-fa1d-4427-bc25-b80d6684b14e` | `dev` | `RWA` | `mpox` | `cas` | `4` | `confirme` | `exact` | `cumule` | `2024-08-07` | `four confirmed mpox cases and zero deaths had cumulatively been reported` |
| `a2e9b557-fa1d-4427-bc25-b80d6684b14e` | `dev` | `RWA` | `mpox` | `deces` | `0` | `non_precise` | `exact` | `cumule` | `2024-08-07` | `four confirmed mpox cases and zero deaths had cumulatively been reported` |
| `202f9f50-fdb1-4f07-b54b-007046fb5b59` | `holdout` | `IDN` | `grippe_aviaire` | `cas` | `119` | `confirme` | `exact` | `cumule` |   | `Of the 119 cases confirmed to date in Indonesia, 97 have been fatal.` |
| `202f9f50-fdb1-4f07-b54b-007046fb5b59` | `holdout` | `IDN` | `grippe_aviaire` | `deces` | `97` | `non_precise` | `exact` | `cumule` |   | `Of the 119 cases confirmed to date in Indonesia, 97 have been fatal.` |
| `9cca163d-6ef3-4d3e-b149-2cd7acf408f6` | `holdout` |   |   |   |   |   |   |   |   | `aucun chiffre` |

- **Cumulé (Somalie)** : 2 lignes. La létalité de la même phrase, `(CFR: 0.5%)`, ne donne **aucune** ligne.
- **Plusieurs pays (Mpox, région Afrique)** : une ligne par pays et par type ; ici le Burundi et le Rwanda (les autres pays du DON se feraient de la même façon). « four » s'écrit `4`, « zero deaths » `0`.
- **Cumulé avec mise à jour (Indonésie, update 32)** : « to date » sans date citée → `date_reference` vide. « a new case » n'a pas de nombre : pas de ligne.
- **Sans chiffre (Russie)** : « only two cases of COVID-19 » concerne d'autres agents (arrière-plan) : `aucun chiffre`.

## Points à confirmer

(1) `non_precise` comme qualificatif ; (2) « no deaths » = `0` ; (3) « more than X » = `au_moins` X ; (4) un chiffre dont le texte ne dit pas s'il est de l'événement en cours est d'arrière-plan.
