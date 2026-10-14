# Phase 1 : validation du schéma

Fichier généré par `python db/check_schema.py --out docs/01-validation.md --volume`. Ne pas modifier à la main.

## 1. Application du schéma

- Moteur : SQLite 3.50.4 (module `sqlite3` de Python ; l'outil en ligne de commande `sqlite3` n'est pas installé sur ce poste).
- `db/schema.sql` puis `db/seed.sql` exécutés sans erreur.
- `PRAGMA user_version` = 1
- `PRAGMA integrity_check` = ok
- `PRAGMA foreign_key_check` : 0 violation(s)

```sql
SELECT type, name FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name;
```
| type | name |
|---|---|
| index | ingestion_runs_by_source |
| index | ingestion_runs_one_running |
| index | observations_one_current |
| index | report_countries_by_country |
| index | report_countries_one_primary |
| index | report_figures_by_report |
| index | report_figures_one_value |
| index | reports_by_date |
| index | reports_by_disease_date |
| table | alerts_log |
| table | anomalies |
| table | datasets |
| table | diseases |
| table | ingestion_runs |
| table | observations |
| table | raw_payloads |
| table | report_countries |
| table | report_figures |
| table | report_versions |
| table | reports |
| table | series |
| table | sources |
| view | controle_invariants |
| view | observations_current |
| view | report_figures_current |
| view | reports_active |
| view | reports_presence |

27 ligne(s).

## 2. Les 5 DON de l'échantillon

```sql
SELECT r.slug, r.external_ref, r.title, substr(r.published_at, 1, 10) AS publie_le,
       r.disease_code, r.geo_scope,
       (SELECT group_concat(c.country_iso3) FROM report_countries AS c WHERE c.report_id = r.id) AS pays,
       (SELECT group_concat(f.measure || ' ' || f.value || ' (' || f.status || ')')
        FROM report_figures_current AS f WHERE f.report_id = r.id) AS chiffres
FROM reports AS r
ORDER BY r.published_at DESC;
```
| slug | external_ref | title | publie_le | disease_code | geo_scope | pays | chiffres |
|---|---|---|---|---|---|---|---|
| 2026-DON620 | 2026-DON620 | Pneumonia of undetermined etiology - the Russian Federation | 2026-10-10 | pneumonie_indeterminee | pays | RUS | NULL |
| 2024-DON528 | 2024-DON528 | Mpox – African Region | 2024-08-22 | mpox | region | NULL | NULL |
| 2022-DON398_1 | 2022-DON398 | Cholera – Somalia | 2022-07-20 | cholera | pays | SOM | NULL |
| 2008_01_21-en | NULL | Avian influenza – situation in Indonesia – update 32 | 2008-01-21 | grippe_aviaire | pays | IDN | cas 119 (valide),deces 97 (valide) |
| 1996_01_22a-en | NULL | 1996 - Global Cholera Update | 1996-01-22 | cholera | mondial | NULL | NULL |

5 ligne(s).

## 3. Observations hebdomadaires fictives

Série : Sentinelles `inc-3-PAY-ds2` / `inc100`, France métropolitaine. **Valeurs fictives.** Exécution A (2026-09-30) : S38 = 50, S39 = 60. Exécution B (2026-10-07) : S38 inchangée (50), S39 révisée à 63, S40 = 70.

```sql
SELECT id, iso_year, iso_week, period_start, version, value, valid_from, valid_to, run_id
FROM observations ORDER BY period_start, version;
```
| id | iso_year | iso_week | period_start | version | value | valid_from | valid_to | run_id |
|---|---|---|---|---|---|---|---|---|
| 1 | 2026 | 38 | 2026-09-14 | 1 | 50.0 | 2026-09-30T17:18:00Z | NULL | 2 |
| 2 | 2026 | 39 | 2026-09-21 | 1 | 60.0 | 2026-09-30T17:18:00Z | 2026-10-07T17:18:00Z | 2 |
| 3 | 2026 | 39 | 2026-09-21 | 2 | 63.0 | 2026-10-07T17:18:00Z | NULL | 3 |
| 4 | 2026 | 40 | 2026-09-28 | 1 | 70.0 | 2026-10-07T17:18:00Z | NULL | 3 |

