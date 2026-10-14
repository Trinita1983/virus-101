# Phase 1b : rejeu des contre-exemples et des preuves du relecteur

Fichier généré par `python db/check_invariants.py --out docs/01b-preuves.md`. Ne pas modifier à la main.

Moteur : SQLite 3.50.4, bases `:memory:` ouvertes par le module `sqlite3` de Python (l'outil en ligne de commande `sqlite3` n'est pas installé sur ce poste). Chaque cas part d'une base neuve. Phase 1 = schéma et référentiel du commit `e8f65a6` (lus par `git show`).

Deux séries de cas :
- **§2-3, contre-exemples de l'arbitrage** (CE-…), construits à partir des points A à D de la demande ;
- **§4-5, preuves du rapport du relecteur** (K…, K*n* = constat *n*), rejouées telles qu'écrites, sur son état de départ (5 fixtures, série Sentinelles 1, exécutions 1 OMS, 2 Sentinelles, 3 Odissé). Les instructions marquées « complément » montrent la correction retenue.

## 1. Application des schémas

**Phase 1 (`e8f65a6`)** : schéma puis référentiel exécutés sans erreur ; 10 tables, 6 index, 2 vues ; `integrity_check` = ok.

**Corrigé (`db/schema.sql`)** : schéma puis référentiel exécutés sans erreur ; 13 tables, 9 index, 5 vues ; `integrity_check` = ok.
`controle_invariants` : 0 ligne(s) sur la base vide, 0 sur l'état de départ des CE, 0 sur celui du relecteur ; `foreign_key_check` : 0 et 0 violation(s). La vue ne produit pas de fausse alerte sur un état cohérent.

État de départ des CE : 3 DON réels de la fixture (`2026-DON620`, `2024-DON528`, `2022-DON398_1`) vus par l'exécution OMS n° 1 ; une série Sentinelles hebdomadaire (S39 révisée de 60 à 63, S40 = 70) ; une série Odissé annuelle ; une anomalie ouverte sur S39 v2 ; une alerte envoyée. Schéma corrigé seulement : deux chiffres de `2024-DON528` (Burundi, Kenya). Valeurs des séries fictives.

## 2. Contre-exemples de l'arbitrage : synthèse

49 contre-exemples. Phase 1 : **40 acceptés sur 43** applicables. Schéma corrigé (48 applicables) :

- rejeté par la base : **25**
- accepté, détecté par `controle_invariants` : **17**
- accepté, détecté par `PRAGMA foreign_key_check` : **1**
- accepté, **non détecté dans la base** : contrôle de relecture des bruts (phase 2, D31) : **1**
- accepté **par conception** (risque documenté) : **1**
- accepté, état cohérent (attendu) : **3**

Écarts entre résultat attendu et résultat obtenu : **aucun**.

| Code | Point | Invariant | Phase 1 (`e8f65a6`) | Schéma corrigé | Couverture Python |
|---|---|---|---|---|---|
| A1 | A | I7, I9, I10 | accepté | accepté, aucune violation | `tests/test_oms.py::test_ecart_zero_sur_les_presents, ::test_retrait_a_la_troisieme_absence, ::test_execution_partielle_ne_compte_pas` |
| A2 | A | I10 | accepté | accepté, vue : I10 | `tests/test_oms.py::test_retrait_a_la_troisieme_absence` |
| A3 | A | I10 | accepté | rejeté | `(contrainte SQL)` |
| A4 | A | I7 | accepté | rejeté | `(contrainte SQL)` |
| A5 | A | I9 | accepté | accepté, vue : I9 | `tests/test_oms.py::test_ecart_zero_sur_les_presents` |
| A6 | A | I8 | accepté | rejeté | `(contrainte SQL) ; Id distincts : tests/test_oms.py::test_pagination_complete_sans_doublon` |
| A7 | A | I5 | accepté | rejeté | `(contrainte SQL)` |
| A8 | A | I6 | accepté | accepté, vue : I6 | `tests/test_pipeline.py::test_echec_de_source_ferme_l_execution` |
| R1 | B-révisions | I22 | accepté | accepté, vue : I22 | `tests/test_observations.py::test_fermeture_egale_ouverture_suivante` |
| R2 | B-révisions | I21 | accepté | accepté, vue : I21 | `tests/test_observations.py::test_versions_numerotees_sans_trou` |
| R3 | B-révisions | I22 | accepté | accepté, vue : I22 | `tests/test_observations.py::test_retrait_cree_une_version_nulle` |
| R4 | B-révisions | I23 | accepté | rejeté | `(contrainte SQL)` |
| R5 | B-révisions | I25 | accepté | accepté, vue : I25 | `tests/test_observations.py::test_valeur_inchangee_ne_cree_pas_de_version` |
| R6 | B-révisions | I27 | accepté | rejeté | `(contrainte SQL)` |
| R7 | B-révisions | I28 | accepté | accepté, vue : I28 | `tests/test_detection.py::test_revision_remplace_l_anomalie` |
| R8 | B-révisions | I26 | accepté | accepté, aucune violation | `tests/test_observations.py::test_ecriture_par_ajout_seul, tests/test_controle.py::test_relecture_detecte_valeur_reecrite` |
| R9 | B-révisions | I24 | accepté | accepté, vue : I24 | `tests/test_observations.py::test_valid_from_egale_debut_d_execution` |
| R10 | B-révisions | I29 | accepté | accepté, vue : I29 | `tests/test_detection.py::test_anomalie_reprend_la_valeur_observee` |
| W1 | B-semaines | I30 | accepté | rejeté | `(contrainte SQL)` |
| W2 | B-semaines | I31 | accepté | accepté, vue : I31 | `tests/test_semaines.py::test_type_de_periode_coherent` |
| W3 | B-semaines | I31 | accepté | accepté, vue : I31 | `tests/test_semaines.py::test_type_de_periode_coherent` |
| W4 | B-semaines | I32 | accepté | rejeté | `(contrainte SQL)` |
| W5 | B-semaines | I33 | accepté | rejeté | `(contrainte SQL) ; tests/test_semaines.py::test_lundi_de_la_semaine_iso` |
| W6 | B-semaines | I33 | accepté | rejeté | `(contrainte SQL) ; tests/test_semaines.py::test_semaine_53_refusee_si_annee_a_52_semaines` |
| W7 | B-semaines | I33 | accepté | rejeté | `(contrainte SQL) ; tests/test_semaines.py::test_annee_iso_differente_de_l_annee_civile` |
| W8 | B-semaines | I33 | accepté | rejeté | `(contrainte SQL) ; tests/test_semaines.py::test_lundi_de_la_semaine_iso` |
| X1 | B-références | I13 | accepté | rejeté | `(contrainte SQL)` |
| X2 | B-références | I13 | accepté | rejeté | `(contrainte SQL)` |
| X3 | B-références | I12 | accepté | rejeté | `(contrainte SQL)` |
| X4 | B-références | I15 | accepté | accepté, vue : I15 | `tests/test_observations.py::test_observation_rattachee_a_la_source_de_sa_serie` |
| X5 | B-références | I15 | accepté | accepté, vue : I15 | `tests/test_observations.py::test_observation_rattachee_a_la_source_de_sa_serie` |
| X6 | B-références | I14 | sans objet | rejeté | `(contrainte SQL)` |
| X7 | B-références | I16 | sans objet | accepté, vue : I16 | `tests/test_chiffres.py::test_chiffre_rattache_a_une_version_de_son_don` |
| X8 | B-références | I17 | sans objet | rejeté | `(contrainte SQL)` |
| C1 | C | I44 | rejeté | rejeté | `(contrainte SQL)` |
| C2 | C | D19, R14 | accepté | accepté, aucune violation | `tests/test_alertes.py::test_alerte_journalisee_avant_envoi` |
| C3 | C | I47 | accepté | rejeté | `(contrainte SQL)` |
| C4 | C | I47 | accepté | rejeté | `(contrainte SQL)` |
| C5 | C | I47 | accepté | rejeté | `(contrainte SQL)` |
| D1 | D | D23 | accepté | accepté, aucune violation | `tests/test_chiffres.py::test_un_chiffre_par_pays_et_par_mesure` |
| D2 | D | D23 | rejeté | sans objet | `(sans objet)` |
| D3 | D | I35 | rejeté | rejeté | `(contrainte SQL)` |
| D4 | D | I36 | sans objet | rejeté | `(contrainte SQL)` |
| P1 | bruts | I53 | accepté | rejeté | `(contrainte SQL)` |
| V1 | bruts | I51 | accepté | accepté, vue : I51 | `tests/test_oms.py::test_changement_de_contenu_cree_une_version` |
| L1 | licences | D30, I54 | sans objet | accepté, aucune violation | `tests/test_sources.py::test_licence_retiree_garde_les_donnees_anterieures` |
| L2 | licences | D30, I54 | sans objet | accepté, vue : I54 | `tests/test_sources.py::test_jeu_non_publiable_non_ingere` |
| S1 | séries | I49 | accepté | rejeté | `(contrainte SQL)` |
| G1 | général | I1 | accepté, foreign_key_check | accepté, foreign_key_check | `tests/test_db.py::test_connexion_active_les_cles_etrangeres` |

## 3. Contre-exemples de l'arbitrage : détail

### CE-A1 · Un DON disparaît de l'API : écart 0 et retrait

Point A · invariant(s) I7, I9, I10 · résultat attendu : accepté, état cohérent (attendu)

Sur l'ancien schéma, la règle « seen_count = expected_count = nombre de reports_active » (architecture §3.2) échoue sur une exécution correcte dès qu'un DON disparaît ; le critère « DON ingérés = DON du site » ne redevient jamais vrai.

**Phase 1**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, error_kind)
VALUES (5, 'oms_don', '2026-10-12T05:47:00Z', '2026-10-12T05:50:00Z', 'succes', 'planifie', 'ce', 2, 2, NULL);
UPDATE reports SET last_seen_at = '2026-10-12T05:47:00Z' WHERE external_id IN ('guid-a', 'guid-b');
```

→ accepté ; aucun contrôle ne le détecte

```sql
SELECT (SELECT expected_count FROM ingestion_runs WHERE id = (SELECT max(id) FROM ingestion_runs
        WHERE source_code = 'oms_don')) AS total_api,
       (SELECT count(*) FROM reports_active) AS dons_actifs_en_base,
       (SELECT count(*) FROM reports) AS dons_ingeres;
```
| total_api | dons_actifs_en_base | dons_ingeres |
|---|---|---|
| 2 | 3 | 3 |

**Schéma corrigé**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, absent_count, removed_count, reappeared_count, error_kind)
VALUES (5, 'oms_don', '2026-10-12T05:47:00Z', '2026-10-12T05:50:00Z', 'succes', 'planifie', 'ce', 2, 2, 1, 0, 0, NULL);
UPDATE reports SET last_seen_run_id = 5 WHERE external_id IN ('guid-a', 'guid-b');
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, absent_count, removed_count, reappeared_count, error_kind)
VALUES (6, 'oms_don', '2026-10-13T05:47:00Z', '2026-10-13T05:50:00Z', 'partiel', 'planifie', 'ce', 2, 1, NULL, NULL, NULL, 'controle');
UPDATE reports SET last_seen_run_id = 6 WHERE external_id = 'guid-a';
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, absent_count, removed_count, reappeared_count, error_kind)
VALUES (7, 'oms_don', '2026-10-14T05:47:00Z', '2026-10-14T05:50:00Z', 'succes', 'planifie', 'ce', 2, 2, 1, 0, 0, NULL);
UPDATE reports SET last_seen_run_id = 7 WHERE external_id IN ('guid-a', 'guid-b');
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, absent_count, removed_count, reappeared_count, error_kind)
VALUES (8, 'oms_don', '2026-10-15T05:47:00Z', '2026-10-15T05:50:00Z', 'succes', 'planifie', 'ce', 2, 2, 1, 1, 0, NULL);
UPDATE reports SET last_seen_run_id = 8 WHERE external_id IN ('guid-a', 'guid-b');
UPDATE reports SET removed_run_id = 8 WHERE external_id = 'guid-c';
```

→ accepté ; aucune violation détectée

```sql
SELECT g.id AS derniere_execution, g.expected_count AS total_api, g.seen_count,
       (SELECT count(*) FROM reports AS r WHERE r.last_seen_run_id = g.id) AS presents_en_base,
       g.absent_count, g.removed_count
FROM ingestion_runs AS g WHERE g.id = (SELECT max(id) FROM ingestion_runs WHERE source_code = 'oms_don');
```
| derniere_execution | total_api | seen_count | presents_en_base | absent_count | removed_count |
|---|---|---|---|---|---|
| 8 | 2 | 2 | 2 | 1 | 1 |

```sql
SELECT slug, last_seen_run_id, missing_runs, presence, removed_run_id, expected_removed_run_id
FROM reports_presence ORDER BY report_id;
```
| slug | last_seen_run_id | missing_runs | presence | removed_run_id | expected_removed_run_id |
|---|---|---|---|---|---|
| 2026-DON620 | 8 | 0 | present | NULL | NULL |
| 2024-DON528 | 8 | 0 | present | NULL | NULL |
| 2022-DON398_1 | 1 | 3 | retire | 8 | 8 |

