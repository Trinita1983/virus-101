# Phase 1b : arbitrage de la revue du schéma

Rédigé le 2026-10-13. Fichiers lus : `docs/00-sources.md`, `docs/01-architecture.md`, `docs/01-decisions.md`, `db/schema.sql` (commit `e8f65a6`), puis le rapport du relecteur (Codex GPT-5.5, version corrigée après lecture du contexte).
Fichiers produits :
- `db/schema.sql` et `db/seed.sql` corrigés ;
- `docs/01-decisions.md` mis à jour ;
- `docs/01-invariants.md` ;
- `docs/01b-preuves.md`, généré par `db/check_invariants.py`.

## 0. Déroulement

1. **Premier passage, sans le rapport.** La première demande contenait le texte d'exemple « [COLLER ICI LE RAPPORT COMPLET…] » à la place du rapport. J'ai construit des contre-exemples à partir des points A à D de la demande (CE-…, 47 aujourd'hui).
2. **Second passage, avec le rapport.** Chacune des preuves SQL du relecteur est rejouée telle qu'écrite (K*n* = constat *n*, 22 preuves pour 14 constats) :
   - sur le schéma du commit `e8f65a6`, pour vérifier qu'elle se reproduit ;
   - puis sur le schéma corrigé.

   Je reprends son état de départ : 5 fixtures, série Sentinelles 1, exécutions 1 OMS, 2 Sentinelles, 3 Odissé. La preuve du constat 4 appelle la fonction `insert_observation` du commit `e8f65a6`, lue par `git show`.
3. **Numérotation.** Dans le rapport transmis, le constat 1 est le comptage OMS (BLOQUANT) et le constat 2 les chiffres d'un DON. Le « constat 1 » du point D de la demande correspond donc au **constat 2** du rapport. Après lecture du contexte, le relecteur le qualifie d'IMPORTANT : « une limitation importante, pas une non-conformité bloquante ».
4. **CONTEXTE.md** n'était pas dans le dépôt pendant l'arbitrage : je n'en connaissais le contenu que par les citations de la demande, du rapport et des documents. Il y a été versé le 2026-10-14, après l'arbitrage, et la lecture du texte complet ne change aucun verdict.

Résultat du rejeu : **les 14 constats sont reproduits sur le schéma `e8f65a6`**, avec les résultats annoncés par le relecteur. Seule exception : les projections de volume à 1 et 5 ans du constat 13, dont le modèle n'est pas fourni en détail (§1, ligne 13).

## 1. Tableau constat → verdict → correction

| # | Gravité (relecteur) | Constat | Preuve rejouée sur `e8f65a6` | Verdict | Justification | Correction retenue | Schéma corrigé |
|---|---|---|---|---|---|---|---|
| 1 | Bloquant | Le comptage OMS contredit le retrait après 3 absences ; des comptes égaux ne prouvent pas des ensembles égaux | **Reproduite** : (4, 4, 5) et (5, 4, 5) | **Accepté** | La contradiction est réelle (CE-A1 la montrait aussi). Un doublon reçu masque un DON manquant tant qu'on compare des totaux | D24 : écart 0 mesuré sur les présents, absents suivis à part, seules les exécutions complètes comptent ; I8 (`Id` distincts) ; I9 (DON vus en base = `seen_count`) | K1a cohérent ; K1b détecté (I9) |
| 2 | Important | Les chiffres d'un DON ne portent ni définition, ni période, ni pays | **Reproduite** : aucune colonne de définition ; (1, 1, 1) | **Accepté** | Des deux options du relecteur, je retiens les faits chiffrés définis : un passage tardif coûte une reconstruction de table (CE-D2) | D23 `report_figures` ; I57 : `as_of` jamais déduit de la publication, pas d'addition ni de comparaison aux séries | K2 : 474 suspects et 142 confirmés distincts |
| 3 | Important | Les versions historiques peuvent se chevaucher | **Reproduite** : 2 versions connues au 2026-10-07 | **Accepté** | Même défaut que CE-R1 | I22 (vue), I23 (`valid_to > valid_from`, couvre les horodatages identiques) | K3 détecté (I22, I24) |
| 4 | Important | Une révision des bornes est perdue si la valeur ne change pas | **Reproduite** avec la fonction du commit : 1 ligne, bornes 50 et 70, `v1` | **Accepté** | Le défaut est dans `insert_observation`, prototype de l'écriture du pipeline. Une republication sans changement ne doit pas créer de version | I50 ; I25 étendu à `value_status` ; `insert_observation` compare valeur, bornes et statut, mais pas `source_version` | K4 : version 2 (bornes 40 et 80) créée |
| 5 | Important | La déduplication des bruts perd la chronologie A → B → A | **Reproduite** : 2 lignes, retour à A non daté | **Accepté** | Je ne l'avais pas vu : l'archive des contenus n'est pas une chronologie | D26 `report_versions` ; I51, I52 ; I53 (JSON OMS jamais purgé) | K5 : 3 versions datées |
| 6 | Important | Le calendrier ISO n'est pas garanti ; aucune règle pour la baseline de W53 | **Reproduite** : (2020, 53, 2) ; 2021-W53 accepté ; (1, 14) | **Accepté modifié** | Le calendrier passe en `CHECK` SQL, au lieu de la validation Python proposée. La baseline de W53 est hors schéma et reste à décider | I33 en SQL (D15 révisée) ; Q9 | K6a, K6b rejetés ; K6c inchangé (Q9) |
| 7 | Important | Des clés étrangères valides peuvent donner une provenance fausse | **Reproduite** : (sentinelles, oms_don, oms_don) ; 0 | **Accepté** | Déjà corrigé au premier passage (CE-X1 à X5) | I13 (clé composite), I15 (vue) | K7a détecté (I15) ; K7b rejeté |
| 8 | Important | Le titre d'un DON régional ne cite pas ses pays | **Reproduite** : (0, 1) | **Accepté, sans changement de schéma** | C'est la méthode de classification de la phase 3. `report_countries` suffit ; un rôle par pays s'ajoutera par `ALTER TABLE` (démontré) | R11 mis à jour | K8 : même résultat (hors schéma) |
| 9 | Important | La licence du fournisseur ne vaut pas pour chaque jeu | **Reproduite** : aucune colonne ; « Licence Ouverte 2.0 » affichée pour un jeu exclu | **Accepté** | La base est publique : y stocker un jeu non publiable revient à le publier | D27 `datasets` (licence, preuve, date, publiable) ; I54 ; 9 jeux vérifiés et 7 exclus inscrits au référentiel ; provisionalité dans D28 | K9 : licence NULL, jeu non publiable, observation détectée (I54) |
| 10 | Important | Les absences n'ont pas de motif ; des valeurs incohérentes passent | **Reproduite** : (39, -5, 0, 10), (40, NULL…), (41, 0…) | **Accepté modifié** | -5 hors de ses bornes était déjà rejeté depuis le premier passage (I27). J'ajoute le motif d'absence et un domaine par série ; une valeur négative n'est jamais ramenée à 0 | D28 `value_status`, `value_min` ; I55, I56 | K10a, K10b rejetés ; K10c détecté (I56) |
| 11 | Important | Les `CHECK LIKE` ne valident pas le calendrier | **Reproduite** : `2026-99-99t99:99:99z` accepté ; `+02:00` rejeté | **Accepté** | `LIKE` est insensible à la casse : je l'avais manqué en confiant la validité à Python | I2 en SQL (`strftime`, `date`) ; D15 révisée | K11a rejeté ; K11b rejeté |
| 12 | Important | L'unicité du journal ne garantit pas un envoi Telegram unique | **Reproduite** : `a_envoyer` après restauration | **Accepté** | Déjà traité au premier passage | D19 (« au moins une fois »), R14, I45 à I47 | K12 accepté par conception |
| 13 | Important | La croissance des exports bruts n'est pas dimensionnée | **Partiellement reproduite** : l'arithmétique (260, 520, 2600) est rejouée. Les projections à 1 et 5 ans ne le sont pas, faute du modèle détaillé. Ma mesure initiale : 82,2 Mo contre 82,9 Mo chez le relecteur | **Accepté modifié** | Juste sur le fond. Le volume réel des exports n'est pas mesuré, ni par lui ni par moi : je pose des garde-fous plutôt qu'un dimensionnement | D29 : rétention par source, `VACUUM`, seuils I58, instantanés quotidiens ; R16 ; R5 | Hors schéma |
| 14 | Mineur | La liste de migration PostgreSQL omet des différences | **Reproduite** : précision de `REAL` ; (`pas du JSON`, 0) | **Accepté** | Omissions réelles dans l'architecture §6 | §6 : lignes 2, 4b, 4c et 7 ; I59 (`json_valid`) | K14b rejeté |

**Points que le relecteur a vérifiés sans défaut** : identité OMS par `Id`, index de la version courante et des recherches de DON, transactions par source, règle LLM. Je n'ai rien à y opposer.

**Verdict du relecteur** (« ne pas passer en phase 2 en l'état ») : **d'accord pour le schéma `e8f65a6`.** Après correction :
- la contradiction bloquante est levée (D24) ;
- les invariants de révision, de calendrier, de provenance et de comparaison des contenus sont formalisés (60 invariants, 49 contre-exemples et 22 preuves rejoués sans écart) ;
- tous les points à trancher l'ont été le 2026-10-14 (§7) : le schéma peut passer en phase 2.

## 2. Écart 0 et retrait (constat 1, point A ; D24)

**Contrôle « écart 0 » OMS**, évalué à chaque exécution OMS complète (statut `succes` ou `inchange`) :

1. `seen_count = expected_count`, où `expected_count` est le `@odata.count` de l'API, et les `Id` reçus sont tous distincts (I7, I8). Sinon l'exécution est `partiel` et elle ne compte pas pour le retrait.
2. Le nombre de DON de la base vus par cette exécution (`last_seen_run_id`) est égal à `seen_count` (I9). C'est ce qui garantit l'égalité des ensembles : un doublon reçu laisse un DON non vu, et la vue le signale (K1b).

**DON en base absents de l'API** (hors de l'écart) :
- ils sont « absents » après 1 ou 2 exécutions complètes sans eux, puis « retirés » à la 3e (`removed_run_id`, I10) ;
- ils restent en base, sont exclus de `reports_active` et font l'objet d'une alerte `rapport_retire` ;
- `ingestion_runs` les compte : `absent_count`, `removed_count`, `reappeared_count`.

**Votre piste** : confirmée, avec quatre amendements :
1. le compteur d'absences est calculé par la vue `reports_presence`, pas stocké ;
2. seules les exécutions complètes comptent (CE-A1) ;
3. un DON qui réapparaît redevient présent ;
4. le total du site OMS n'est pas lisible à chaque exécution (liste rendue dans le navigateur) : `@odata.count` en tient lieu, l'égalité n'ayant été vérifiée qu'une fois (3199 = 3199).

## 3. Invariants (point B)

Liste complète : `docs/01-invariants.md` (**60 invariants**, chacun avec son placement, sa justification et sa vérification).

Règle de placement (D25) :
- **SQL** tout ce qui s'écrit sans trigger ni dénormalisation coûteuse, y compris les validations de date et de JSON (D15 révisée) ;
- **Python avec un test nommé** sinon ;
- **vue `controle_invariants`** pour tout ce qui est vérifiable après coup. Elle doit être vide avant l'envoi de la base.

| Placement | Nombre | Révisions | Semaines ISO | Références entre sources |
|---|---|---|---|---|
| SQL seul | 28 | I19, I20, I23, I27 | I30, I32, I33 | I12, I13, I14, I17, I18 |
| SQL et Python | 8 | I29, I60 | | I51 |
| Python + vue de contrôle | 12 | I21, I22, I24, I25, I28 | I31 | I15, I16 |
| Python + relecture des bruts | 2 | I26, I50 | | |
| Python seul | 10 | | I34 | |

Les triggers restent refusés. Deux invariants de l'historique ne sont pas imposés par la base : **I26** (réécriture d'une version fermée) et **I50** (révision manquée). Ils sont vérifiés par la relecture des bruts (D31) ; chaque version cite son brut (I60). Risque résiduel : les versions dont l'export Odissé est purgé (R15).