4 ligne(s).

## 4. Requêtes demandées

### 4.1 Dernière version d'une observation (S39)

```sql
SELECT period_start, iso_week, version, value, valid_from
FROM observations_current
WHERE series_id = :series_id AND period_start = '2026-09-21';
```
| period_start | iso_week | version | value | valid_from |
|---|---|---|---|---|
| 2026-09-21 | 39 | 2 | 63.0 | 2026-10-07T17:18:00Z |

1 ligne(s).

Série courante complète (ce que le site affiche) :

```sql
SELECT iso_week, value, version FROM observations_current
WHERE series_id = :series_id ORDER BY period_start;
```
| iso_week | value | version |
|---|---|---|
| 38 | 50.0 | 1 |
| 39 | 63.0 | 2 |
| 40 | 70.0 | 1 |

3 ligne(s).

### 4.2 Historique d'une révision (S39)

```sql
SELECT version, value, valid_from, valid_to, source_version, run_id
FROM observations
WHERE series_id = :series_id AND period_start = '2026-09-21'
ORDER BY version;
```
| version | value | valid_from | valid_to | source_version | run_id |
|---|---|---|---|---|---|
| 1 | 60.0 | 2026-09-30T17:18:00Z | 2026-10-07T17:18:00Z | v-a | 2 |
| 2 | 63.0 | 2026-10-07T17:18:00Z | NULL | v-b | 3 |

2 ligne(s).

Valeur telle qu'elle était connue le 2026-10-03 (requête « as-of », utile au backtest) :

```sql
SELECT version, value
FROM observations
WHERE series_id = :series_id AND period_start = '2026-09-21'
  AND valid_from <= :as_of AND (valid_to IS NULL OR valid_to > :as_of);
```
| version | value |
|---|---|
| 1 | 60.0 |

1 ligne(s).

### 4.3 DON d'une maladie sur 12 mois

Les bornes sont calculées en Python et passées en paramètres (pas de fonction de date SQL, pour la portabilité).

Paramètres : `disease = 'pneumonie_indeterminee'`, `since = '2025-10-13T18:00:00Z'`, `until = '2026-10-13T18:00:00Z'`

```sql
SELECT slug, title, substr(published_at, 1, 10) AS publie_le
FROM reports_active
WHERE disease_code = :disease AND published_at >= :since AND published_at < :until
ORDER BY published_at DESC;
```
| slug | title | publie_le |
|---|---|---|
| 2026-DON620 | Pneumonia of undetermined etiology - the Russian Federation | 2026-10-10 |

1 ligne(s).

Paramètres : `disease = 'cholera'`, `since = '2022-01-01T00:00:00Z'`, `until = '2023-01-01T00:00:00Z'`

```sql
SELECT slug, title, substr(published_at, 1, 10) AS publie_le
FROM reports_active
WHERE disease_code = :disease AND published_at >= :since AND published_at < :until
ORDER BY published_at DESC;
```
| slug | title | publie_le |
|---|---|---|
| 2022-DON398_1 | Cholera – Somalia | 2022-07-20 |

1 ligne(s).

Contre-exemple : la même question pour le choléra en 2021, avec le champ `PublicationDate` lu dans le JSON brut au lieu de `published_at` (`PublicationDateAndTime`) :

```sql
SELECT r.slug, r.title,
       substr(json_extract(p.body_text, '$.PublicationDate'), 1, 10) AS publication_date_brute,
       substr(r.published_at, 1, 10) AS published_at
FROM reports AS r JOIN raw_payloads AS p ON p.id = r.raw_payload_id
WHERE r.disease_code = 'cholera'
  AND json_extract(p.body_text, '$.PublicationDate') >= '2021-01-01'
  AND json_extract(p.body_text, '$.PublicationDate') <  '2022-01-01';
```
| slug | title | publication_date_brute | published_at |
|---|---|---|---|
| 1996_01_22a-en | 1996 - Global Cholera Update | 2021-06-08 | 1996-01-22 |

1 ligne(s).

Le bulletin de 1996 sortirait à tort dans une recherche sur 2021. Avec `published_at`, la même recherche ne renvoie rien.

