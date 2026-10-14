# Phase 2 : validation du pipeline d'ingestion OMS

Rédigé le 2026-10-14. Code : `src/observatoire/`, tests : `tests/`. Choix, limites et questions : `docs/02-notes.md`.

Environnement de mesure : Python 3.12.3, SQLite 3.45.1, httpx 0.28.1, pydantic 2.14.1, pytest 9.1.1, dans un environnement virtuel dédié (`pip install -e .` puis `pytest`). Le schéma testé est `db/schema.sql` et `db/seed.sql` du dépôt, appliqués sans modification.

**Résumé.**
- **Tests : 122 passés, 0 échec** (section 1).
- `mypy --strict` : aucune erreur sur `src` et sur `tests` (section 3).
- **Run réel contre l'API OMS : impossible dans cet environnement, donc non mesuré** (section 4). Aucun chiffre de cette section n'est une estimation.

## 1. Sortie complète de pytest

Commande : `pytest -v` (configuration dans `pyproject.toml`, avertissements Python traités comme des erreurs). Aucun appel réseau : `httpx.MockTransport` et `fixtures/who_don_sample.json`.

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0 -- <venv>/bin/python
rootdir: /home/user/virus-101
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.15.1
collecting ... collected 122 items

tests/test_bruts.py::test_empreinte_sur_contenu_non_compresse PASSED     [  0%]
tests/test_bruts.py::test_json_brut_archive_identique_a_l_enregistrement_recu PASSED [  1%]
tests/test_bruts.py::test_meme_contenu_pas_reinsere PASSED               [  2%]
tests/test_cli.py::test_ingest_oms_succes_puis_second_run_idempotent PASSED [  3%]
tests/test_cli.py::test_contact_obligatoire PASSED                       [  4%]
tests/test_cli.py::test_contact_et_base_depuis_l_environnement PASSED    [  4%]
tests/test_cli.py::test_reglage_invalide_est_une_erreur_d_usage PASSED   [  5%]
tests/test_cli.py::test_code_de_sortie_non_nul_en_cas_d_echec PASSED     [  6%]
tests/test_cli.py::test_code_de_sortie_distinct_pour_un_run_partiel PASSED [  7%]
tests/test_cli.py::test_db_check PASSED                                  [  8%]
tests/test_cli.py::test_db_check_base_introuvable PASSED                 [  9%]
tests/test_client.py::test_user_agent_explicite_avec_contact_et_requete_odata PASSED [  9%]
tests/test_client.py::test_delais_exponentiels_plafonnes_sur_erreur_reseau PASSED [ 10%]
tests/test_client.py::test_part_aleatoire_ajoutee_a_l_attente PASSED     [ 11%]
tests/test_client.py::test_timeout_est_reessaye_puis_echoue_proprement PASSED [ 12%]
tests/test_client.py::test_reprise_apres_erreurs_transitoires PASSED     [ 13%]
tests/test_client.py::test_5xx_retry_avec_backoff_puis_echec_propre[500] PASSED [ 13%]
tests/test_client.py::test_5xx_retry_avec_backoff_puis_echec_propre[502] PASSED [ 14%]
tests/test_client.py::test_5xx_retry_avec_backoff_puis_echec_propre[503] PASSED [ 15%]
tests/test_client.py::test_5xx_retry_avec_backoff_puis_echec_propre[504] PASSED [ 16%]
tests/test_client.py::test_4xx_jamais_de_retry[400] PASSED               [ 17%]
tests/test_client.py::test_4xx_jamais_de_retry[401] PASSED               [ 18%]
tests/test_client.py::test_4xx_jamais_de_retry[403] PASSED               [ 18%]
tests/test_client.py::test_4xx_jamais_de_retry[404] PASSED               [ 19%]
tests/test_client.py::test_4xx_jamais_de_retry[410] PASSED               [ 20%]
tests/test_client.py::test_429_quota_sans_retry PASSED                   [ 21%]
tests/test_client.py::test_reponse_non_json_est_une_erreur_de_format PASSED [ 22%]
tests/test_client.py::test_decompte_absent_est_une_erreur_de_format PASSED [ 22%]
tests/test_client.py::test_page_sans_champ_value_est_une_erreur_de_format PASSED [ 23%]
tests/test_client.py::test_pagination_qui_ne_se_termine_pas_est_bornee PASSED [ 24%]
tests/test_client.py::test_reglages_valides PASSED                       [ 25%]
tests/test_controle.py::test_vue_controle_vide_sur_base_coherente PASSED [ 26%]
tests/test_controle.py::test_la_vue_signale_un_retrait_prematuré PASSED  [ 27%]
tests/test_db.py::test_connexion_active_les_cles_etrangeres PASSED       [ 27%]
tests/test_db.py::test_horodatage_converti_en_utc[2026-10-10T15:53:19Z-2026-10-10T15:53:19Z] PASSED [ 28%]
tests/test_db.py::test_horodatage_converti_en_utc[2026-10-10T17:53:19+02:00-2026-10-10T15:53:19Z] PASSED [ 29%]
tests/test_db.py::test_horodatage_converti_en_utc[2026-10-10T10:53:19-05:00-2026-10-10T15:53:19Z] PASSED [ 30%]
tests/test_db.py::test_horodatage_converti_en_utc[2026-10-10T15:53:19.987654Z-2026-10-10T15:53:19Z] PASSED [ 31%]
tests/test_db.py::test_horodatage_converti_en_utc[2008-01-21T00:00:00Z-2008-01-21T00:00:00Z] PASSED [ 31%]
tests/test_db.py::test_horodatage_converti_en_utc[given5-2026-10-10T15:53:19Z] PASSED [ 32%]
tests/test_db.py::test_horodatage_converti_en_utc[given6-2026-10-10T15:53:19Z] PASSED [ 33%]
tests/test_db.py::test_horodatage_invalide_ou_sans_fuseau_refuse[2026-10-10T15:53:19] PASSED [ 34%]
tests/test_db.py::test_horodatage_invalide_ou_sans_fuseau_refuse[2026-10-10] PASSED [ 35%]
tests/test_db.py::test_horodatage_invalide_ou_sans_fuseau_refuse[pas une date] PASSED [ 36%]
tests/test_db.py::test_horodatage_invalide_ou_sans_fuseau_refuse[2026-99-99T00:00:00Z] PASSED [ 36%]
tests/test_db.py::test_horodatage_invalide_ou_sans_fuseau_refuse[] PASSED [ 37%]
tests/test_db.py::test_aucun_delete_hors_purge PASSED                    [ 38%]
tests/test_db.py::test_init_db_cree_une_fois_et_verifie_la_version PASSED [ 39%]
tests/test_db.py::test_transaction_annule_tout_en_cas_d_exception PASSED [ 40%]
tests/test_normalize.py::test_titre_affiche_regle_d8[True-Titre affich\xe9-Titre de base-Titre affich\xe9] PASSED [ 40%]
tests/test_normalize.py::test_titre_affiche_regle_d8[True--Titre de base-Titre de base] PASSED [ 41%]
tests/test_normalize.py::test_titre_affiche_regle_d8[True-   -Titre de base-Titre de base] PASSED [ 42%]
tests/test_normalize.py::test_titre_affiche_regle_d8[True-None-Titre de base-Titre de base] PASSED [ 43%]
tests/test_normalize.py::test_titre_affiche_regle_d8[False-Titre affich\xe9-Titre de base-Titre de base] PASSED [ 44%]
tests/test_normalize.py::test_strip_html PASSED                          [ 45%]
tests/test_normalize.py::test_date_quality[2026-DON620-Pneumonia-2026-10-10T15:00:00Z-ok] PASSED [ 45%]
tests/test_normalize.py::test_date_quality[2019DON-Autre-2019-05-01T00:00:00Z-ok] PASSED [ 46%]
tests/test_normalize.py::test_date_quality[1997-Autre-1997-05-01T00:00:00Z-ok] PASSED [ 47%]
tests/test_normalize.py::test_date_quality[-1996 - Global Cholera Update-1996-01-22T00:00:00Z-ok] PASSED [ 48%]
tests/test_normalize.py::test_date_quality[None-Avian influenza-2008-01-21T00:00:00Z-ok] PASSED [ 49%]
tests/test_normalize.py::test_date_quality[2020-DON286-Autre-2021-04-01T00:00:00Z-a_verifier] PASSED [ 50%]
tests/test_normalize.py::test_date_quality[-1996 - Global Cholera Update-2021-06-08T00:00:00Z-a_verifier] PASSED [ 50%]
tests/test_normalize.py::test_date_quality[DON588-Sans ann\xe9e-2013-01-01T00:00:00Z-ok] PASSED [ 51%]
tests/test_normalize.py::test_champs_de_reports_depuis_la_fixture PASSED [ 52%]
tests/test_normalize.py::test_url_publique_encode_le_slug PASSED         [ 53%]
tests/test_normalize.py::test_json_canonique_independant_de_l_ordre_des_cles PASSED [ 54%]
tests/test_normalize.py::test_champ_mal_type_ou_invalide_rejete[Id-None] PASSED [ 54%]
tests/test_normalize.py::test_champ_mal_type_ou_invalide_rejete[Id-] PASSED [ 55%]
tests/test_normalize.py::test_champ_mal_type_ou_invalide_rejete[Id-12] PASSED [ 56%]
tests/test_normalize.py::test_champ_mal_type_ou_invalide_rejete[UrlName-None] PASSED [ 57%]
tests/test_normalize.py::test_champ_mal_type_ou_invalide_rejete[Title-None] PASSED [ 58%]
tests/test_normalize.py::test_champ_mal_type_ou_invalide_rejete[Title-3] PASSED [ 59%]
tests/test_normalize.py::test_champ_mal_type_ou_invalide_rejete[UseOverrideTitle-true] PASSED [ 59%]
tests/test_normalize.py::test_champ_mal_type_ou_invalide_rejete[UseOverrideTitle-1] PASSED [ 60%]
tests/test_normalize.py::test_champ_mal_type_ou_invalide_rejete[UseOverrideTitle-None] PASSED [ 61%]
tests/test_normalize.py::test_champ_mal_type_ou_invalide_rejete[PublicationDateAndTime-hier] PASSED [ 62%]
tests/test_normalize.py::test_champ_mal_type_ou_invalide_rejete[PublicationDateAndTime-2026-10-10T15:00:00] PASSED [ 63%]
tests/test_normalize.py::test_champ_mal_type_ou_invalide_rejete[PublicationDateAndTime-20261010] PASSED [ 63%]
tests/test_normalize.py::test_champ_mal_type_ou_invalide_rejete[LastModified-None] PASSED [ 64%]
tests/test_normalize.py::test_champ_mal_type_ou_invalide_rejete[DonId-42] PASSED [ 65%]
tests/test_normalize.py::test_champ_obligatoire_manquant_rejete[Id] PASSED [ 66%]
tests/test_normalize.py::test_champ_obligatoire_manquant_rejete[UrlName] PASSED [ 67%]
tests/test_normalize.py::test_champ_obligatoire_manquant_rejete[Title] PASSED [ 68%]
tests/test_normalize.py::test_champ_obligatoire_manquant_rejete[UseOverrideTitle] PASSED [ 68%]
tests/test_normalize.py::test_champ_obligatoire_manquant_rejete[PublicationDateAndTime] PASSED [ 69%]
tests/test_normalize.py::test_champ_obligatoire_manquant_rejete[LastModified] PASSED [ 70%]
tests/test_normalize.py::test_champs_inutilises_acceptes_et_archives PASSED [ 71%]
tests/test_oms.py::test_pagination_complete_sans_doublon[5-0] PASSED     [ 72%]
tests/test_oms.py::test_pagination_complete_sans_doublon[5-1] PASSED     [ 72%]
tests/test_oms.py::test_pagination_complete_sans_doublon[5-3] PASSED     [ 73%]
tests/test_oms.py::test_pagination_complete_sans_doublon[5-9] PASSED     [ 74%]
tests/test_oms.py::test_pagination_complete_sans_doublon[1-4] PASSED     [ 75%]
tests/test_oms.py::test_pagination_complete_sans_doublon[2-0] PASSED     [ 76%]
tests/test_oms.py::test_pagination_a_l_echelle_de_la_phase_0 PASSED      [ 77%]
tests/test_oms.py::test_pagination_reponse_vide PASSED                   [ 77%]
tests/test_oms.py::test_ids_en_double_rendent_l_execution_partielle PASSED [ 78%]
tests/test_oms.py::test_total_annonce_different_du_recu_rend_l_execution_partielle PASSED [ 79%]
tests/test_oms.py::test_baisse_de_plus_de_1_pourcent_rend_l_execution_partielle PASSED [ 80%]
tests/test_oms.py::test_idempotence_second_run_sans_ajout PASSED         [ 81%]
tests/test_oms.py::test_champs_de_reports_depuis_les_5_enregistrements_de_la_fixture PASSED [ 81%]
tests/test_oms.py::test_enregistrements_invalides_rejetes_sans_arreter_le_run PASSED [ 82%]
tests/test_oms.py::test_enregistrement_corrige_est_repris_au_run_suivant PASSED [ 83%]
tests/test_oms.py::test_rejet_d_un_don_connu_ne_modifie_pas_la_base PASSED [ 84%]
tests/test_oms.py::test_champs_de_l_api_ajoutes_ne_font_pas_echouer PASSED [ 85%]
tests/test_oms.py::test_changement_de_contenu_cree_une_version PASSED    [ 86%]
tests/test_oms.py::test_retour_a_un_contenu_anterieur_cree_une_version PASSED [ 86%]
tests/test_oms.py::test_ecart_zero_sur_les_presents PASSED               [ 87%]
tests/test_oms.py::test_retrait_a_la_troisieme_absence PASSED            [ 88%]
tests/test_oms.py::test_execution_partielle_ne_compte_pas PASSED         [ 89%]
tests/test_oms.py::test_echec_ne_compte_pas_pour_le_retrait PASSED       [ 90%]
tests/test_oms.py::test_reapparition_annule_le_retrait[1] PASSED         [ 90%]
tests/test_oms.py::test_reapparition_annule_le_retrait[2] PASSED         [ 91%]
tests/test_oms.py::test_reapparition_annule_le_retrait[3] PASSED         [ 92%]
tests/test_oms.py::test_reapparition_annule_le_retrait[5] PASSED         [ 93%]
tests/test_oms.py::test_compteurs_d_absence_journalises PASSED           [ 94%]
tests/test_oms.py::test_run_sans_changement_apres_retrait_reste_inchange PASSED [ 95%]
tests/test_pipeline.py::test_echec_reseau_a_la_page_3_sur_5_base_inchangee PASSED [ 95%]
tests/test_pipeline.py::test_echec_de_source_ferme_l_execution PASSED    [ 96%]
tests/test_pipeline.py::test_echec_sur_le_decompte_est_journalise PASSED [ 97%]
tests/test_pipeline.py::test_conflit_de_slug_annule_toute_l_ecriture PASSED [ 98%]
tests/test_pipeline.py::test_exception_inattendue_en_cours_d_ecriture_annule_tout PASSED [ 99%]
tests/test_pipeline.py::test_run_reussi_ecrit_un_journal_complet PASSED  [100%]