## 4. Alertes (constat 12, point C ; D19)

- Garantie : livraison **au moins une fois**, dédupliquée par la clé `(channel, dedup_key)`.
- Aucune perte : l'alerte est écrite dans la même transaction que son événement (I46).
- Aucun renvoi d'une alerte marquée `envoyee` dans la base de départ (I44).
- **Doublon possible (R14)** : base non envoyée après les alertes (rejoué par CE-C2 et par K12) ; arrêt du job entre la réponse de Telegram et la validation du statut ; délai dépassé alors que Telegram a reçu le message.
- `sendMessage` n'a aucune clé d'idempotence (documentation de l'API Bot lue le 2026-10-13).
- Reprise d'un envoi incertain : nouvel essai préfixé « renvoi possible », `dedup_key` affichée en fin de message.

## 5. Chiffres des DON (constat 2, point D ; D23)

| | Rester limité en v1 | `report_figures` maintenant (retenu) |
|---|---|---|
| Coût maintenant | Nul | Une table (13 colonnes), un index unique, une vue ; dans `reports`, 7 colonnes de chiffres retirées et 2 ajoutées ; 7 invariants (I16, I17, I35 à I38, I57). Fait |
| Coût en phase 3 | Même extracteur, plus une règle arbitraire : quel couple garder ? | L'extracteur écrit des lignes au lieu de colonnes ; la difficulté d'extraction est la même |
| Coût en phase 4 | Afficher le chiffre « avec son contexte », comme le demande le relecteur, sans contexte stocké | Règle d'affichage du chiffre principal (Q8) |
| Coût d'un passage ultérieur | SQLite refuse `DROP COLUMN cases` (CE-D2) : reconstruction de `reports` ; revalidation manuelle de chiffres au sens ambigu ; extracteur, exports et tests à reprendre | Aucun |
| Information perdue en v1 | 3 DON sur 5 de l'échantillon portent plus d'un couple ; `2024-DON528` : 474 suspects et 142 confirmés au Burundi, plus 4 autres pays (CE-D1, K2) | Aucune |

**Décision : `report_figures` maintenant.** Le relecteur jugeait acceptable de rester limité, à condition d'afficher le chiffre avec son contexte et sans le comparer. Je retiens l'autre option, parce que ce contexte (définition, période, pays) doit être stocké pour pouvoir être affiché, et que le stocker plus tard coûte une migration.

## 6. Validation chiffrée

Commandes : `python db/check_invariants.py --out docs/01b-preuves.md` (code de sortie 0) et `python db/check_schema.py --out docs/01-validation.md --volume`. Moteur : SQLite 3.50.4, bases `:memory:`. Sur le schéma corrigé, les insertions d'observations du relecteur sont complétées par la colonne obligatoire `raw_payload_id` (I60), sans autre changement ; chaque adaptation est signalée en commentaire dans `docs/01b-preuves.md`.

- **Schéma corrigé exécuté sans erreur**, avec le référentiel : 13 tables, 9 index, 5 vues ; `integrity_check` = ok.
- **Vue `controle_invariants`** : 0 ligne sur la base vide, sur l'état de départ des CE et sur celui du relecteur ; `foreign_key_check` vide. Il n'y a donc pas de fausse alerte.
- **Volume** (base synthétique, sans exports) : 86,7 Mo, 10,5 Mo compressés, contre 82,2 et 10,2 Mo avant la phase 1b.

**49 contre-exemples de l'arbitrage** : phase 1, 40 acceptés sur 43 applicables (L1 et L2 sont sans objet en phase 1). Schéma corrigé, aucun écart avec le résultat attendu :

| Résultat sur le schéma corrigé | Nombre | Cas |
|---|---|---|
| Rejeté par la base | 25 | A3, A4, A6, A7, R4, R6, W1, W4, W5, W6, W7, W8, X1, X2, X3, X6, X8, C1, C3, C4, C5, D3, D4, P1, S1 |
| Accepté, détecté par `controle_invariants` | 17 | A2, A5, A8, R1, R2, R3, R5, R7, R9, R10, W2, W3, X4, X5, X7, V1, L2 |
| Accepté, détecté par `PRAGMA foreign_key_check` | 1 | G1 (I1) |
| Accepté, non détecté dans la base : relecture des bruts (phase 2) | 1 | R8 (I26) : `tests/test_controle.py::test_relecture_detecte_valeur_reecrite` |
| Accepté par conception | 1 | C2 (D19, R14) |
| État cohérent attendu | 3 | A1, D1, L1 |
| Sans objet sur le nouveau schéma | 1 | D2 (coût d'un `DROP COLUMN`) |

**22 preuves du relecteur** : phase 1, 20 acceptées sur 21. K11b (fuseau `+02:00`) était déjà rejetée. Les 4 constats hors schéma, sans instruction, sont comptés comme acceptés. Schéma corrigé, aucun écart :

| Résultat sur le schéma corrigé | Nombre | Cas |
|---|---|---|
| Rejeté par la base | 8 | K6a, K6b, K7b, K10a, K10b, K11a, K11b, K14b |
| Accepté, détecté par `controle_invariants` | 5 | K1b (I9), K3 (I22, I24), K7a (I15), K9 (I54), K10c (I56) |
| Accepté par conception | 1 | K12 (R14) |
| État cohérent après correction | 4 | K1a (écart 0), K2 (chiffres définis), K4 (bornes révisées), K5 (chronologie A → B → A) |
| Constat hors schéma, même résultat | 4 | K6c (Q9), K8 (R11), K13 (D29), K14a (§6) |

Les noms des tests Python futurs figurent pour chaque cas dans `docs/01b-preuves.md` et dans `docs/01-invariants.md`.

## 7. Points tranchés par le porteur du projet (2026-10-14)

1. **Reformulation du critère « écart 0 » de CONTEXTE** (D24, §2) : **validée le 2026-10-14.** Pas de contrôle manuel périodique du site ; une vérification unique en phase 2.
2. **Révisions non détectables (I26, I50, R15)** : **relecture des bruts retenue le 2026-10-14** (D31, I60).
3. **Changement de licence d'un jeu après collecte** : **les données déjà collectées restent** (D30) ; seule une collecte postérieure est bloquée (I54, CE-L1, CE-L2).
4. **Doublons d'alerte (R14)** : **acceptés**, pas de second envoi de la base (D19).
5. **Rétention et seuils** (D29, Q1) : **validés le 2026-10-14** (26 semaines pour les exports Odissé ; alerte à 1 Gio, blocage à 1,5 Gio).
6. **Baseline de la semaine 53** (Q9) : **fenêtre de ±3 semaines sur 5 ans, au moins 3 années** (D32).
7. **Retrait d'un DON** : **seuil de 3 exécutions complètes gardé** ; un DON « absent » reste affiché ; la page d'un DON retiré reste en ligne avec la mention « retiré par l'OMS le … » (D24, phase 4).
8. **CONTEXTE.md** : **versé au dépôt le 2026-10-14**, à la racine, avec une annexe qui renvoie aux décisions qui le précisent (D1, D19, D23, D24, phase 0).