### 4.4 Doublons et contraintes

**Doublon de DON (même Id OMS)**

```sql
INSERT INTO reports (source_code, external_id, slug, url, title, published_at, date_quality,
                     geo_scope, classification_status, raw_payload_id, first_seen_run_id, last_seen_run_id)
VALUES ('oms_don', ?, 'autre-slug', 'https://example.invalid', 'doublon', ?, 'ok',
        'inconnu', 'non_classe', 1, ?, ?);
```
Résultat : rejeté, `sqlite3.IntegrityError: UNIQUE constraint failed: reports.source_code, reports.external_id`

**Doublon de version d'observation (S39, version 2)**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
                          value, valid_from, valid_to, run_id, raw_payload_id)
VALUES (?, '2026-09-21', '2026-09-27', 2026, 39, 2, 99, ?, ?, ?, ?);
```
Résultat : rejeté, `sqlite3.IntegrityError: UNIQUE constraint failed: observations.series_id, observations.period_start, observations.version`

**Deuxième version courante sans fermer la précédente (S40)**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
                          value, valid_from, run_id, raw_payload_id)
VALUES (?, '2026-09-28', '2026-10-04', 2026, 40, 2, 71, ?, ?, ?);
```
Résultat : rejeté, `sqlite3.IntegrityError: UNIQUE constraint failed: observations.series_id, observations.period_start`

**Chiffres extraits par LLM marqués « auto »**

```sql
INSERT INTO report_figures (report_id, raw_payload_id, measure, case_definition, value,
                            method, status, evidence, extractor_version)
SELECT id, raw_payload_id, 'deces', 'total', 1, 'llm', 'auto', 'confirmed the death', 'llm-0'
FROM reports WHERE slug = '2026-DON620';
```
Résultat : rejeté, `sqlite3.IntegrityError: CHECK constraint failed: method <> 'llm' OR status IN ('incertain', 'valide')`

**Clé étrangère vers une série inexistante**

```sql
INSERT INTO observations (series_id, period_start, period_end, iso_year, iso_week, version,
                          value, valid_from, run_id, raw_payload_id)
VALUES (999, '2026-09-28', '2026-10-04', 2026, 40, 1, 1, ?, ?, ?);
```
Résultat : rejeté, `sqlite3.IntegrityError: FOREIGN KEY constraint failed`

**Relance : même contenu brut réinséré (déduplication idempotente, pas une erreur)**

```sql
INSERT INTO raw_payloads (source_code, resource_key, request_url, content_type, sha256,
                          byte_size, body_text, first_run_id, retrieved_at)
VALUES ('oms_don', ?, 'https://www.who.int/api/news/diseaseoutbreaknews', 'application/json', ?, ?, ?, ?, ?)
ON CONFLICT (source_code, resource_key, sha256) DO NOTHING;
```
Résultat : **aucune erreur**, 0 ligne(s) modifiée(s).

Après la relance : 7 lignes dans `raw_payloads` (5 attendues).

### 4.5 Contrôle des invariants

Vue qui doit être vide avant tout envoi de la base (voir `docs/01-invariants.md`) :

```sql
SELECT invariant, table_name, row_id FROM controle_invariants;
```
| invariant | table_name | row_id |
|---|---|---|

0 ligne(s).

## 5. Mesure de volume (base synthétique)

Hypothèses (estimation, à confirmer en phase 2) : Sentinelles 4 indicateurs hebdomadaires × 14 zones (national + 13 régions) × 2 mesures × 560 semaines ; Odissé 4 jeux SurSaUD × 19 zones × 6 classes d'âge × 3 mesures × 300 semaines ; 5 % de points révisés une fois ; 3199 DON avec un JSON brut de 6 466 caractères (moyenne réelle mesurée en phase 0). Exports bruts Odissé non inclus (rétention à part).

| Mesure | Valeur |
|---|---|
| Séries | 1 480 |
| Lignes `observations` | 496 770 |
| JSON brut OMS | 15.4 Mo |
| Taille du fichier SQLite (après VACUUM) | 86.7 Mo |
| Taille compressée (gzip -6) | 10.5 Mo |
| Temps de remplissage | 7.5 s |