Test Python futur : `tests/test_oms.py::test_ecart_zero_sur_les_presents, ::test_retrait_a_la_troisieme_absence, ::test_execution_partielle_ne_compte_pas`

### CE-A2 · Retrait posé dès la première absence

Point A · invariant(s) I10 · résultat attendu : accepté, détecté par `controle_invariants`

Rien ne relie le retrait aux exécutions : un retrait prématuré passe.

**Phase 1**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, error_kind)
VALUES (5, 'oms_don', '2026-10-12T05:47:00Z', '2026-10-12T05:50:00Z', 'succes', 'planifie', 'ce', 2, 2, NULL);
UPDATE reports SET last_seen_at = '2026-10-12T05:47:00Z' WHERE external_id IN ('guid-a', 'guid-b');
UPDATE reports SET removed_at = '2026-10-12T05:50:00Z' WHERE external_id = 'guid-c';
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, absent_count, removed_count, reappeared_count, error_kind)
VALUES (5, 'oms_don', '2026-10-12T05:47:00Z', '2026-10-12T05:50:00Z', 'succes', 'planifie', 'ce', 2, 2, 1, 1, 0, NULL);
UPDATE reports SET last_seen_run_id = 5 WHERE external_id IN ('guid-a', 'guid-b');
UPDATE reports SET removed_run_id = 5 WHERE external_id = 'guid-c';
```

→ accepté ; détecté par `controle_invariants` : I10 (reports #3)

```sql
SELECT slug, last_seen_run_id, missing_runs, presence, removed_run_id, expected_removed_run_id
FROM reports_presence ORDER BY report_id;
```
| slug | last_seen_run_id | missing_runs | presence | removed_run_id | expected_removed_run_id |
|---|---|---|---|---|---|
| 2026-DON620 | 5 | 0 | present | NULL | NULL |
| 2024-DON528 | 5 | 0 | present | NULL | NULL |
| 2022-DON398_1 | 1 | 1 | absent | 5 | NULL |

Test Python futur : `tests/test_oms.py::test_retrait_a_la_troisieme_absence`

### CE-A3 · Retrait antérieur à la dernière présence

Point A · invariant(s) I10 · résultat attendu : rejeté par la base

Un DON peut être marqué retiré avant d'avoir été vu pour la dernière fois.

**Phase 1**

```sql
UPDATE reports SET removed_at = '2026-10-01T00:00:00Z' WHERE external_id = 'guid-c';
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
UPDATE reports SET removed_run_id = 1 WHERE external_id = 'guid-c';
```

→ rejeté : `IntegrityError: CHECK constraint failed: removed_run_id IS NULL OR removed_run_id > last_seen_run_id`

Test Python futur : `(contrainte SQL)`

### CE-A4 · Exécution « succes » avec un comptage incomplet

Point A · invariant(s) I7 · résultat attendu : rejeté par la base

Une exécution peut être marquée réussie alors qu'il manque des enregistrements.

**Phase 1**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, error_kind)
VALUES (5, 'oms_don', '2026-10-12T05:47:00Z', '2026-10-12T05:50:00Z', 'succes', 'planifie', 'ce', 3, 2, NULL);
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, absent_count, removed_count, reappeared_count, error_kind)
VALUES (5, 'oms_don', '2026-10-12T05:47:00Z', '2026-10-12T05:50:00Z', 'succes', 'planifie', 'ce', 3, 2, 0, 0, 0, NULL);
```

→ rejeté : `IntegrityError: CHECK constraint failed: status NOT IN ('succes', 'inchange') OR expected_count IS NULL OR seen_count = expected_count`

Test Python futur : `(contrainte SQL)`

### CE-A5 · DON reçu mais non écrit en base

Point A · invariant(s) I9 · résultat attendu : accepté, détecté par `controle_invariants`

L'ancien contrôle compare des totaux : un DON reçu mais non mis à jour reste compté comme présent.

**Phase 1**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, error_kind)
VALUES (5, 'oms_don', '2026-10-12T05:47:00Z', '2026-10-12T05:50:00Z', 'succes', 'planifie', 'ce', 3, 3, NULL);
UPDATE reports SET last_seen_at = '2026-10-12T05:47:00Z' WHERE external_id IN ('guid-a', 'guid-b');
```

→ accepté ; aucun contrôle ne le détecte

```sql
SELECT (SELECT expected_count FROM ingestion_runs WHERE id = (SELECT max(id) FROM ingestion_runs
        WHERE source_code = 'oms_don')) AS total_api,
       (SELECT count(*) FROM reports_active) AS dons_actifs_en_base,
       (SELECT count(*) FROM reports) AS dons_ingeres;
```
| total_api | dons_actifs_en_base | dons_ingeres |
|---|---|---|
| 3 | 3 | 3 |

**Schéma corrigé**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, absent_count, removed_count, reappeared_count, error_kind)
VALUES (5, 'oms_don', '2026-10-12T05:47:00Z', '2026-10-12T05:50:00Z', 'succes', 'planifie', 'ce', 3, 3, 0, 0, 0, NULL);
UPDATE reports SET last_seen_run_id = 5 WHERE external_id IN ('guid-a', 'guid-b');
```

→ accepté ; détecté par `controle_invariants` : I9 (ingestion_runs #5)

```sql
SELECT g.id AS derniere_execution, g.expected_count AS total_api, g.seen_count,
       (SELECT count(*) FROM reports AS r WHERE r.last_seen_run_id = g.id) AS presents_en_base,
       g.absent_count, g.removed_count
FROM ingestion_runs AS g WHERE g.id = (SELECT max(id) FROM ingestion_runs WHERE source_code = 'oms_don');
```
| derniere_execution | total_api | seen_count | presents_en_base | absent_count | removed_count |
|---|---|---|---|---|---|
| 5 | 3 | 3 | 2 | 0 | 0 |

Test Python futur : `tests/test_oms.py::test_ecart_zero_sur_les_presents`

### CE-A6 · Exécution OMS complète sans comptages

Point A · invariant(s) I8 · résultat attendu : rejeté par la base

Une exécution OMS réussie peut n'avoir ni total annoncé ni total reçu : l'écart n'est pas mesurable.

**Phase 1**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, error_kind)
VALUES (5, 'oms_don', '2026-10-12T05:47:00Z', '2026-10-12T05:50:00Z', 'succes', 'planifie', 'ce', NULL, NULL, NULL);
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, absent_count, removed_count, reappeared_count, error_kind)
VALUES (5, 'oms_don', '2026-10-12T05:47:00Z', '2026-10-12T05:50:00Z', 'succes', 'planifie', 'ce', NULL, NULL, NULL, NULL, NULL, NULL);
```

→ rejeté : `IntegrityError: CHECK constraint failed: source_code <> 'oms_don' OR status NOT IN ('succes', 'inchange') OR (expected_count IS NOT NULL AND seen_count IS NOT NULL)`

Test Python futur : `(contrainte SQL) ; Id distincts : tests/test_oms.py::test_pagination_complete_sans_doublon`

### CE-A7 · Deux exécutions en cours pour une même source

Point A · invariant(s) I5 · résultat attendu : rejeté par la base

Rien n'empêche deux exécutions simultanées de la même source.

**Phase 1**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, error_kind)
VALUES (5, 'oms_don', '2026-10-12T05:47:00Z', NULL, 'en_cours', 'planifie', 'ce', NULL, NULL, NULL);
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, error_kind)
VALUES (6, 'oms_don', '2026-10-12T05:47:00Z', NULL, 'en_cours', 'planifie', 'ce', NULL, NULL, NULL);
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, absent_count, removed_count, reappeared_count, error_kind)
VALUES (5, 'oms_don', '2026-10-12T05:47:00Z', NULL, 'en_cours', 'planifie', 'ce', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, absent_count, removed_count, reappeared_count, error_kind)
VALUES (6, 'oms_don', '2026-10-12T05:47:00Z', NULL, 'en_cours', 'planifie', 'ce', NULL, NULL, NULL, NULL, NULL, NULL);
```

→ rejeté : `IntegrityError: UNIQUE constraint failed: ingestion_runs.source_code`

Test Python futur : `(contrainte SQL)`

### CE-A8 · Exécution restée « en cours » dans la base envoyée

Point A · invariant(s) I6 · résultat attendu : accepté, détecté par `controle_invariants`

Une exécution interrompue sans être fermée reste en_cours.

**Phase 1**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, error_kind)
VALUES (5, 'oms_don', '2026-10-12T05:47:00Z', NULL, 'en_cours', 'planifie', 'ce', NULL, NULL, NULL);
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, absent_count, removed_count, reappeared_count, error_kind)
VALUES (5, 'oms_don', '2026-10-12T05:47:00Z', NULL, 'en_cours', 'planifie', 'ce', NULL, NULL, NULL, NULL, NULL, NULL);
```

→ accepté ; détecté par `controle_invariants` : I6 (ingestion_runs #5)

Test Python futur : `tests/test_pipeline.py::test_echec_de_source_ferme_l_execution`

### CE-R1 · Versions qui se chevauchent

Point B-révisions · invariant(s) I22 · résultat attendu : accepté, détecté par `controle_invariants`

La version 1 reste valide après l'ouverture de la version 2 : deux valeurs connues à la même date.

**Phase 1**

```sql
UPDATE observations SET valid_to = '2026-10-09T05:47:00Z' WHERE id = 1;
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
UPDATE observations SET valid_to = '2026-10-09T05:47:00Z' WHERE id = 1;
```

→ accepté ; détecté par `controle_invariants` : I22 (observations #1)

Test Python futur : `tests/test_observations.py::test_fermeture_egale_ouverture_suivante`

### CE-R2 · Trou dans la numérotation des versions

Point B-révisions · invariant(s) I21 · résultat attendu : accepté, détecté par `controle_invariants`

Une version 3 sans version 2.

**Phase 1**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by, code_version)
VALUES (5, 'sentinelles', '2026-10-14T05:47:00Z', '2026-10-14T05:50:00Z', 'succes', 'planifie', 'ce');
UPDATE observations SET valid_to = '2026-10-14T05:47:00Z' WHERE id = 3;
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (1, '2026-09-28', '2026-10-04', 2026, 40, 3, 72.0, '2026-10-14T05:47:00Z', NULL, 5, 5);
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by, code_version)
VALUES (5, 'sentinelles', '2026-10-14T05:47:00Z', '2026-10-14T05:50:00Z', 'succes', 'planifie', 'ce');
UPDATE observations SET valid_to = '2026-10-14T05:47:00Z' WHERE id = 3;
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (1, '2026-09-28', '2026-10-04', 2026, 40, 3, 72.0, '2026-10-14T05:47:00Z', NULL, 5, 5);
```

→ accepté ; détecté par `controle_invariants` : I21 (observations #3)

Test Python futur : `tests/test_observations.py::test_versions_numerotees_sans_trou`

### CE-R3 · Point sans version courante

Point B-révisions · invariant(s) I22 · résultat attendu : accepté, détecté par `controle_invariants`

La seule version d'un point est fermée sans successeur : le point disparaît de la série courante.

**Phase 1**

```sql
UPDATE observations SET valid_to = '2026-10-14T05:47:00Z' WHERE id = 3;
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
UPDATE observations SET valid_to = '2026-10-14T05:47:00Z' WHERE id = 3;
```

→ accepté ; détecté par `controle_invariants` : I22 (observations #3)

Test Python futur : `tests/test_observations.py::test_retrait_cree_une_version_nulle`

### CE-R4 · Version de durée nulle

Point B-révisions · invariant(s) I23 · résultat attendu : rejeté par la base

valid_to = valid_from : la version n'est visible à aucune date (requête « as-of »).

**Phase 1**

```sql
UPDATE observations SET valid_to = valid_from WHERE id = 1;
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
UPDATE observations SET valid_to = valid_from WHERE id = 1;
```

→ rejeté : `IntegrityError: CHECK constraint failed: valid_to IS NULL OR valid_to > valid_from`

Test Python futur : `(contrainte SQL)`

### CE-R5 · Nouvelle version identique à la précédente

Point B-révisions · invariant(s) I25 · résultat attendu : accepté, détecté par `controle_invariants`

Une révision sans changement de valeur fausse le décompte des révisions.

**Phase 1**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by, code_version)
VALUES (5, 'sentinelles', '2026-10-14T05:47:00Z', '2026-10-14T05:50:00Z', 'succes', 'planifie', 'ce');
UPDATE observations SET valid_to = '2026-10-14T05:47:00Z' WHERE id = 3;
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (1, '2026-09-28', '2026-10-04', 2026, 40, 2, 70.0, '2026-10-14T05:47:00Z', NULL, 5, 5);
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by, code_version)
VALUES (5, 'sentinelles', '2026-10-14T05:47:00Z', '2026-10-14T05:50:00Z', 'succes', 'planifie', 'ce');
UPDATE observations SET valid_to = '2026-10-14T05:47:00Z' WHERE id = 3;
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (1, '2026-09-28', '2026-10-04', 2026, 40, 2, 70.0, '2026-10-14T05:47:00Z', NULL, 5, 5);
```

→ accepté ; détecté par `controle_invariants` : I25 (observations #5)

Test Python futur : `tests/test_observations.py::test_valeur_inchangee_ne_cree_pas_de_version`

### CE-R6 · Valeur hors de son intervalle

Point B-révisions · invariant(s) I27 · résultat attendu : rejeté par la base

value = 70 avec un intervalle [75, 80].

**Phase 1**

```sql
UPDATE observations SET value_low = 75, value_up = 80 WHERE id = 3;
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
UPDATE observations SET value_low = 75, value_up = 80 WHERE id = 3;
```

→ rejeté : `IntegrityError: CHECK constraint failed: value_low IS NULL OR value >= value_low`

Test Python futur : `(contrainte SQL)`

### CE-R7 · Anomalie ouverte sur une version révisée

Point B-révisions · invariant(s) I28 · résultat attendu : accepté, détecté par `controle_invariants`

Une alerte peut porter sur une valeur que la source a déjà corrigée.

**Phase 1**

```sql
INSERT INTO anomalies (observation_id, method, method_version, parameters, observed_value,
    expected_value, threshold_value, severity, status, detected_at, code_version)