============================= 122 passed in 17.27s =============================
```

## 2. Exigences de la phase et tests

| Exigence | Test(s) |
|---|---|
| 1. Pagination : N pages = N×taille moins les manquants, sans doublon ni perte ; dernière page partielle ; réponse vide | `test_oms.py::test_pagination_complete_sans_doublon` (6 cas « pages, manquants » : (5, 0), (5, 1), (5, 3), (5, 9), (1, 4), (2, 0) ; sans manquant, la dernière page est pleine et une page vide la suit ; sinon la dernière page est partielle), `::test_pagination_reponse_vide`, `::test_pagination_a_l_echelle_de_la_phase_0` (3199 DON simulés : 1 décompte + 32 pages) |
| 2. Idempotence : 0 ligne ajoutée au second run | `test_oms.py::test_idempotence_second_run_sans_ajout` (écarts de lignes : `reports` 0, `raw_payloads` 0, `report_versions` 0 ; seule `ingestion_runs` gagne 1 ligne), `test_cli.py::test_ingest_oms_succes_puis_second_run_idempotent` |
| 3. DON modifié : mise à jour et brut historisé | `test_oms.py::test_changement_de_contenu_cree_une_version`, `::test_retour_a_un_contenu_anterieur_cree_une_version` |
| 4. DON disparu : compteur, « absent » puis « retiré », retour à « présent » | `test_oms.py::test_retrait_a_la_troisieme_absence`, `::test_execution_partielle_ne_compte_pas`, `::test_echec_ne_compte_pas_pour_le_retrait`, `::test_reapparition_annule_le_retrait` (4 cas : après 1, 2, 3 et 5 absences), `::test_compteurs_d_absence_journalises` |
| 5. Échec réseau à la page 3 sur 5 : base inchangée, run échoué | `test_pipeline.py::test_echec_reseau_a_la_page_3_sur_5_base_inchangee` (instantané complet des 4 tables avant et après), `::test_conflit_de_slug_annule_toute_l_ecriture`, `::test_exception_inattendue_en_cours_d_ecriture_annule_tout` |
| 6. 4xx sans retry ; 5xx avec backoff puis échec propre | `test_client.py::test_4xx_jamais_de_retry` (400, 401, 403, 404, 410), `::test_429_quota_sans_retry`, `::test_5xx_retry_avec_backoff_puis_echec_propre` (500, 502, 503, 504 ; attentes 2, 8, 30 s), `::test_delais_exponentiels_plafonnes_sur_erreur_reseau`, `::test_reprise_apres_erreurs_transitoires` |
| 7. Champ manquant ou mal typé : rejet journalisé, le run continue | `test_oms.py::test_enregistrements_invalides_rejetes_sans_arreter_le_run`, `test_normalize.py::test_champ_mal_type_ou_invalide_rejete` (14 cas), `::test_champ_obligatoire_manquant_rejete` (6 cas) |

Invariants que `docs/01-invariants.md` assigne à Python et qui concernent cette phase, avec le nom de test imposé : I1 `test_db.py::test_connexion_active_les_cles_etrangeres` ; I2 `test_db.py::test_horodatage_converti_en_utc` ; I3 `test_db.py::test_aucun_delete_hors_purge` ; I6 `test_pipeline.py::test_echec_de_source_ferme_l_execution` ; I8 `test_oms.py::test_pagination_complete_sans_doublon` ; I9 `test_oms.py::test_ecart_zero_sur_les_presents` ; I10 `test_oms.py::test_retrait_a_la_troisieme_absence`, `::test_execution_partielle_ne_compte_pas`, `::test_reapparition_annule_le_retrait` ; I11 `test_oms.py::test_compteurs_d_absence_journalises` ; I43 `test_bruts.py::test_empreinte_sur_contenu_non_compresse` ; I51 `test_oms.py::test_changement_de_contenu_cree_une_version` ; I52 `test_oms.py::test_retour_a_un_contenu_anterieur_cree_une_version` ; méta-test `test_controle.py::test_vue_controle_vide_sur_base_coherente`. Les invariants Python des autres phases (observations, chiffres, classification, alertes, taille de l'asset) ne sont pas implémentés : voir `docs/02-notes.md` §4.

Les tests d'ingestion se terminent par `assert_base_coherente` : `PRAGMA integrity_check` = `ok`, `PRAGMA foreign_key_check` vide et vue `controle_invariants` vide. La règle de retrait (I10) est calculée en Python (`bisect` sur les exécutions complètes) et contrôlée en parallèle par la vue, écrite séparément en SQL : les deux doivent concorder.

## 3. Contrôles complémentaires

- `mypy --strict src` : « Success: no issues found in 10 source files ». `mypy --strict tests` (avec `MYPYPATH=tests`) : idem.
- **Mutations manuelles.** Pour vérifier que les tests détectent une régression, chacune des 18 modifications ci-dessous a été appliquée seule au code (par `sed`, sur une copie restaurée ensuite), puis la suite a été lancée avec `-x`. Les 18 sont détectées. Le script n'est pas conservé dans le dépôt. Une première version du test sur les exécutions partielles ne détectait pas la mutation 2 : le test a été renforcé (le run partiel tombe désormais en 3e position) puis les 18 mutations ont été rejouées.

| Mutation | Résultat de pytest |
|---|---|
| retrait à la 2e absence au lieu de la 3e | 1 failed, 31 passed in 1.53s |
| une exécution partielle compte pour le retrait | 1 failed, 108 passed in 11.07s |
| contenu comparé sans tenir compte du courant | 1 failed, 103 passed in 8.70s |
| réapparition : removed_run_id non remis à NULL | 1 failed, 112 passed in 14.00s |
| Id en double non détecté | 1 failed, 95 passed in 9.19s |
| compteur absent_count faux | 1 failed, 114 passed in 15.59s |
| compteur reappeared_count jamais incrémenté | 1 failed, 110 passed in 12.85s |
| numéro de version non incrémenté | 1 failed, 103 passed in 8.82s |
| statut inchange jamais attribué | 1 failed, 3 passed in 0.49s |
| baisse de plus de 1 % ignorée | 1 failed, 97 passed in 8.47s |
| un rejet interrompt le run | 1 failed, 8 passed in 0.48s |
| ROLLBACK remplacé par COMMIT | 1 failed, 48 passed in 4.34s |
| clés étrangères désactivées | 1 error in 0.31s |
| retry aussi sur les 4xx | 1 failed, 20 passed in 0.62s |
| backoff non plafonné | 1 failed, 12 passed in 0.57s |
| titre : OverrideTitle ignoré | 1 failed, 49 passed in 4.31s |
| published_at = LastModified | 1 failed, 63 passed in 4.58s |
| empreinte sur un contenu tronqué | 1 failed in 0.25s |

(« 1 error » pour la mutation des clés étrangères : `connect()` refuse de démarrer si `PRAGMA foreign_keys` ne vaut pas 1, ce qui est le comportement voulu pour I1.)

## 4. Run réel contre l'API OMS : impossible ici

**Cause.** La politique réseau de l'environnement refuse l'hôte `www.who.int:443` : la passerelle répond 403 au `CONNECT`. Ce n'est pas une panne de l'API. Je n'ai pas contourné ce refus.

**Tentative faite**, le 2026-10-14 à 09:35 UTC, avec la commande du pipeline lui-même (sans nouvelle tentative, pour ne pas attendre 40 s) :

```text
observatoire ingest-oms --db <scratchpad>/real.sqlite --contact <adresse> --max-retries 0 --timeout 20
code de sortie : 1
```

```json
{
  "run_id": 1,
  "status": "echec",
  "expected_count": null,
  "seen_count": null,
  "inserted_count": 0,
  "updated_count": 0,
  "absent_count": null,
  "removed_count": null,
  "reappeared_count": null,
  "rejected_count": 0,
  "http_requests": 1,
  "http_retries": 0,
  "error_kind": "reseau",
  "error_message": "ProxyError : 403 Forbidden (https://www.who.int/api/news/diseaseoutbreaknews?$top=0&$count=true)"
}
```

`observatoire db-check` sur cette base : `integrity_check` = `ok`, 0 violation de clé étrangère, `controle_invariants` vide, 0 DON, un seul run (`echec`, `reseau`). C'est le comportement attendu face à une panne (test 5), observé sur le vrai réseau. Ce n'est pas une mesure de l'API.

**Mesures demandées : toutes non mesurées.**

| Mesure | Valeur |
|---|---|
| Identifiants renvoyés par l'API (`expected_count` et `seen_count` du 1er run) | **non mesuré** |
| DON en base après le 1er run (`reports_distinct_external_id` de `db-check`) | **non mesuré** |
| Écart API / base | **non mesuré** |
| `inserted_count` du 2e run immédiat (attendu : 0) | **non mesuré** |
| Total affiché par la page de liste du site OMS | **non mesuré** |
| Écart base / site | **non mesuré** |

La simulation `test_pagination_a_l_echelle_de_la_phase_0` (3199 DON fictifs) vérifie la mécanique de pagination. Elle ne mesure rien sur l'API.

**Pour mémoire, mesure de la phase 0 (2026-10-13, hors périmètre de cette phase, pipeline différent)** : `@odata.count` = 3199, 3199 enregistrements récupérés, 3199 `Id` uniques, pager du site « 1-30 of 3199 items ». Écart 0. Ce chiffre n'est pas une mesure du pipeline de la phase 2 : l'objectif « écart 0 » du pipeline reste à constater.

**Procédure à exécuter depuis un poste ou un environnement qui autorise `www.who.int`** (aucune modification du code n'est nécessaire) :

```bash
pip install -e .            # Python 3.12
export OBSERVATOIRE_CONTACT=<votre adresse>
observatoire ingest-oms --db data/observatoire.sqlite     # 1er run : noter expected_count, seen_count, inserted_count
observatoire db-check   --db data/observatoire.sqlite     # noter reports_distinct_external_id, presence, controle_invariants
observatoire ingest-oms --db data/observatoire.sqlite     # 2e run immédiat : inserted_count doit valoir 0
observatoire db-check   --db data/observatoire.sqlite
```

Méthode de comptage sur le site (celle de la phase 0, la liste étant rendue côté navigateur) : ouvrir `https://www.who.int/emergencies/disease-outbreak-news` dans un navigateur, lire le total dans le pager (« 1-30 of N items »). Contrôle de D24 (« la liste du site lit-elle la même API ? ») : comparer les titres des 30 éléments de la page 1 aux 30 premiers enregistrements de l'API triés par `PublicationDate desc`. Le code de sortie `3` (run `partiel`) ou une valeur de `seen_count` différente de `expected_count` signalent un écart.
