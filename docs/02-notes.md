# Phase 2 : notes

Rédigé le 2026-10-14. Mesures et sortie de tests : `docs/02-validation.md`.

## 1. Utilisation

```bash
pip install -e ".[dev]"                      # Python 3.12 ; installation « editable » : le code lit db/schema.sql à la racine du dépôt
pytest                                       # 122 tests, sans réseau
export OBSERVATOIRE_CONTACT=<adresse>        # obligatoire : figure dans le User-Agent
observatoire ingest-oms --db data/observatoire.sqlite [--timeout 30] [--page-size 100] [--max-retries 3]
observatoire db-check   --db data/observatoire.sqlite
```

Codes de sortie de `ingest-oms` : 0 (`succes`, `inchange`), 1 (`echec`), 2 (configuration ou usage), **3 (`partiel`)**. `db-check` : 0 si la base est publiable (intégrité, clés étrangères, vue `controle_invariants` vides), 1 sinon.

Arborescence : `src/observatoire/` — `config.py` (réglages), `db.py` (connexion I1, création du schéma, transaction, `to_utc_z` I2), `cli.py` ; `oms/client.py` (HTTP, pagination, retries), `oms/models.py` (pydantic), `oms/normalize.py` (champs de `reports`, JSON canonique), `oms/ingest.py` (transaction, présence, journal), `oms/errors.py`. Tests dans `tests/` ; `fake_who.py` simule l'API OData.

## 2. Choix faits