VALUES (1, 'baseline_saisonniere', '1', '{}', 60.0, 40.0, 55.0, 'elevee', 'ouverte', '2026-10-07T05:47:00Z', 'ce');
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO anomalies (observation_id, method, method_version, parameters, observed_value,
    expected_value, threshold_value, severity, status, detected_at, code_version)
VALUES (1, 'baseline_saisonniere', '1', '{}', 60.0, 40.0, 55.0, 'elevee', 'ouverte', '2026-10-07T05:47:00Z', 'ce');
```

→ accepté ; détecté par `controle_invariants` : I28 (anomalies #2)

Test Python futur : `tests/test_detection.py::test_revision_remplace_l_anomalie`

### CE-R8 · Version fermée réécrite

Point B-révisions · invariant(s) I26 · résultat attendu : accepté, **non détecté dans la base** : contrôle de relecture des bruts (phase 2, D31)

La valeur d'une version déjà fermée est modifiée : l'historique est falsifié sans trace.

**Phase 1**

```sql
UPDATE observations SET value = 99 WHERE id = 1;
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
UPDATE observations SET value = 99 WHERE id = 1;
```

→ accepté ; aucune violation détectée

Test Python futur : `tests/test_observations.py::test_ecriture_par_ajout_seul, tests/test_controle.py::test_relecture_detecte_valeur_reecrite`

### CE-R9 · valid_from différent du début d'exécution

Point B-révisions · invariant(s) I24 · résultat attendu : accepté, détecté par `controle_invariants`

La date de validité ne correspond à aucune exécution : le « vintage » n'est pas reproductible.

**Phase 1**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (1, '2026-10-05', '2026-10-11', 2026, 41, 1, 75.0, '2026-10-07T17:18:00Z', NULL, 3, 5);
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (1, '2026-10-05', '2026-10-11', 2026, 41, 1, 75.0, '2026-10-07T17:18:00Z', NULL, 3, 5);
```

→ accepté ; détecté par `controle_invariants` : I24 (observations #5)

Test Python futur : `tests/test_observations.py::test_valid_from_egale_debut_d_execution`

### CE-R10 · Anomalie qui ne reprend pas la valeur évaluée

Point B-révisions · invariant(s) I29 · résultat attendu : accepté, détecté par `controle_invariants`

La valeur affichée dans l'alerte diffère de la valeur en base.

**Phase 1**

```sql
UPDATE anomalies SET observed_value = 64 WHERE id = 1;
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
UPDATE anomalies SET observed_value = 64 WHERE id = 1;
```

→ accepté ; détecté par `controle_invariants` : I29 (anomalies #1)

Test Python futur : `tests/test_detection.py::test_anomalie_reprend_la_valeur_observee`

### CE-W1 · Année au format YYYYWW

Point B-semaines · invariant(s) I30 · résultat attendu : rejeté par la base

La semaine Sentiweb '202641' rangée telle quelle dans iso_year.

**Phase 1**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (1, '2026-10-05', '2026-10-11', 202641, 41, 1, 75.0, '2026-10-07T05:47:00Z', NULL, 3, 5);
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (1, '2026-10-05', '2026-10-11', 202641, 41, 1, 75.0, '2026-10-07T05:47:00Z', NULL, 3, 5);
```

→ rejeté : `IntegrityError: CHECK constraint failed: iso_year BETWEEN 1950 AND 2100`

Test Python futur : `(contrainte SQL)`

### CE-W2 · Point annuel dans une série hebdomadaire

Point B-semaines · invariant(s) I31 · résultat attendu : accepté, détecté par `controle_invariants`

iso_week NULL dans une série semaine_iso.

**Phase 1**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (1, '2026-01-01', '2026-12-31', 2026, NULL, 1, 75.0, '2026-10-07T05:47:00Z', NULL, 3, 5);
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (1, '2026-01-01', '2026-12-31', 2026, NULL, 1, 75.0, '2026-10-07T05:47:00Z', NULL, 3, 5);
```

→ accepté ; détecté par `controle_invariants` : I31 (observations #5)

Test Python futur : `tests/test_semaines.py::test_type_de_periode_coherent`

### CE-W3 · Semaine dans une série annuelle

Point B-semaines · invariant(s) I31 · résultat attendu : accepté, détecté par `controle_invariants`

iso_week renseignée dans une série annee.

**Phase 1**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (2, '2026-09-28', '2026-10-04', 2026, 40, 1, 1.0, '2026-10-08T05:47:00Z', NULL, 4, 6);
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (2, '2026-09-28', '2026-10-04', 2026, 40, 1, 1.0, '2026-10-08T05:47:00Z', NULL, 4, 6);
```

→ accepté ; détecté par `controle_invariants` : I31 (observations #5)

Test Python futur : `tests/test_semaines.py::test_type_de_periode_coherent`

### CE-W4 · Point annuel qui ne couvre pas l'année

Point B-semaines · invariant(s) I32 · résultat attendu : rejeté par la base

Période 2024-03-01 → 2024-12-31 pour l'année 2024.

**Phase 1**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (2, '2024-03-01', '2024-12-31', 2024, NULL, 1, 1.0, '2026-10-08T05:47:00Z', NULL, 4, 6);
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (2, '2024-03-01', '2024-12-31', 2024, NULL, 1, 1.0, '2026-10-08T05:47:00Z', NULL, 4, 6);
```

→ rejeté : `IntegrityError: CHECK constraint failed: iso_week IS NOT NULL OR (period_start = CAST(iso_year AS TEXT) || '-01-01' AND period_end = CAST(iso_year AS TEXT) || '-12-31')`

Test Python futur : `(contrainte SQL)`

### CE-W5 · Début de semaine qui n'est pas un lundi

Point B-semaines · invariant(s) I33 · résultat attendu : rejeté par la base

Semaine 41 de 2026 rangée au mardi 2026-10-06.

**Phase 1**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (1, '2026-10-06', '2026-10-12', 2026, 41, 1, 75.0, '2026-10-07T05:47:00Z', NULL, 3, 5);
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (1, '2026-10-06', '2026-10-12', 2026, 41, 1, 75.0, '2026-10-07T05:47:00Z', NULL, 3, 5);
```

→ rejeté : `IntegrityError: CHECK constraint failed: iso_week IS NULL OR ( strftime('%w', period_start) = '1' AND period_end = date(period_start, '+6 days') AND CAST(strftime('%Y', period_start, '+3 days') AS INTEGER) = iso_year AND (CAST(strftime('%j', period_start, '+3 days') AS INTEGER) - 1) / 7 + 1 = iso_week)`

Test Python futur : `(contrainte SQL) ; tests/test_semaines.py::test_lundi_de_la_semaine_iso`

### CE-W6 · Semaine 53 d'une année qui n'en a que 52

Point B-semaines · invariant(s) I33 · résultat attendu : rejeté par la base

2025-W53 n'existe pas (2025 commence un mercredi).

**Phase 1**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (1, '2025-12-29', '2026-01-04', 2025, 53, 1, 75.0, '2026-10-07T05:47:00Z', NULL, 3, 5);
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (1, '2025-12-29', '2026-01-04', 2025, 53, 1, 75.0, '2026-10-07T05:47:00Z', NULL, 3, 5);
```

→ rejeté : `IntegrityError: CHECK constraint failed: iso_week IS NULL OR ( strftime('%w', period_start) = '1' AND period_end = date(period_start, '+6 days') AND CAST(strftime('%Y', period_start, '+3 days') AS INTEGER) = iso_year AND (CAST(strftime('%j', period_start, '+3 days') AS INTEGER) - 1) / 7 + 1 = iso_week)`

Test Python futur : `(contrainte SQL) ; tests/test_semaines.py::test_semaine_53_refusee_si_annee_a_52_semaines`

### CE-W7 · Année civile au lieu de l'année ISO

Point B-semaines · invariant(s) I33 · résultat attendu : rejeté par la base

La semaine du lundi 2025-12-29 est 2026-W01 ; elle est rangée en 2025-W01.

**Phase 1**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (1, '2025-12-29', '2026-01-04', 2025, 1, 1, 75.0, '2026-10-07T05:47:00Z', NULL, 3, 5);
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (1, '2025-12-29', '2026-01-04', 2025, 1, 1, 75.0, '2026-10-07T05:47:00Z', NULL, 3, 5);
```

→ rejeté : `IntegrityError: CHECK constraint failed: iso_week IS NULL OR ( strftime('%w', period_start) = '1' AND period_end = date(period_start, '+6 days') AND CAST(strftime('%Y', period_start, '+3 days') AS INTEGER) = iso_year AND (CAST(strftime('%j', period_start, '+3 days') AS INTEGER) - 1) / 7 + 1 = iso_week)`

Test Python futur : `(contrainte SQL) ; tests/test_semaines.py::test_annee_iso_differente_de_l_annee_civile`

### CE-W8 · Fin de semaine fausse

Point B-semaines · invariant(s) I33 · résultat attendu : rejeté par la base

Semaine 41 fermée le samedi 2026-10-10.

**Phase 1**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (1, '2026-10-05', '2026-10-10', 2026, 41, 1, 75.0, '2026-10-07T05:47:00Z', NULL, 3, 5);
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (1, '2026-10-05', '2026-10-10', 2026, 41, 1, 75.0, '2026-10-07T05:47:00Z', NULL, 3, 5);
```

→ rejeté : `IntegrityError: CHECK constraint failed: iso_week IS NULL OR ( strftime('%w', period_start) = '1' AND period_end = date(period_start, '+6 days') AND CAST(strftime('%Y', period_start, '+3 days') AS INTEGER) = iso_year AND (CAST(strftime('%j', period_start, '+3 days') AS INTEGER) - 1) / 7 + 1 = iso_week)`

Test Python futur : `(contrainte SQL) ; tests/test_semaines.py::test_lundi_de_la_semaine_iso`

### CE-X1 · DON rattaché à un brut Sentinelles

Point B-références · invariant(s) I13 · résultat attendu : rejeté par la base

reports.raw_payload_id pointe vers un brut d'une autre source.

**Phase 1**

```sql
UPDATE reports SET raw_payload_id = 4 WHERE external_id = 'guid-a';
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
UPDATE reports SET raw_payload_id = 4 WHERE external_id = 'guid-a';
```

→ rejeté : `IntegrityError: FOREIGN KEY constraint failed`

Test Python futur : `(contrainte SQL)`

### CE-X2 · DON rattaché au brut d'un autre DON

Point B-références · invariant(s) I13 · résultat attendu : rejeté par la base

Le DON a pointe vers la version brute du DON b.

**Phase 1**

```sql
UPDATE reports SET raw_payload_id = 2 WHERE external_id = 'guid-a';
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
UPDATE reports SET raw_payload_id = 2 WHERE external_id = 'guid-a';
```

→ rejeté : `IntegrityError: FOREIGN KEY constraint failed`

Test Python futur : `(contrainte SQL)`

### CE-X3 · Brut OMS attribué à une exécution Sentinelles

Point B-références · invariant(s) I12 · résultat attendu : rejeté par la base

raw_payloads.first_run_id désigne une exécution d'une autre source.

**Phase 1**

```sql
INSERT INTO raw_payloads (source_code, resource_key, request_url, content_type, sha256, byte_size,
    body_text, first_run_id, retrieved_at)
VALUES ('oms_don', 'guid-d', 'u', 'application/json', '0000000000000000000000000000000000000000000000000000000000000000', 2, '{}', 2, '2026-10-11T05:47:00Z');
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO raw_payloads (source_code, resource_key, request_url, content_type, sha256, byte_size,
    body_text, first_run_id, retrieved_at)
VALUES ('oms_don', 'guid-d', 'u', 'application/json', '0000000000000000000000000000000000000000000000000000000000000000', 2, '{}', 2, '2026-10-11T05:47:00Z');
```

→ rejeté : `IntegrityError: FOREIGN KEY constraint failed`

Test Python futur : `(contrainte SQL)`

### CE-X4 · Observation Sentinelles attribuée à une exécution OMS

Point B-références · invariant(s) I15 · résultat attendu : accepté, détecté par `controle_invariants`

observations.run_id désigne une exécution d'une autre source que la série.

**Phase 1**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (1, '2026-10-05', '2026-10-11', 2026, 41, 1, 75.0, '2026-10-11T05:47:00Z', NULL, 1, 5);
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (1, '2026-10-05', '2026-10-11', 2026, 41, 1, 75.0, '2026-10-11T05:47:00Z', NULL, 1, 5);
```

→ accepté ; détecté par `controle_invariants` : I15 (observations #5)

Test Python futur : `tests/test_observations.py::test_observation_rattachee_a_la_source_de_sa_serie`

### CE-X5 · Observation Sentinelles rattachée à un brut OMS

Point B-références · invariant(s) I15 · résultat attendu : accepté, détecté par `controle_invariants`

observations.raw_payload_id désigne un brut d'une autre source que la série.

**Phase 1**

```sql
UPDATE observations SET raw_payload_id = 1 WHERE id = 3;
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
UPDATE observations SET raw_payload_id = 1 WHERE id = 3;
```

→ accepté ; détecté par `controle_invariants` : I15 (observations #3)

Test Python futur : `tests/test_observations.py::test_observation_rattachee_a_la_source_de_sa_serie`

### CE-X6 · DON « vu » par une exécution Sentinelles

Point B-références · invariant(s) I14 · résultat attendu : rejeté par la base

Sans objet dans l'ancien schéma (le DON n'était pas relié à une exécution).

**Phase 1** : sans objet.

**Schéma corrigé**

```sql
UPDATE reports SET last_seen_run_id = 2 WHERE external_id = 'guid-a';
```

→ rejeté : `IntegrityError: FOREIGN KEY constraint failed`

Test Python futur : `(contrainte SQL)`

### CE-X7 · Chiffre lu dans la version d'un autre DON

Point B-références · invariant(s) I16 · résultat attendu : accepté, détecté par `controle_invariants`

Sans objet dans l'ancien schéma (pas de lien chiffre → version brute).

**Phase 1** : sans objet.

**Schéma corrigé**

```sql
INSERT INTO report_figures (report_id, raw_payload_id, country_iso3, measure, case_definition,
    period_start, as_of, value, method, status, evidence, extractor_version)
VALUES (2, 1, 'BDI', 'deces', 'confirme', NULL, '2024-08-17', 0, 'regle', 'auto', 'No deaths were reported as of 17 August.', 'regle-0');
```

→ accepté ; détecté par `controle_invariants` : I16 (report_figures #3)

Test Python futur : `tests/test_chiffres.py::test_chiffre_rattache_a_une_version_de_son_don`

### CE-X8 · Chiffre pour un pays que le DON ne cite pas

Point B-références · invariant(s) I17 · résultat attendu : rejeté par la base

Sans objet dans l'ancien schéma (pas de chiffre par pays).

**Phase 1** : sans objet.

**Schéma corrigé**

```sql
INSERT INTO report_figures (report_id, raw_payload_id, country_iso3, measure, case_definition,
    period_start, as_of, value, method, status, evidence, extractor_version)
VALUES (2, 2, 'UGA', 'cas', 'confirme', NULL, '2024-08-12', 2, 'regle', 'auto', 'two of which tested positive for MPXV Clade Ib', 'regle-0');
```

→ rejeté : `IntegrityError: FOREIGN KEY constraint failed`

Test Python futur : `(contrainte SQL)`

### CE-C1 · Relance dans la même base : même clé de déduplication

Point C · invariant(s) I44 · résultat attendu : rejeté par la base

La déduplication fonctionne quand la base de départ connaît l'envoi.

**Phase 1**

```sql
INSERT INTO alerts_log (alert_type, channel, dedup_key, anomaly_id, report_id, run_id, message,
    status, attempts, created_at, sent_at, last_error)
VALUES ('anomalie', 'telegram', 'anomalie:sentinelles:inc-3-PAY-ds2:inc100:FR-MET:2026-09-21:v2:baseline_saisonniere@1', 1, NULL, NULL, 'Grippe : hausse S39', 'a_envoyer', 0, '2026-10-14T05:47:00Z', NULL, NULL);
```

→ rejeté : `IntegrityError: UNIQUE constraint failed: alerts_log.channel, alerts_log.dedup_key`

**Schéma corrigé**

```sql
INSERT INTO alerts_log (alert_type, channel, dedup_key, anomaly_id, report_id, run_id, message,
    status, attempts, created_at, sent_at, last_error)
VALUES ('anomalie', 'telegram', 'anomalie:sentinelles:inc-3-PAY-ds2:inc100:FR-MET:2026-09-21:v2:baseline_saisonniere@1', 1, NULL, NULL, 'Grippe : hausse S39', 'a_envoyer', 0, '2026-10-14T05:47:00Z', NULL, NULL);
```

→ rejeté : `IntegrityError: UNIQUE constraint failed: alerts_log.channel, alerts_log.dedup_key`

Test Python futur : `(contrainte SQL)`

### CE-C2 · Relance après échec de l'envoi de la base

Point C · invariant(s) D19, R14 · résultat attendu : accepté **par conception** (risque documenté)

L'alerte a été envoyée à Telegram mais la base qui le note n'a pas été publiée : la relance repart de la base de la veille, qui ne connaît pas l'envoi. La même alerte est réécrite et renvoyée.

**Phase 1**

```sql
INSERT INTO alerts_log (alert_type, channel, dedup_key, anomaly_id, report_id, run_id, message,
    status, attempts, created_at, sent_at, last_error)
VALUES ('nouveau_rapport', 'telegram', 'nouveau_rapport:oms_don:guid-a', NULL, 1, NULL, 'Nouveau DON : 2026-DON620', 'a_envoyer', 0, '2026-10-11T05:47:00Z', NULL, NULL);
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO alerts_log (alert_type, channel, dedup_key, anomaly_id, report_id, run_id, message,
    status, attempts, created_at, sent_at, last_error)
VALUES ('nouveau_rapport', 'telegram', 'nouveau_rapport:oms_don:guid-a', NULL, 1, NULL, 'Nouveau DON : 2026-DON620', 'a_envoyer', 0, '2026-10-11T05:47:00Z', NULL, NULL);
```

→ accepté ; aucune violation détectée

Test Python futur : `tests/test_alertes.py::test_alerte_journalisee_avant_envoi`

### CE-C3 · Échec d'envoi sans tentative ni erreur

Point C · invariant(s) I47 · résultat attendu : rejeté par la base

Une alerte en echec sans message d'erreur ni tentative.

**Phase 1**

```sql
INSERT INTO alerts_log (alert_type, channel, dedup_key, anomaly_id, report_id, run_id, message,
    status, attempts, created_at, sent_at, last_error)
VALUES ('source_en_echec', 'telegram', 'source_en_echec:sentinelles:2026-10-14', NULL, NULL, 2, 'Sentinelles en échec', 'echec', 0, '2026-10-14T05:47:00Z', NULL, NULL);
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO alerts_log (alert_type, channel, dedup_key, anomaly_id, report_id, run_id, message,
    status, attempts, created_at, sent_at, last_error)
VALUES ('source_en_echec', 'telegram', 'source_en_echec:sentinelles:2026-10-14', NULL, NULL, 2, 'Sentinelles en échec', 'echec', 0, '2026-10-14T05:47:00Z', NULL, NULL);
```

→ rejeté : `IntegrityError: CHECK constraint failed: status = 'a_envoyer' OR attempts >= 1`

Test Python futur : `(contrainte SQL)`

### CE-C4 · Alerte envoyée sans tentative

Point C · invariant(s) I47 · résultat attendu : rejeté par la base

status envoyee avec attempts = 0.

**Phase 1**

```sql
UPDATE alerts_log SET attempts = 0 WHERE id = 1;
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
UPDATE alerts_log SET attempts = 0 WHERE id = 1;
```

→ rejeté : `IntegrityError: CHECK constraint failed: status = 'a_envoyer' OR attempts >= 1`

Test Python futur : `(contrainte SQL)`

### CE-C5 · Alerte envoyée avant d'être créée

Point C · invariant(s) I47 · résultat attendu : rejeté par la base

sent_at antérieur à created_at.

**Phase 1**

```sql
UPDATE alerts_log SET sent_at = '2026-10-01T00:00:00Z' WHERE id = 1;
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
UPDATE alerts_log SET sent_at = '2026-10-01T00:00:00Z' WHERE id = 1;
```

→ rejeté : `IntegrityError: CHECK constraint failed: sent_at IS NULL OR sent_at >= created_at`

Test Python futur : `(contrainte SQL)`

### CE-D1 · DON multi-pays (2024-DON528) : un chiffre par pays

Point D · invariant(s) D23 · résultat attendu : accepté, état cohérent (attendu)

Constat 1 : un seul couple cas/décès par DON. Trois pays écrits, un seul conservé.

**Phase 1**

```sql
UPDATE reports SET cases = 142, deaths = NULL, figures_as_of = '2024-08-17', figures_method = 'regle',
    figures_status = 'auto', figures_evidence = 'Burundi' WHERE slug = '2024-DON528';
UPDATE reports SET cases = 1, deaths = NULL, figures_as_of = '2024-08-13', figures_method = 'regle',
    figures_status = 'auto', figures_evidence = 'Kenya' WHERE slug = '2024-DON528';
UPDATE reports SET cases = 4, deaths = 0, figures_as_of = '2024-08-07', figures_method = 'regle',
    figures_status = 'auto', figures_evidence = 'Rwanda' WHERE slug = '2024-DON528';
```

→ accepté ; aucun contrôle ne le détecte

```sql
SELECT slug, cases, deaths, figures_as_of, figures_evidence FROM reports WHERE slug = '2024-DON528';
```
| slug | cases | deaths | figures_as_of | figures_evidence |
|---|---|---|---|---|
| 2024-DON528 | 4 | 0 | 2024-08-07 | Rwanda |

**Schéma corrigé**

```sql
INSERT INTO report_figures (report_id, raw_payload_id, country_iso3, measure, case_definition,
    period_start, as_of, value, method, status, evidence, extractor_version)
VALUES (2, 2, 'RWA', 'cas', 'confirme', NULL, '2024-08-07', 4, 'regle', 'auto', 'four confirmed mpox cases and zero deaths', 'regle-0');
INSERT INTO report_figures (report_id, raw_payload_id, country_iso3, measure, case_definition,
    period_start, as_of, value, method, status, evidence, extractor_version)
VALUES (2, 2, 'RWA', 'deces', 'confirme', NULL, '2024-08-07', 0, 'regle', 'auto', 'four confirmed mpox cases and zero deaths', 'regle-0');
```

→ accepté ; aucune violation détectée

```sql
SELECT country_iso3, measure, case_definition, as_of, value
FROM report_figures_current WHERE report_id = 2 ORDER BY country_iso3, measure;
```
| country_iso3 | measure | case_definition | as_of | value |
|---|---|---|---|---|
| BDI | cas | confirme | 2024-08-17 | 142 |
| KEN | cas | confirme | 2024-08-13 | 1 |
| RWA | cas | confirme | 2024-08-07 | 4 |
| RWA | deces | confirme | 2024-08-07 | 0 |

Test Python futur : `tests/test_chiffres.py::test_un_chiffre_par_pays_et_par_mesure`

### CE-D2 · Coût d'un passage tardif à une table de chiffres

Point D · invariant(s) D23 · résultat attendu : rejeté par la base

SQLite ne peut pas supprimer une colonne citée par une contrainte CHECK de table : passer à report_figures après la phase 3 imposerait de reconstruire reports.

**Phase 1**

```sql
ALTER TABLE reports DROP COLUMN cases;
```

→ rejeté : `OperationalError: error in table reports after drop column: no such column: cases`

**Schéma corrigé** : sans objet.

Test Python futur : `(sans objet)`

### CE-D3 · Chiffre extrait par LLM marqué « auto »

Point D · invariant(s) I35 · résultat attendu : rejeté par la base

Règle de CONTEXTE ; déjà appliquée par l'ancien schéma, conservée.

**Phase 1**

```sql
UPDATE reports SET cases = 10, figures_method = 'llm', figures_status = 'auto',
    figures_evidence = 'x' WHERE slug = '2026-DON620';
```

→ rejeté : `IntegrityError: CHECK constraint failed: figures_method <> 'llm' OR figures_status IN ('incertain', 'valide')`

**Schéma corrigé**

```sql
INSERT INTO report_figures (report_id, raw_payload_id, country_iso3, measure, case_definition,
    period_start, as_of, value, method, status, evidence, extractor_version)
VALUES (1, 1, 'RUS', 'deces', 'total', NULL, '2026-10-02', 1, 'llm', 'auto', 'confirmed the death', 'llm-0');
```

→ rejeté : `IntegrityError: CHECK constraint failed: method <> 'llm' OR status IN ('incertain', 'valide')`

Test Python futur : `(contrainte SQL)`

### CE-D4 · Chiffre « ensemble du rapport » en double

Point D · invariant(s) I36 · résultat attendu : rejeté par la base

Sans objet dans l'ancien schéma. Montre l'utilité du COALESCE dans l'index unique (NULL ≠ NULL).

**Phase 1** : sans objet.

**Schéma corrigé**

```sql
INSERT INTO report_figures (report_id, raw_payload_id, country_iso3, measure, case_definition,
    period_start, as_of, value, method, status, evidence, extractor_version)
VALUES (3, 3, NULL, 'cas', 'total', '2022-01-01', '2022-07-10', 7796, 'regle', 'auto', 'a cumulative number of 7796 cases of cholera', 'regle-0');
INSERT INTO report_figures (report_id, raw_payload_id, country_iso3, measure, case_definition,
    period_start, as_of, value, method, status, evidence, extractor_version)
VALUES (3, 3, NULL, 'cas', 'total', '2022-01-01', '2022-07-10', 7796, 'regle', 'auto', 'a cumulative number of 7796 cases of cholera', 'regle-0');
```

→ rejeté : `IntegrityError: UNIQUE constraint failed: index 'report_figures_one_value'`

Test Python futur : `(contrainte SQL)`

### CE-P1 · Purge du JSON brut d'un DON

Point bruts · invariant(s) I53 · résultat attendu : rejeté par la base

Le JSON brut OMS doit être conservé ; la purge est réservée aux exports volumineux.

**Phase 1**

```sql
UPDATE raw_payloads SET body_text = NULL, purged_at = '2026-10-12T00:00:00Z' WHERE id = 1;
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
UPDATE raw_payloads SET body_text = NULL, purged_at = '2026-10-12T00:00:00Z' WHERE id = 1;
```

→ rejeté : `IntegrityError: CHECK constraint failed: purged_at IS NULL OR (source_code = 'spf_odisse' AND content_type = 'text/csv')`

Test Python futur : `(contrainte SQL)`

### CE-V1 · Contenu courant changé sans nouvelle version

Point bruts · invariant(s) I51 · résultat attendu : accepté, détecté par `controle_invariants`

reports.raw_payload_id change sans ligne dans la chronologie : le changement n'est pas daté.

**Phase 1**

```sql
INSERT INTO raw_payloads (source_code, resource_key, request_url, content_type, sha256, byte_size,
    body_text, first_run_id, retrieved_at)
VALUES ('oms_don', 'guid-a', 'u', 'application/json', '1111111111111111111111111111111111111111111111111111111111111111', 2, '{}', 1, '2026-10-11T05:47:00Z');
UPDATE reports SET raw_payload_id = (SELECT max(id) FROM raw_payloads) WHERE external_id = 'guid-a';
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO raw_payloads (source_code, resource_key, request_url, content_type, sha256, byte_size,
    body_text, first_run_id, retrieved_at)
VALUES ('oms_don', 'guid-a', 'u', 'application/json', '1111111111111111111111111111111111111111111111111111111111111111', 2, '{}', 1, '2026-10-11T05:47:00Z');
UPDATE reports SET raw_payload_id = (SELECT max(id) FROM raw_payloads) WHERE external_id = 'guid-a';
```

→ accepté ; détecté par `controle_invariants` : I51 (reports #1)

Test Python futur : `tests/test_oms.py::test_changement_de_contenu_cree_une_version`

### CE-L1 · Licence retirée après collecte : données antérieures gardées

Point licences · invariant(s) D30, I54 · résultat attendu : accepté, état cohérent (attendu)

La Licence Ouverte 2.0 accorde un droit sans limite de durée : les observations collectées avant le changement restent publiables.

**Phase 1** : sans objet.

**Schéma corrigé**

```sql
UPDATE datasets SET is_publishable = 0, not_publishable_since = '2026-10-14T00:00:00Z',
    license_note = 'Licence retirée du catalogue le 2026-10-14.'
WHERE dataset = 'rougeole-donnees-declaration-obligatoire';
```

→ accepté ; aucune violation détectée

Test Python futur : `tests/test_sources.py::test_licence_retiree_garde_les_donnees_anterieures`

### CE-L2 · Observation collectée après le retrait de licence

Point licences · invariant(s) D30, I54 · résultat attendu : accepté, détecté par `controle_invariants`

La collecte doit s'arrêter à not_publishable_since.

**Phase 1** : sans objet.

**Schéma corrigé**

```sql
UPDATE datasets SET is_publishable = 0, not_publishable_since = '2026-10-14T00:00:00Z',
    license_note = 'Licence retirée du catalogue le 2026-10-14.'
WHERE dataset = 'rougeole-donnees-declaration-obligatoire';
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by, code_version)
VALUES (5, 'spf_odisse', '2026-10-15T05:47:00Z', '2026-10-15T05:50:00Z', 'succes', 'planifie', 'ce');
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (2, '2026-01-01', '2026-12-31', 2026, NULL, 1, 2.0, '2026-10-15T05:47:00Z', NULL, 5, 6);
```

→ accepté ; détecté par `controle_invariants` : I54 (observations #5)

Test Python futur : `tests/test_sources.py::test_jeu_non_publiable_non_ingere`

### CE-S1 · Série Sentinelles en France entière

Point séries · invariant(s) I49 · résultat attendu : rejeté par la base

Sentinelles ne couvre que la métropole (D22) ; une série 'FR' mélangerait deux périmètres.

**Phase 1**

```sql
INSERT INTO series (source_code, dataset, metric, disease_code, geo_level, geo_code, geo_label,
    period_type, value_kind, unit, case_status, date_basis)
VALUES ('sentinelles', 'inc-3-PAY-ds2', 'inc', 'grippe', 'pays', 'FR', 'France', 'semaine_iso',
    'incidence', 'cas', 'syndromique', 'consultation');
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
INSERT INTO series (source_code, dataset, metric, disease_code, geo_level, geo_code, geo_label,
    period_type, value_kind, unit, case_status, date_basis)
VALUES ('sentinelles', 'inc-3-PAY-ds2', 'inc', 'grippe', 'pays', 'FR', 'France', 'semaine_iso',
    'incidence', 'cas', 'syndromique', 'consultation');
```

→ rejeté : `IntegrityError: CHECK constraint failed: source_code <> 'sentinelles' OR geo_code <> 'FR'`

Test Python futur : `(contrainte SQL)`

### CE-G1 · Connexion sans PRAGMA foreign_keys

Point général · invariant(s) I1 · résultat attendu : accepté, détecté par `PRAGMA foreign_key_check`

Toutes les clés étrangères (dont les clés composites I12-I17) sont inertes sur une connexion qui n'a pas exécuté le PRAGMA.

**Phase 1**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (999, '2026-10-05', '2026-10-11', 2026, 41, 1, 75.0, '2026-10-07T05:47:00Z', NULL, 3, 5);
```

→ accepté ; détecté par `PRAGMA foreign_key_check` : 1 violation(s)

**Schéma corrigé**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (999, '2026-10-05', '2026-10-11', 2026, 41, 1, 75.0, '2026-10-07T05:47:00Z', NULL, 3, 5);
```

→ accepté ; détecté par `PRAGMA foreign_key_check` : 1 violation(s)

Test Python futur : `tests/test_db.py::test_connexion_active_les_cles_etrangeres`

## 4. Preuves du relecteur : synthèse

22 preuves rejouées. Phase 1 : **20 acceptés sur 21** applicables. Schéma corrigé (22 applicables) :

- rejeté par la base : **8**
- accepté, détecté par `controle_invariants` : **5**
- accepté **par conception** (risque documenté) : **1**
- accepté, état cohérent (attendu) : **4**
- constat hors schéma : même résultat sur les deux schémas : **4**

Écarts entre résultat attendu et résultat obtenu : **aucun**.

| Code | Point | Invariant | Phase 1 (`e8f65a6`) | Schéma corrigé | Couverture Python |
|---|---|---|---|---|---|
| K1a | constat 1 | D24, I9, I10 | accepté | accepté, aucune violation | `tests/test_oms.py::test_ecart_zero_sur_les_presents` |
| K1b | constat 1 | I8, I9 | accepté | accepté, vue : I9 | `tests/test_oms.py::test_pagination_complete_sans_doublon` |
| K2 | constat 2 | D23 | accepté | accepté, aucune violation | `tests/test_chiffres.py::test_un_chiffre_par_pays_et_par_mesure` |
| K3 | constat 3 | I22, I24 | accepté | accepté, vue : I22, I24 | `tests/test_observations.py::test_fermeture_egale_ouverture_suivante` |
| K4 | constat 4 | I50 | accepté | accepté, aucune violation | `tests/test_observations.py::test_revision_des_bornes_cree_une_version` |
| K5 | constat 5 | D26, I51, I52 | accepté | accepté, aucune violation | `tests/test_oms.py::test_retour_a_un_contenu_anterieur_cree_une_version` |
| K6a | constat 6 | I33 | accepté | rejeté | `(contrainte SQL)` |
| K6b | constat 6 | I33 | accepté | rejeté | `(contrainte SQL)` |
| K6c | constat 6 | Q9 | accepté | accepté, aucune violation | `tests/test_detection.py::test_semaine_53_regle_de_reference` |
| K7a | constat 7 | I15 | accepté | accepté, vue : I15 | `tests/test_observations.py::test_observation_rattachee_a_la_source_de_sa_serie` |
| K7b | constat 7 | I13 | accepté | rejeté | `(contrainte SQL)` |
| K8 | constat 8 | R11 | accepté | accepté, aucune violation | `tests/test_classification.py::test_pays_lus_dans_le_texte_regional` |
| K9 | constat 9 | D27, I54 | accepté | accepté, vue : I54 | `tests/test_sources.py::test_jeu_sans_licence_non_ingere` |
| K10a | constat 10 | I27 | accepté | rejeté | `(contrainte SQL)` |
| K10b | constat 10 | I55 | accepté | rejeté | `(contrainte SQL)` |
| K10c | constat 10 | I56 | sans objet | accepté, vue : I56 | `tests/test_observations.py::test_valeur_dans_le_domaine_de_la_serie` |
| K11a | constat 11 | I2 | accepté | rejeté | `(contrainte SQL)` |
| K11b | constat 11 | I2 | rejeté | rejeté | `(contrainte SQL)` |
| K12 | constat 12 | D19, R14 | accepté | accepté, aucune violation | `tests/test_alertes.py::test_alerte_journalisee_avant_envoi` |
| K13 | constat 13 | R16, I58 | accepté | accepté, aucune violation | `tests/test_pipeline.py::test_taille_de_l_asset_bornee` |
| K14a | constat 14 | architecture §6 | accepté | accepté, aucune violation | `(migration)` |
| K14b | constat 14 | I59 | accepté | rejeté | `(contrainte SQL)` |

## 5. Preuves du relecteur : détail

### K1a · Comptage OMS contre retrait après trois absences

Point constat 1 · invariant(s) D24, I9, I10 · résultat attendu : accepté, état cohérent (attendu)

Règle de la phase 1 : seen = expected = nombre de reports_active. Un DON sur 5 disparaît de l'API.

**Phase 1**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, error_kind)
VALUES (4, 'oms_don', '2026-10-02T00:00:00Z', '2026-10-02T00:50:00Z', 'succes', 'planifie', 'ce', 4, 4, NULL);
UPDATE reports SET last_seen_at = '2026-10-02T00:00:00Z' WHERE id <> 5;
```

→ accepté ; aucun contrôle ne le détecte

```sql
SELECT 4 AS expected_count, 4 AS seen_count,
       (SELECT count(*) FROM reports_active) AS actifs;
```
| expected_count | seen_count | actifs |
|---|---|---|
| 4 | 4 | 5 |

**Schéma corrigé**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, absent_count, removed_count, reappeared_count, error_kind)
VALUES (4, 'oms_don', '2026-10-02T00:00:00Z', '2026-10-02T00:50:00Z', 'succes', 'planifie', 'ce', 4, 4, 1, 0, 0, NULL);
UPDATE reports SET last_seen_run_id = 4 WHERE id <> 5;
```

→ accepté ; aucune violation détectée

```sql
SELECT 4 AS expected_count, 4 AS seen_count,
       (SELECT count(*) FROM reports_active) AS actifs;
```
| expected_count | seen_count | actifs |
|---|---|---|
| 4 | 4 | 5 |

```sql
SELECT g.id AS derniere_execution, g.expected_count AS total_api, g.seen_count,
       (SELECT count(*) FROM reports AS r WHERE r.last_seen_run_id = g.id) AS presents_en_base,
       g.absent_count, g.removed_count
FROM ingestion_runs AS g WHERE g.id = (SELECT max(id) FROM ingestion_runs WHERE source_code = 'oms_don');
```
| derniere_execution | total_api | seen_count | presents_en_base | absent_count | removed_count |
|---|---|---|---|---|---|
| 4 | 4 | 4 | 4 | 1 | 0 |

```sql
SELECT slug, last_seen_run_id, missing_runs, presence, removed_run_id, expected_removed_run_id
FROM reports_presence ORDER BY report_id;
```
| slug | last_seen_run_id | missing_runs | presence | removed_run_id | expected_removed_run_id |
|---|---|---|---|---|---|
| 2026-DON620 | 4 | 0 | present | NULL | NULL |
| 2024-DON528 | 4 | 0 | present | NULL | NULL |
| 2022-DON398_1 | 4 | 0 | present | NULL | NULL |
| 2008_01_21-en | 4 | 0 | present | NULL | NULL |
| 1996_01_22a-en | 1 | 1 | absent | NULL | NULL |

Test Python futur : `tests/test_oms.py::test_ecart_zero_sur_les_presents`

### K1b · Comptes égaux, ensembles différents

Point constat 1 · invariant(s) I8, I9 · résultat attendu : accepté, détecté par `controle_invariants`

5 enregistrements reçus dont un doublon, le 5e DON manque : seen_count = expected_count = 5.

**Phase 1**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, error_kind)
VALUES (4, 'oms_don', '2026-10-02T00:00:00Z', '2026-10-02T00:50:00Z', 'succes', 'planifie', 'ce', 5, 5, NULL);
UPDATE reports SET last_seen_at = '2026-10-02T00:00:00Z' WHERE id IN (1, 2, 3, 4);
```

→ accepté ; aucun contrôle ne le détecte

```sql
WITH received(id) AS (VALUES(1),(2),(3),(4),(4))
SELECT count(*), count(DISTINCT id),
       (SELECT count(*) FROM reports_active)
FROM received;
```
| count(*) | count(DISTINCT id) | (SELECT count(*) FROM reports_active) |
|---|---|---|
| 5 | 4 | 5 |

**Schéma corrigé**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, absent_count, removed_count, reappeared_count, error_kind)
VALUES (4, 'oms_don', '2026-10-02T00:00:00Z', '2026-10-02T00:50:00Z', 'succes', 'planifie', 'ce', 5, 5, 1, 0, 0, NULL);
UPDATE reports SET last_seen_run_id = 4 WHERE id IN (1, 2, 3, 4);
```

→ accepté ; détecté par `controle_invariants` : I9 (ingestion_runs #4)

```sql
WITH received(id) AS (VALUES(1),(2),(3),(4),(4))
SELECT count(*), count(DISTINCT id),
       (SELECT count(*) FROM reports_active)