1. **Lecture complète en mémoire, puis une seule transaction d'écriture.** Une panne réseau survient donc avant toute écriture. Une panne en cours d'écriture (contrainte SQL, exception) annule tout. Poids : 3199 DON × ~6,5 Ko ≈ 21 Mo en mémoire.
2. **Le run échoué est écrit après le ROLLBACK**, dans une seconde transaction (`echec`, cause dans `error_kind` et `error_message`). Une ligne `en_cours` n'est jamais validée en base : elle n'existe que dans la transaction du run, donc un processus tué ne laisse rien derrière lui. Écart avec le texte de l'architecture §3.1 (« ouvre une ligne `en_cours` »), sans effet sur I5 et I6. La concurrence est arbitrée par `BEGIN IMMEDIATE` (verrou d'écriture SQLite, attente de 30 s) et par le groupe `concurrency` de GitHub Actions.
3. **Pagination** : `$top=0&$count=true` d'abord, puis `$top=100&$skip=N&$orderby=PublicationDate desc`, exactement la forme vérifiée en phase 0 (`$` littéral dans l'URL). Arrêt sur la première page incomplète ou vide. Garde-fou : au plus `ceil(total/100) + 10` pages. `nextLink` n'est pas utilisé.
4. **Retries** : erreurs réseau, délais dépassés et 5xx, 3 nouvelles tentatives, attentes `min(30, 2 × 4^n)` = 2, 8, 30 s plus une part aléatoire jusqu'à 25 %. Jamais sur 4xx ; le 429 est une erreur `quota`. Erreurs : `reseau`, `http`, `quota`, `format` (JSON illisible, `value` ou `@odata.count` absent, contrainte SQL telle que `UrlName` en double, R7), `validation`, `controle`, `autre`.
5. **Run `partiel`** (écrit, mais ne compte pas pour le retrait, D24) si : au moins un enregistrement rejeté (`validation`) ; `Id` en double (le premier est gardé) ; `seen_count` ≠ `expected_count` ; total en baisse de plus de 1 % par rapport à la dernière exécution complète (architecture §7). La dernière règle protège contre une API tronquée qui ferait « retirer » tous les DON en 3 jours.
6. **`inchange`** = exécution complète sans DON inséré, mis à jour, retiré ni réapparu. Une exécution qui ne fait que faire passer des DON à « absent » est donc `inchange`.
7. **Validation pydantic stricte** des seuls champs lus : `Id`, `UrlName`, `Title`, `UseOverrideTitle`, `PublicationDateAndTime`, `LastModified` obligatoires ; `OverrideTitle`, `DonId`, `Summary` optionnels. Les autres champs (`Epidemiology` est `null` sur les DON anciens) sont archivés sans être contrôlés. `field_fingerprint` = sha256 de l'union triée des noms de champs reçus ; un changement est journalisé en avertissement, sans échec.
8. **Mapping de `reports`** : conforme au commentaire de `schema.sql` (D6, D7, D8). `summary` = champ `Summary` sans HTML (NULL s'il est vide ; pas de repli sur `Overview`). `url` = `…/disease-outbreak-news/item/{UrlName}`. Classification : `non_classe`, `geo_scope = 'inconnu'`, chiffres vides (`figures_payload_id` NULL), comme le schéma le prévoit pour la phase 3.
9. **Contenu inchangé = rien à écrire** sauf `last_seen_run_id` (mis à jour pour chaque DON reçu, par conception de D24). Le changement est détecté par sha256 du JSON canonique (clés triées, UTF-8) comparé à celui du contenu courant (I52), pas par `LastModified`.
10. **Retrait** : `removed_run_id` est recalculé à chaque run en Python (3e exécution complète après `last_seen_run_id`) ; la vue `reports_presence` du schéma sert de contrôle indépendant, pas de source.

## 3. Limites connues

- **Run réel non fait** (réseau refusé pour `www.who.int`). Non vérifiés contre la vraie API : la stabilité de la pagination sur les ex æquo de `PublicationDate`, et le contenu réel des 3199 enregistrements (champs requis nuls ou mal typés). Un champ requis nul chez un seul DON rend chaque run `partiel` (visible, mais le retrait est alors bloqué).
- **Ex æquo de tri (R10)** : 733 enregistrements partagent un horodatage. Une pagination instable donnerait des doublons ou des manques ; les contrôles (`Id` distincts, `seen_count` = `expected_count`) la rendraient `partiel`, sans l'empêcher.
- **Les rejets ne sont journalisés que dans `error_message`** du run (les 10 premiers, 2000 caractères au plus) et dans les logs. Le JSON d'un enregistrement rejeté n'est pas archivé.
- **Pas de recalcul des colonnes dérivées** (titre, `date_quality`) pour un contenu inchangé : si une règle de normalisation change, il faudra un rejeu explicite.
- `raw_payloads.retrieved_at` = début du run, pas l'heure de chaque page.
- **Aucune alerte écrite** (`alerts_log` : `nouveau_rapport`, `rapport_retire`, `ecart_comptage`, `format_modifie`…) : hors périmètre.
- Installation « editable » requise (le schéma est lu dans `db/`, hors du paquet).

## 4. Invariants Python non traités ici, car hors de la phase

Observations et sources France : I15, I21 à I26, I28, I29, I31, I34, I50, I54, I56, I60. Chiffres : I16, I57. Classification : I40, I41. Alertes : I45, I46. **I58 (taille de l'asset compressé avant envoi) : non fait**, car il relève de l'envoi de la base en release (GitHub Actions, exclu). Dites-moi si vous voulez la fonction de contrôle (taille d'un fichier contre deux seuils) dès maintenant.

## 5. Signalements sur le schéma et les documents (rien n'a été modifié)

1. **Rejets** : `ingestion_runs` n'a pas de compteur de rejets, et aucune table ne les garde. Proposition : une colonne `rejected_count` et/ou une table `ingestion_rejects (run_id, position, external_id, reason)`.
2. **I11 et le schéma** : `docs/01-invariants.md` dit que les trois compteurs « décrivent l'état de `reports_presence` à la fin de l'exécution », le commentaire du schéma dit de `removed_count` « DON retirés par cette exécution ». J'ai suivi le schéma : `absent_count` = DON absents (1 ou 2 exécutions complètes) à la fin du run, `removed_count` = retraits faits par ce run, `reappeared_count` = DON absents ou retirés à l'exécution complète précédente et reçus à nouveau.
3. **Architecture §3.1** : voir choix 2 (ligne `en_cours`).

## 6. Questions ouvertes

1. **Autoriser `www.who.int`** dans l'environnement (ou lancer la procédure de `docs/02-validation.md` §4 sur un poste) pour obtenir les mesures chiffrées et le contrôle « la liste du site lit-elle la même API ? ».
2. **Clé de tri secondaire** : `PublicationDate desc,Id` n'est pas vérifiée (architecture §3.2, R10). Je n'ai pas supposé qu'elle marche ; l'option `--order-by` permet de la tester lors du run réel.
3. **`date_quality`** : la règle exacte des 13 cas de la phase 1 n'est pas écrite. J'ai implémenté « l'année en tête du `DonId` ou du titre diffère de celle de `PublicationDateAndTime` ». Elle est à comparer au décompte attendu (11 + 2) lors du run réel.
4. **Un run `partiel` doit-il faire échouer le job CI** (code 3 non nul, retenu) ou seulement alerter ?
5. **`Summary` seul** pour `reports.summary`, ou repli sur `Overview` (renseigné pour 200 DON sur 200, alors que `Summary` l'est pour 105 sur 200) ? À trancher avec l'affichage (phase 4).
6. **Stockage des rejets** : voir §5.1.