FROM received;
```
| count(*) | count(DISTINCT id) | (SELECT count(*) FROM reports_active) |
|---|---|---|
| 5 | 4 | 5 |

Test Python futur : `tests/test_oms.py::test_pagination_complete_sans_doublon`

### K2 · Chiffres d'un DON sans définition

Point constat 2 · invariant(s) D23 · résultat attendu : accepté, état cohérent (attendu)

Le DON mpox contient 474 suspects, 142 confirmés, des cumuls et plusieurs pays.

**Phase 1**

→ accepté ; aucun contrôle ne le détecte

```sql
SELECT name FROM pragma_table_info('reports')
WHERE name IN
 ('case_status','value_kind','period_start','period_end','date_basis');
```
| name |
|---|

```sql
SELECT
 instr(json_extract(p.body_text,'$.Overview'),'474 suspected')>0,
 instr(json_extract(p.body_text,'$.Overview'),'142 (39.7%)')>0,
 instr(json_extract(p.body_text,'$.Overview'),'cumulatively')>0
FROM reports r JOIN raw_payloads p ON p.id=r.raw_payload_id
WHERE r.slug='2024-DON528';
```
| instr(json_extract(p.body_text,'$.Overview'),'474 suspected')>0 | instr(json_extract(p.body_text,'$.Overview'),'142 (39.7%)')>0 | instr(json_extract(p.body_text,'$.Overview'),'cumulatively')>0 |
|---|---|---|
| 1 | 1 | 1 |

**Schéma corrigé**

```sql
INSERT INTO report_countries (report_id, country_iso3) VALUES ((SELECT id FROM reports WHERE slug = '2024-DON528'), 'BDI');
UPDATE reports SET figures_payload_id = raw_payload_id, figures_extractor_version = 'regle-0'
WHERE id = (SELECT id FROM reports WHERE slug = '2024-DON528');
INSERT INTO report_figures (report_id, raw_payload_id, country_iso3, measure, case_definition,
    as_of, value, method, status, evidence, extractor_version)
SELECT id, raw_payload_id, 'BDI', 'cas', 'suspect', '2024-08-17', 474, 'regle', 'auto',
    '474 suspected cases (86.9%) had been investigated and validated', 'regle-0'
FROM reports WHERE slug = '2024-DON528';
INSERT INTO report_figures (report_id, raw_payload_id, country_iso3, measure, case_definition,
    as_of, value, method, status, evidence, extractor_version)
SELECT id, raw_payload_id, 'BDI', 'cas', 'confirme', '2024-08-17', 142, 'regle', 'auto',
    'Of 358 suspected cases tested, 142 (39.7%) tested positive for MPXV.', 'regle-0'
FROM reports WHERE slug = '2024-DON528';
```

→ accepté ; aucune violation détectée

```sql
SELECT country_iso3, measure, case_definition, period_start, as_of, value
FROM report_figures_current ORDER BY value DESC;
```
| country_iso3 | measure | case_definition | period_start | as_of | value |
|---|---|---|---|---|---|
| BDI | cas | suspect | NULL | 2024-08-17 | 474 |
| BDI | cas | confirme | NULL | 2024-08-17 | 142 |

Test Python futur : `tests/test_chiffres.py::test_un_chiffre_par_pays_et_par_mesure`

### K3 · Versions historiques qui se chevauchent

Point constat 3 · invariant(s) I22, I24 · résultat attendu : accepté, détecté par `controle_invariants`

Deux versions connues le 2026-10-07.

**Phase 1**

```sql
INSERT INTO observations
(series_id,period_start,period_end,iso_year,iso_week,version,
 value,valid_from,valid_to,run_id)
VALUES
(1,'2026-09-21','2026-09-27',2026,39,1,60,
 '2026-10-01T00:00:00Z','2026-10-10T00:00:00Z',2),
(1,'2026-09-21','2026-09-27',2026,39,2,63,
 '2026-10-05T00:00:00Z',NULL,2);
```

→ accepté ; aucun contrôle ne le détecte

```sql
SELECT version,value FROM observations
WHERE series_id=1 AND period_start='2026-09-21'
  AND valid_from<='2026-10-07T00:00:00Z'
  AND (valid_to IS NULL OR valid_to>'2026-10-07T00:00:00Z');
```
| version | value |
|---|---|
| 1 | 60.0 |
| 2 | 63.0 |

**Schéma corrigé**

```sql
-- adaptation : raw_payload_id ajouté (colonne obligatoire, I60)
INSERT INTO observations
(series_id,period_start,period_end,iso_year,iso_week,version,
 value,valid_from,valid_to,run_id, raw_payload_id)
VALUES
(1,'2026-09-21','2026-09-27',2026,39,1,60,
 '2026-10-01T00:00:00Z','2026-10-10T00:00:00Z',2, 6),
(1,'2026-09-21','2026-09-27',2026,39,2,63,
 '2026-10-05T00:00:00Z',NULL,2, 6);
```

→ accepté ; détecté par `controle_invariants` : I22 (observations #1), I24 (observations #2)

```sql
SELECT version,value FROM observations
WHERE series_id=1 AND period_start='2026-09-21'
  AND valid_from<='2026-10-07T00:00:00Z'
  AND (valid_to IS NULL OR valid_to>'2026-10-07T00:00:00Z');
```
| version | value |
|---|---|
| 1 | 60.0 |
| 2 | 63.0 |

Test Python futur : `tests/test_observations.py::test_fermeture_egale_ouverture_suivante`

### K4 · Révision des bornes perdue

Point constat 4 · invariant(s) I50 · résultat attendu : accepté, état cohérent (attendu)

Point initial 60 [50, 70] ; nouvelle publication 60 [40, 80], source_version 'v2'.

**Phase 1**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by, code_version)
VALUES (4, 'sentinelles', '2026-10-08T00:00:00Z', '2026-10-08T00:50:00Z', 'succes', 'planifie', 'ce');
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, value_low, value_up, source_version, valid_from, run_id)
VALUES (1, '2026-09-21', '2026-09-27', 2026, 39, 1, 60, 50, 70, 'v1', '2026-10-01T00:00:00Z', 2);
```

Python : relance de `insert_observation` avec la valeur 60 et `source_version = 'v2'`. Phase 1 : fonction du commit e8f65a6, qui ne reçoit pas les bornes et ne compare que la valeur. Corrigé : fonction actuelle, appelée avec les bornes 40 et 80.

→ accepté ; aucun contrôle ne le détecte

```sql
SELECT version, value, value_low, value_up, source_version, valid_from, valid_to
FROM observations WHERE series_id = 1 ORDER BY version;
```
| version | value | value_low | value_up | source_version | valid_from | valid_to |
|---|---|---|---|---|---|---|
| 1 | 60.0 | 50.0 | 70.0 | v1 | 2026-10-01T00:00:00Z | NULL |

**Schéma corrigé**

```sql
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by, code_version)
VALUES (4, 'sentinelles', '2026-10-08T00:00:00Z', '2026-10-08T00:50:00Z', 'succes', 'planifie', 'ce');
-- adaptation : raw_payload_id ajouté (colonne obligatoire, I60)
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, value_low, value_up, source_version, valid_from, run_id, raw_payload_id)
VALUES (1, '2026-09-21', '2026-09-27', 2026, 39, 1, 60, 50, 70, 'v1', '2026-10-01T00:00:00Z', 2, 6);
INSERT INTO raw_payloads (source_code, resource_key, request_url, content_type, sha256, byte_size,
    body_text, first_run_id, retrieved_at)
VALUES ('sentinelles', 'inc-3-PAY-ds2', 'u', 'text/csv', printf('%064d', 8), 2, 'v2', 4, '2026-10-08T00:00:00Z');
```

Python : relance de `insert_observation` avec la valeur 60 et `source_version = 'v2'`. Phase 1 : fonction du commit e8f65a6, qui ne reçoit pas les bornes et ne compare que la valeur. Corrigé : fonction actuelle, appelée avec les bornes 40 et 80.

→ accepté ; aucune violation détectée

```sql
SELECT version, value, value_low, value_up, source_version, valid_from, valid_to
FROM observations WHERE series_id = 1 ORDER BY version;
```
| version | value | value_low | value_up | source_version | valid_from | valid_to |
|---|---|---|---|---|---|---|
| 1 | 60.0 | 50.0 | 70.0 | v1 | 2026-10-01T00:00:00Z | 2026-10-08T00:00:00Z |
| 2 | 60.0 | 40.0 | 80.0 | v2 | 2026-10-08T00:00:00Z | NULL |

Test Python futur : `tests/test_observations.py::test_revision_des_bornes_cree_une_version`

### K5 · Suite de contenus A → B → A

Point constat 5 · invariant(s) D26, I51, I52 · résultat attendu : accepté, état cohérent (attendu)

La déduplication par hash garde 2 contenus et perd la date du retour à A.

**Phase 1**

```sql
INSERT INTO raw_payloads
(source_code,resource_key,request_url,content_type,sha256,
 byte_size,body_text,first_run_id,retrieved_at)
VALUES
('oms_don','test','u','application/json',printf('%064d',1),
 7,'{"v":1}',1,'2026-10-01T00:00:00Z')
ON CONFLICT(source_code,resource_key,sha256) DO NOTHING;
INSERT INTO raw_payloads
(source_code,resource_key,request_url,content_type,sha256,
 byte_size,body_text,first_run_id,retrieved_at)
VALUES
('oms_don','test','u','application/json',printf('%064d',2),
 7,'{"v":2}',1,'2026-10-02T00:00:00Z')
ON CONFLICT(source_code,resource_key,sha256) DO NOTHING;
INSERT INTO raw_payloads
(source_code,resource_key,request_url,content_type,sha256,
 byte_size,body_text,first_run_id,retrieved_at)
VALUES
('oms_don','test','u','application/json',printf('%064d',1),
 7,'{"v":1}',1,'2026-10-03T00:00:00Z')
ON CONFLICT(source_code,resource_key,sha256) DO NOTHING;
```

→ accepté ; aucun contrôle ne le détecte

```sql
SELECT body_text,retrieved_at FROM raw_payloads
WHERE resource_key='test' ORDER BY retrieved_at;
```
| body_text | retrieved_at |
|---|---|
| {"v":1} | 2026-10-01T00:00:00Z |
| {"v":2} | 2026-10-02T00:00:00Z |

**Schéma corrigé**

```sql
INSERT INTO raw_payloads
(source_code,resource_key,request_url,content_type,sha256,
 byte_size,body_text,first_run_id,retrieved_at)
VALUES
('oms_don','test','u','application/json',printf('%064d',1),
 7,'{"v":1}',1,'2026-10-01T00:00:00Z')
ON CONFLICT(source_code,resource_key,sha256) DO NOTHING;
INSERT INTO raw_payloads
(source_code,resource_key,request_url,content_type,sha256,
 byte_size,body_text,first_run_id,retrieved_at)
VALUES
('oms_don','test','u','application/json',printf('%064d',2),
 7,'{"v":2}',1,'2026-10-02T00:00:00Z')
ON CONFLICT(source_code,resource_key,sha256) DO NOTHING;
INSERT INTO raw_payloads
(source_code,resource_key,request_url,content_type,sha256,
 byte_size,body_text,first_run_id,retrieved_at)
VALUES
('oms_don','test','u','application/json',printf('%064d',1),
 7,'{"v":1}',1,'2026-10-03T00:00:00Z')
ON CONFLICT(source_code,resource_key,sha256) DO NOTHING;
-- complément : chronologie du DON 'test' dans report_versions
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, absent_count, removed_count, reappeared_count, error_kind)
VALUES (4, 'oms_don', '2026-10-02T00:00:00Z', '2026-10-02T00:50:00Z', 'partiel', 'planifie', 'ce', NULL, NULL, NULL, NULL, NULL, 'controle');
INSERT INTO ingestion_runs (id, source_code, started_at, finished_at, status, triggered_by,
    code_version, expected_count, seen_count, absent_count, removed_count, reappeared_count, error_kind)
VALUES (5, 'oms_don', '2026-10-03T00:00:00Z', '2026-10-03T00:50:00Z', 'partiel', 'planifie', 'ce', NULL, NULL, NULL, NULL, NULL, 'controle');
INSERT INTO reports (source_code, external_id, slug, url, title, published_at, date_quality,
    geo_scope, classification_status, raw_payload_id, first_seen_run_id, last_seen_run_id)
VALUES ('oms_don', 'test', 'test', 'u', 'test', '2026-10-01T00:00:00Z', 'ok', 'inconnu', 'non_classe',
    (SELECT id FROM raw_payloads WHERE resource_key = 'test' AND sha256 = printf('%064d', 1)), 1, 5);
INSERT INTO report_versions (report_id, version, source_code, external_id, raw_payload_id, run_id)
SELECT id, 1, 'oms_don', 'test', (SELECT id FROM raw_payloads WHERE resource_key = 'test' AND sha256 = printf('%064d', 1)), 1 FROM reports WHERE external_id = 'test';
INSERT INTO report_versions (report_id, version, source_code, external_id, raw_payload_id, run_id)
SELECT id, 2, 'oms_don', 'test', (SELECT id FROM raw_payloads WHERE resource_key = 'test' AND sha256 = printf('%064d', 2)), 4 FROM reports WHERE external_id = 'test';
INSERT INTO report_versions (report_id, version, source_code, external_id, raw_payload_id, run_id)
SELECT id, 3, 'oms_don', 'test', (SELECT id FROM raw_payloads WHERE resource_key = 'test' AND sha256 = printf('%064d', 1)), 5 FROM reports WHERE external_id = 'test';
```

→ accepté ; aucune violation détectée

```sql
SELECT body_text,retrieved_at FROM raw_payloads
WHERE resource_key='test' ORDER BY retrieved_at;
```
| body_text | retrieved_at |
|---|---|
| {"v":1} | 2026-10-01T00:00:00Z |
| {"v":2} | 2026-10-02T00:00:00Z |

```sql
SELECT v.version, p.body_text, g.started_at AS depuis
FROM report_versions AS v
JOIN raw_payloads AS p ON p.id = v.raw_payload_id
JOIN ingestion_runs AS g ON g.id = v.run_id
WHERE v.report_id = (SELECT id FROM reports WHERE external_id = 'test') ORDER BY v.version;
```
| version | body_text | depuis |
|---|---|---|
| 1 | {"v":1} | 2026-10-01T00:00:00Z |
| 2 | {"v":2} | 2026-10-02T00:00:00Z |
| 3 | {"v":1} | 2026-10-03T00:00:00Z |

Test Python futur : `tests/test_oms.py::test_retour_a_un_contenu_anterieur_cree_une_version`

### K6a · Semaine commençant un mardi, deux semaines 2020-W53 courantes

Point constat 6 · invariant(s) I33 · résultat attendu : rejeté par la base

Deux points courants pour la même année et la même semaine ISO.

**Phase 1**

```sql
INSERT INTO observations
(series_id,period_start,period_end,iso_year,iso_week,
 version,value,valid_from,run_id)
VALUES
(1,'2020-12-28','2021-01-03',2020,53,1,10,
 '2026-10-01T00:00:00Z',2),
(1,'2020-12-29','2021-01-04',2020,53,1,20,
 '2026-10-01T00:00:00Z',2);
```

→ accepté ; aucun contrôle ne le détecte

```sql
SELECT iso_year,iso_week,count(*) FROM observations_current
GROUP BY iso_year,iso_week;
```
| iso_year | iso_week | count(*) |
|---|---|---|
| 2020 | 53 | 2 |

**Schéma corrigé**

```sql
-- adaptation : raw_payload_id ajouté (colonne obligatoire, I60)
INSERT INTO observations
(series_id,period_start,period_end,iso_year,iso_week,
 version,value,valid_from,run_id, raw_payload_id)
VALUES
(1,'2020-12-28','2021-01-03',2020,53,1,10,
 '2026-10-01T00:00:00Z',2, 6),
(1,'2020-12-29','2021-01-04',2020,53,1,20,
 '2026-10-01T00:00:00Z',2, 6);
```

→ rejeté : `IntegrityError: CHECK constraint failed: iso_week IS NULL OR ( strftime('%w', period_start) = '1' AND period_end = date(period_start, '+6 days') AND CAST(strftime('%Y', period_start, '+3 days') AS INTEGER) = iso_year AND (CAST(strftime('%j', period_start, '+3 days') AS INTEGER) - 1) / 7 + 1 = iso_week)`

Test Python futur : `(contrainte SQL)`

### K6b · 2021-01-01 rangé en 2021-W53

Point constat 6 · invariant(s) I33 · résultat attendu : rejeté par la base

Cette date appartient à 2020-W53 ; 2021 n'a que 52 semaines ISO.

**Phase 1**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, run_id)
VALUES (1, '2021-01-01', '2021-01-07', 2021, 53, 1, 10, '2026-10-01T00:00:00Z', 2);
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
-- adaptation : raw_payload_id ajouté (colonne obligatoire, I60)
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, run_id, raw_payload_id)
VALUES (1, '2021-01-01', '2021-01-07', 2021, 53, 1, 10, '2026-10-01T00:00:00Z', 2, 6);
```

→ rejeté : `IntegrityError: CHECK constraint failed: iso_week IS NULL OR ( strftime('%w', period_start) = '1' AND period_end = date(period_start, '+6 days') AND CAST(strftime('%Y', period_start, '+3 days') AS INTEGER) = iso_year AND (CAST(strftime('%j', period_start, '+3 days') AS INTEGER) - 1) / 7 + 1 = iso_week)`

Test Python futur : `(contrainte SQL)`

### K6c · Baseline W53 avec une seule référence

Point constat 6 · invariant(s) Q9 · résultat attendu : constat hors schéma : même résultat sur les deux schémas

Hors schéma : règle de la baseline à définir avant la phase de détection.

**Phase 1**

→ accepté ; aucun contrôle ne le détecte

```sql
WITH reference(iso_year,iso_week,value) AS
(VALUES(2016,52,10),(2017,52,11),(2018,52,12),
       (2019,52,13),(2020,53,14))
SELECT count(*),avg(value) FROM reference
WHERE iso_year BETWEEN 2016 AND 2020 AND iso_week=53;
```
| count(*) | avg(value) |
|---|---|
| 1 | 14.0 |

**Schéma corrigé**

→ accepté ; aucune violation détectée

```sql
WITH reference(iso_year,iso_week,value) AS
(VALUES(2016,52,10),(2017,52,11),(2018,52,12),
       (2019,52,13),(2020,53,14))
SELECT count(*),avg(value) FROM reference
WHERE iso_year BETWEEN 2016 AND 2020 AND iso_week=53;
```
| count(*) | avg(value) |
|---|---|
| 1 | 14.0 |

Test Python futur : `tests/test_detection.py::test_semaine_53_regle_de_reference`

### K7a · Observation Sentinelles avec exécution et brut OMS

Point constat 7 · invariant(s) I15 · résultat attendu : accepté, détecté par `controle_invariants`

Clés étrangères valides, provenance fausse.

**Phase 1**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, run_id)
VALUES (1, '2026-09-21', '2026-09-27', 2026, 39, 1, 60, '2026-10-01T00:00:00Z', 1);
UPDATE observations SET raw_payload_id=1;
```

→ accepté ; aucun contrôle ne le détecte

```sql
SELECT s.source_code,i.source_code,r.source_code
FROM observations o
JOIN series s ON s.id=o.series_id
JOIN ingestion_runs i ON i.id=o.run_id
JOIN raw_payloads r ON r.id=o.raw_payload_id;
```
| source_code | source_code | source_code |
|---|---|---|
| sentinelles | oms_don | oms_don |

```sql
PRAGMA foreign_key_check;
```
| table | rowid | parent | fkid |
|---|---|---|---|

**Schéma corrigé**

```sql
-- adaptation : raw_payload_id ajouté (colonne obligatoire, I60)
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, run_id, raw_payload_id)
VALUES (1, '2026-09-21', '2026-09-27', 2026, 39, 1, 60, '2026-10-01T00:00:00Z', 1, 6);
UPDATE observations SET raw_payload_id=1;
```

→ accepté ; détecté par `controle_invariants` : I15 (observations #1)

```sql
SELECT s.source_code,i.source_code,r.source_code
FROM observations o
JOIN series s ON s.id=o.series_id
JOIN ingestion_runs i ON i.id=o.run_id
JOIN raw_payloads r ON r.id=o.raw_payload_id;
```
| source_code | source_code | source_code |
|---|---|---|
| sentinelles | oms_don | oms_don |

Test Python futur : `tests/test_observations.py::test_observation_rattachee_a_la_source_de_sa_serie`

### K7b · DON pointant le brut d'un autre DON

Point constat 7 · invariant(s) I13 · résultat attendu : rejeté par la base

Modification acceptée en phase 1.

**Phase 1**

```sql
UPDATE reports SET raw_payload_id=2 WHERE id=1;
```

→ accepté ; aucun contrôle ne le détecte

```sql
SELECT r.external_id=p.resource_key
FROM reports r JOIN raw_payloads p ON p.id=r.raw_payload_id
WHERE r.id=1;
```
| r.external_id=p.resource_key |
|---|
| 0 |

**Schéma corrigé**

```sql
UPDATE reports SET raw_payload_id=2 WHERE id=1;
```

→ rejeté : `IntegrityError: FOREIGN KEY constraint failed`

Test Python futur : `(contrainte SQL)`

### K8 · Pays absents du titre

Point constat 8 · invariant(s) R11 · résultat attendu : constat hors schéma : même résultat sur les deux schémas

Hors schéma : méthode de classification (phase 3). Complément : ajouter plus tard un rôle par pays ne coûte qu'un ALTER TABLE.

**Phase 1**

```sql
ALTER TABLE report_countries ADD COLUMN role TEXT NOT NULL DEFAULT 'concerne'
    CHECK (role IN ('concerne', 'mentionne', 'voyage'));
```

→ accepté ; aucun contrôle ne le détecte

```sql
SELECT
 instr(json_extract(p.body_text,'$.Title'),'Burundi') AS titre,
 instr(json_extract(p.body_text,'$.Overview'),'Burundi')>0 AS texte
FROM reports r JOIN raw_payloads p ON p.id=r.raw_payload_id
WHERE r.slug='2024-DON528';
```
| titre | texte |
|---|---|
| 0 | 1 |

**Schéma corrigé**

```sql
ALTER TABLE report_countries ADD COLUMN role TEXT NOT NULL DEFAULT 'concerne'
    CHECK (role IN ('concerne', 'mentionne', 'voyage'));
```

→ accepté ; aucune violation détectée

```sql
SELECT
 instr(json_extract(p.body_text,'$.Title'),'Burundi') AS titre,
 instr(json_extract(p.body_text,'$.Overview'),'Burundi')>0 AS texte
FROM reports r JOIN raw_payloads p ON p.id=r.raw_payload_id
WHERE r.slug='2024-DON528';
```
| titre | texte |
|---|---|
| 0 | 1 |

Test Python futur : `tests/test_classification.py::test_pays_lus_dans_le_texte_regional`

### K9 · Licence par jeu de données

Point constat 9 · invariant(s) D27, I54 · résultat attendu : accepté, détecté par `controle_invariants`

Série créée sur un jeu exclu faute de licence ; la licence affichée est celle du fournisseur.

**Phase 1**

```sql
INSERT INTO series
(source_code,dataset,metric,disease_code,geo_level,geo_code,
 geo_label,period_type,value_kind,unit,case_status,date_basis)
VALUES
('spf_odisse','ira-virologie-renal','test','ira','pays','FR',
 'France','semaine_iso','incidence','cas','confirme','declaration');
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, run_id)
VALUES ((SELECT id FROM series WHERE dataset = 'ira-virologie-renal'),
    '2026-09-21', '2026-09-27', 2026, 39, 1, 5, '2026-10-01T00:00:00Z', 3);
```

→ accepté ; aucun contrôle ne le détecte

```sql
SELECT name FROM pragma_table_info('series')
WHERE name LIKE '%license%';
```
| name |
|---|

```sql
SELECT s.dataset,src.license_name
FROM series s JOIN sources src ON src.code=s.source_code
WHERE s.dataset='ira-virologie-renal';
```
| dataset | license_name |
|---|---|
| ira-virologie-renal | Licence Ouverte 2.0 |

**Schéma corrigé**

```sql
INSERT INTO series
(source_code,dataset,metric,disease_code,geo_level,geo_code,
 geo_label,period_type,value_kind,unit,case_status,date_basis)
VALUES
('spf_odisse','ira-virologie-renal','test','ira','pays','FR',
 'France','semaine_iso','incidence','cas','confirme','declaration');
-- adaptation : raw_payload_id ajouté (colonne obligatoire, I60)
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, run_id, raw_payload_id)
VALUES ((SELECT id FROM series WHERE dataset = 'ira-virologie-renal'),
    '2026-09-21', '2026-09-27', 2026, 39, 1, 5, '2026-10-01T00:00:00Z', 3, 7);
```

→ accepté ; détecté par `controle_invariants` : I54 (observations #1)

```sql
SELECT name FROM pragma_table_info('series')
WHERE name LIKE '%license%';
```
| name |
|---|

```sql
SELECT s.dataset, d.license_name, d.is_publishable, d.publishable_since, d.license_note
FROM series s
JOIN datasets d ON d.source_code = s.source_code AND d.dataset = s.dataset
WHERE s.dataset='ira-virologie-renal';
```
| dataset | license_name | is_publishable | publishable_since | license_note |
|---|---|---|---|---|
| ira-virologie-renal | NULL | 0 | NULL | Aucune licence déclarée dans le catalogue (phase 0) : exclu de la v1. |

Test Python futur : `tests/test_sources.py::test_jeu_sans_licence_non_ingere`

### K10a · Valeur négative hors de ses bornes

Point constat 10 · invariant(s) I27 · résultat attendu : rejeté par la base

-5 avec l'intervalle [0, 10] ; absence sans motif ; zéro.

**Phase 1**

```sql
INSERT INTO observations
(series_id,period_start,period_end,iso_year,iso_week,version,
 value,value_low,value_up,valid_from,run_id)
VALUES
(1,'2026-09-21','2026-09-27',2026,39,1,-5,0,10,
 '2026-10-01T00:00:00Z',2),
(1,'2026-09-28','2026-10-04',2026,40,1,NULL,NULL,NULL,
 '2026-10-01T00:00:00Z',2),
(1,'2026-10-05','2026-10-11',2026,41,1,0,NULL,NULL,
 '2026-10-01T00:00:00Z',2);
```

→ accepté ; aucun contrôle ne le détecte

```sql
SELECT iso_week,value,value_low,value_up
FROM observations_current ORDER BY iso_week;
```
| iso_week | value | value_low | value_up |
|---|---|---|---|
| 39 | -5.0 | 0.0 | 10.0 |
| 40 | NULL | NULL | NULL |
| 41 | 0.0 | NULL | NULL |

**Schéma corrigé**

```sql
-- adaptation : raw_payload_id ajouté (colonne obligatoire, I60)
INSERT INTO observations
(series_id,period_start,period_end,iso_year,iso_week,version,
 value,value_low,value_up,valid_from,run_id, raw_payload_id)
VALUES
(1,'2026-09-21','2026-09-27',2026,39,1,-5,0,10,
 '2026-10-01T00:00:00Z',2, 6),
(1,'2026-09-28','2026-10-04',2026,40,1,NULL,NULL,NULL,
 '2026-10-01T00:00:00Z',2, 6),
(1,'2026-10-05','2026-10-11',2026,41,1,0,NULL,NULL,
 '2026-10-01T00:00:00Z',2, 6);
```

→ rejeté : `IntegrityError: CHECK constraint failed: value_low IS NULL OR value >= value_low`

Test Python futur : `(contrainte SQL)`

### K10b · Complément : valeur absente sans motif

Point constat 10 · invariant(s) I55 · résultat attendu : rejeté par la base

Une valeur NULL doit porter son motif (value_status).

**Phase 1**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, run_id)
VALUES (1, '2026-09-28', '2026-10-04', 2026, 40, 1, NULL, '2026-10-01T00:00:00Z', 2);
```

→ accepté ; aucun contrôle ne le détecte

**Schéma corrigé**

```sql
-- adaptation : raw_payload_id ajouté (colonne obligatoire, I60)
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, run_id, raw_payload_id)
VALUES (1, '2026-09-28', '2026-10-04', 2026, 40, 1, NULL, '2026-10-01T00:00:00Z', 2, 6);
```

→ rejeté : `IntegrityError: CHECK constraint failed: (value IS NOT NULL) = (value_status IN ('publiee', 'provisoire'))`

Test Python futur : `(contrainte SQL)`

### K10c · Complément : valeur sous le domaine de la série

Point constat 10 · invariant(s) I56 · résultat attendu : accepté, détecté par `controle_invariants`

-5 sans bornes, pour une série dont la plus petite valeur admissible est 0.

**Phase 1** : sans objet.

**Schéma corrigé**

```sql
UPDATE series SET value_min = 0 WHERE id = 1;
-- adaptation : raw_payload_id ajouté (colonne obligatoire, I60)
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, run_id, raw_payload_id)
VALUES (1, '2026-09-21', '2026-09-27', 2026, 39, 1, -5, '2026-10-01T00:00:00Z', 2, 6);
```

→ accepté ; détecté par `controle_invariants` : I56 (observations #1)

Test Python futur : `tests/test_observations.py::test_valeur_dans_le_domaine_de_la_serie`

### K11a · Horodatage impossible en minuscules

Point constat 11 · invariant(s) I2 · résultat attendu : rejeté par la base

LIKE est insensible à la casse et '_' accepte tout caractère.

**Phase 1**

```sql
UPDATE ingestion_runs
SET started_at='2026-99-99t99:99:99z',
    finished_at='2026-99-99t99:99:99z'
WHERE id=1;
```

→ accepté ; aucun contrôle ne le détecte

```sql
SELECT started_at,finished_at FROM ingestion_runs WHERE id=1;
```
| started_at | finished_at |
|---|---|
| 2026-99-99t99:99:99z | 2026-99-99t99:99:99z |

**Schéma corrigé**

```sql
UPDATE ingestion_runs
SET started_at='2026-99-99t99:99:99z',
    finished_at='2026-99-99t99:99:99z'
WHERE id=1;
```

→ rejeté : `IntegrityError: CHECK constraint failed: started_at IS strftime('%Y-%m-%dT%H:%M:%SZ', started_at)`

Test Python futur : `(contrainte SQL)`

### K11b · Horodatage avec décalage +02:00

Point constat 11 · invariant(s) I2 · résultat attendu : rejeté par la base

Rejeté dans les deux schémas : la normalisation en UTC se fait en Python avant insertion.

**Phase 1**

```sql
UPDATE ingestion_runs
SET started_at='2026-10-01T02:00:00+02:00' WHERE id=1;
```

→ rejeté : `IntegrityError: CHECK constraint failed: started_at LIKE '____-__-__T__:__:__Z'`

**Schéma corrigé**

```sql
UPDATE ingestion_runs
SET started_at='2026-10-01T02:00:00+02:00' WHERE id=1;
```

→ rejeté : `IntegrityError: CHECK constraint failed: started_at IS strftime('%Y-%m-%dT%H:%M:%SZ', started_at)`

Test Python futur : `(contrainte SQL)`

### K12 · Alerte envoyée, base non persistée

Point constat 12 · invariant(s) D19, R14 · résultat attendu : accepté **par conception** (risque documenté)

Restauration de l'image précédente par deserialize().

**Phase 1**

Python : alerte `rapport:1` écrite `a_envoyer`, image de la base (`serialize`), passage à `envoyee`, puis restauration de l'image (`deserialize`).

→ accepté ; aucun contrôle ne le détecte

```sql
SELECT dedup_key,status FROM alerts_log
WHERE status IN ('a_envoyer','echec');
```
| dedup_key | status |
|---|---|
| rapport:1 | a_envoyer |

**Schéma corrigé**

Python : alerte `rapport:1` écrite `a_envoyer`, image de la base (`serialize`), passage à `envoyee`, puis restauration de l'image (`deserialize`).

→ accepté ; aucune violation détectée

```sql
SELECT dedup_key,status FROM alerts_log
WHERE status IN ('a_envoyer','echec');
```
| dedup_key | status |
|---|---|
| rapport:1 | a_envoyer |

Test Python futur : `tests/test_alertes.py::test_alerte_journalisee_avant_envoi`

### K13 · Croissance des exports bruts

Point constat 13 · invariant(s) R16, I58 · résultat attendu : constat hors schéma : même résultat sur les deux schémas

Hors schéma : arithmétique de dimensionnement du relecteur.

**Phase 1**

→ accepté ; aucun contrôle ne le détecte

```sql
SELECT 26*10.0,52*10.0,260*10.0;
```
| 26*10.0 | 52*10.0 | 260*10.0 |
|---|---|---|
| 260.0 | 520.0 | 2600.0 |

**Schéma corrigé**

→ accepté ; aucune violation détectée

```sql
SELECT 26*10.0,52*10.0,260*10.0;
```
| 26*10.0 | 52*10.0 | 260*10.0 |
|---|---|---|
| 260.0 | 520.0 | 2600.0 |

Test Python futur : `tests/test_pipeline.py::test_taille_de_l_asset_bornee`

### K14a · Précision de REAL

Point constat 14 · invariant(s) architecture §6 · résultat attendu : constat hors schéma : même résultat sur les deux schémas

Hors schéma : REAL SQLite = double précision ; à migrer en DOUBLE PRECISION.

**Phase 1**

→ accepté ; aucun contrôle ne le détecte

```sql
SELECT CAST(1.2345678901234567 AS REAL);
```
| CAST(1.2345678901234567 AS REAL) |
|---|
| 1.2345678901234567 |

**Schéma corrigé**

→ accepté ; aucune violation détectée

```sql
SELECT CAST(1.2345678901234567 AS REAL);
```
| CAST(1.2345678901234567 AS REAL) |
|---|
| 1.2345678901234567 |

Test Python futur : `(migration)`

### K14b · Paramètres d'anomalie qui ne sont pas du JSON

Point constat 14 · invariant(s) I59 · résultat attendu : rejeté par la base

parameters = 'pas du JSON' accepté en phase 1.

**Phase 1**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, run_id)
VALUES (1, '2026-09-21', '2026-09-27', 2026, 39, 1, 60, '2026-10-01T00:00:00Z', 2);
INSERT INTO anomalies (observation_id, method, method_version, parameters, observed_value,
    expected_value, threshold_value, severity, detected_at, code_version)
VALUES ((SELECT max(id) FROM observations), 'baseline_saisonniere', '1', 'pas du JSON',
    60, 40, 50, 'elevee', '2026-10-01T00:00:00Z', 'relecteur');
```

→ accepté ; aucun contrôle ne le détecte

```sql
SELECT parameters,json_valid(parameters) FROM anomalies;
```
| parameters | json_valid(parameters) |
|---|---|
| pas du JSON | 0 |

**Schéma corrigé**

```sql
-- adaptation : raw_payload_id ajouté (colonne obligatoire, I60)
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
    value, valid_from, run_id, raw_payload_id)
VALUES (1, '2026-09-21', '2026-09-27', 2026, 39, 1, 60, '2026-10-01T00:00:00Z', 2, 6);
INSERT INTO anomalies (observation_id, method, method_version, parameters, observed_value,
    expected_value, threshold_value, severity, detected_at, code_version)
VALUES ((SELECT max(id) FROM observations), 'baseline_saisonniere', '1', 'pas du JSON',
    60, 40, 50, 'elevee', '2026-10-01T00:00:00Z', 'relecteur');
```

→ rejeté : `IntegrityError: CHECK constraint failed: json_valid(parameters)`

Test Python futur : `(contrainte SQL)`

