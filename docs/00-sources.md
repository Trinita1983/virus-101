# Phase 0 : vérification des sources

Vérifié le **2026-10-13**, avec de vrais appels (User-Agent explicite `ObservatoireMaladies-phase0/0.1`). Tout ce qui n'a pas pu être vérifié est marqué « non vérifié ».
Ce document n'est pas un avis juridique : les points de licence sont à trancher par le porteur du projet (voir la section finale).

## 1. Tableau de synthèse

| Source | URL testée (appel réel) | Format | Champs réels | Fréquence | Licence / conditions | Verdict v1 |
|---|---|---|---|---|---|---|
| **OMS DON** | `https://www.who.int/api/news/diseaseoutbreaknews` (200, `$count`, `$top`, `$skip`, `$orderby`, `$filter` testés) | JSON OData v4 | 22 champs (§2) | Irrégulière : 29 DON en 2026 au 2026-10-10 ; dernier : `2026-DON620` | Non commerciale (§2.5). Publicité = usage commercial → autorisation écrite requise | **Oui, techniquement. Licence à trancher** |
| **Sentinelles / Sentiweb** | `https://www.sentiweb.fr/api/v1/datasets/rest/incidence?indicator=3&geo=PAY&span=short&$format=csv` (200 puis **429** : voir quota) ; `/version` et `/indicators` (200) | JSON ou CSV | `week` (YYYYWW), `indicator`, `inc`, `inc_low`, `inc_up`, `inc100`, `inc100_low`, `inc100_up`, `geo_insee`, `geo_name` | Hebdomadaire, après le bulletin (mercredi après-midi) ; annuelle pour certains indicateurs | **« gratuitement utilisables à des fins non commerciales »** ; données récentes soumises à embargo (§3) | **À vérifier** (bloquant si publicité) |
| **SPF / Odissé** | `https://odisse.santepubliquefrance.fr/api/explore/v2.1/catalog/datasets` (388 jeux) ; `.../records`, `.../exports/csv` (200) | JSON (Opendatasoft Explore v2.1), CSV | Variables par jeu (§4) | Hebdomadaire pour les jeux SurSaUD (modifiés le 2026-10-07), annuelle pour les déclarations obligatoires | **Licence Ouverte 2.0** sur 353/388 jeux (réutilisation commerciale permise, attribution). **35 jeux sans licence déclarée**, dont les jeux IRA | **Oui** pour les jeux sous Licence Ouverte ; jeux sans licence : à vérifier |
| **ECDC** | `https://www.ecdc.europa.eu/en/publications-and-data/monitoring/weekly-threats-reports` (200) ; `https://opendata.ecdc.europa.eu/covid19/nationalcasedeath/json/` (200) | HTML + PDF (rapport hebdo) ; JSON (COVID uniquement) | Rapport narratif : aucun champ structuré trouvé. JSON COVID : `country`, `indicator`, `year_week`, `weekly_count`, `rate_14_day`, `cumulative_count`… | Rapport hebdomadaire (CDTR) ; JSON COVID **figé à 2023-47** | **CC BY 4.0**, usage commercial permis avec attribution (§5) | **Non en v1** (conforme à CONTEXTE : v2) |
| **ProMED** | `https://www.promedmail.org/` (200) | HTML, contenu derrière connexion | Non applicable | Non vérifié | Texte des CGU non lu (§6) | **Non** (sortir de la v1) |
| **GitHub Pages** | `https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits` | n/a | n/a | n/a | Usage commercial **restreint** (§7) | Oui avec réserve |
| **Cloudflare Pages** | `https://developers.cloudflare.com/pages/platform/limits/`, `https://www.cloudflare.com/terms/` | n/a | n/a | n/a | Aucune interdiction d'usage commercial trouvée (§7) | Oui |

## 2. OMS Disease Outbreak News

### 2.1 Point d'accès

`GET https://www.who.int/api/news/diseaseoutbreaknews`, réponse `application/json; odata.metadata=minimal; odata.streaming=true`. Aucune authentification. Aucun en-tête de limite de débit observé (environ 45 appels pendant la vérification, aucun refus). Cache côté serveur : `Cache-Control: public, max-age=0, s-maxage=900`.

### 2.2 Champs réels

Liste renvoyée par `@odata.context` (22 champs), confirmée sur les enregistrements :

`Id`, `LastModified`, `PublicationDate`, `DateCreated`, `IncludeInSitemap`, `SystemSourceKey`, `UrlName`, `ItemDefaultUrl`, `Response`, `FurtherInformation`, `Summary`, `PublicationDateAndTime`, `TitleSuffix`, `UseOverrideTitle`, `Title`, `Epidemiology`, `OverrideTitle`, `Advice`, `Assessment`, `Overview`, `DonId`, `Provider`.

- **Il n'y a aucun champ structuré** pour la maladie, le pays, le nombre de cas ou de décès. Tout est dans `Title` (ex. « Ebola disease caused by Bundibugyo virus - Democratic Republic of the Congo ») et dans le HTML des champs texte (`Overview`, `Epidemiology`, `Summary`, `Assessment`, `Advice`, `Response`, `FurtherInformation`). L'extraction maladie/pays/chiffres est donc entièrement à construire (règles déterministes).
- Sur les 200 DON les plus récents : `Overview` renseigné 200/200 ; `Summary` 105/200 ; `Epidemiology` 98/200 ; `Assessment` 106/200 ; `TitleSuffix` jamais renseigné.
- Langue : anglais seulement. Une version française via l'API n'a **pas** été testée (non vérifié).
- URL publique d'un DON : `https://www.who.int/emergencies/disease-outbreak-news/item/{UrlName}` (200 sur les 4 formes de `UrlName` testées).

### 2.3 Pagination et syntaxe

- Page par défaut : **50** éléments, avec `@odata.nextLink` (`http://www.who.int/api/news/diseaseoutbreaknews?$skip=50`, schéma `http` à normaliser en `https`).
- `$top=100` : OK. `$top=500` et `$top=1000` : **HTTP 400**. Le maximum exact entre 100 et 499 n'a pas été cherché. Utiliser 100.
- `$count=true` ajoute `@odata.count` ; `$top=0&$count=true` donne le total seul.
- `$orderby=PublicationDate desc` et `$filter=UrlName eq '...'` fonctionnent.
- Parcours complet réalisé : `$top=100&$skip=0,100,…&$orderby=PublicationDate desc` → 3199 enregistrements, 3199 `Id` uniques, 3199 `UrlName` uniques.
- Risque non vérifié : de nombreux enregistrements anciens ont une heure à `00:00:00`, donc des `PublicationDate` identiques. Un `$orderby` sur ce seul champ peut produire une pagination instable. À tester en phase 1 (piste : `$orderby=PublicationDate desc,Id`) ; ne pas supposer que ça marche.

### 2.4 Total de l'API contre la page de liste du site

| Mesure | Valeur |
|---|---|
| `@odata.count` de l'API | **3199** |
| Enregistrements récupérés par pagination complète | **3199** |
| Page de liste OMS (`/emergencies/disease-outbreak-news`), pager | « 1-30 of 3199 items », 107 pages |
| Écart | **0** |

Contrôle complémentaire : le 30e enregistrement de l'API (tri par date décroissante) est « Middle East respiratory syndrome coronavirus - Global update », 2025-12-24, ce qui correspond au dernier élément de la page 1 du site. L'égalité n'a été vérifiée que sur la page 1 et sur le total, pas sur chaque page.
La liste du site est rendue côté navigateur (le HTML brut ne contient aucun élément) ; le total a été lu dans le navigateur intégré.

**Le total concorde, mais le contenu de l'API n'est pas un « nombre de DON » propre.** Anomalies constatées :

1. **3199 enregistrements ne sont pas 3199 DON modernes.** `DonId` n'est renseigné que pour 1205 enregistrements. Les 1994 autres sont presque tous des archives antérieures à 2015 (quelques exceptions récentes : 1 en 2016, 1 en 2018, 1 en 2021 hors archives re-datées, etc.).
2. **Dates de publication fausses sur des archives** : 979 enregistrements ont `PublicationDate` en juin 2021 (migration du 2021-06-08), alors que leur titre indique 1996-2003 (ex. « 1996 - Typhoid fever in Algeria »). Aucun enregistrement n'a de `PublicationDate` en 2020 : les DON de 2020 portent une date de 2021 ou 2022 (ex. `2020-DON297` publié le 2022-01-05). La date de publication de l'API est donc **peu fiable avant 2023**.
   *Correction (phase 1, 2026-10-13) : c'est vrai pour `PublicationDate` seulement. Le champ `PublicationDateAndTime` donne des dates cohérentes de 1996 à 2026 (75 DON en 2020). Voir `docs/01-architecture.md` §3.4.*
3. **442 enregistrements** où l'année du `DonId` diffère de l'année de `PublicationDate`.
4. **`DonId` n'est pas unique** : 14 valeurs dupliquées, dont `2019DON` (27 enregistrements) et `1997` (5). Exemples utiles : `2022-DON398` correspond à deux enregistrements (`UrlName` `2022-DON398` et `2022-DON398_1`) ; `2020-DON286` est partagé avec un enregistrement d'avril 2021 qui n'est pas le même DON.
5. **Trois formes de `UrlName`** : `{année}-DON{n}` (418), `{année}_{mm}_{jj}-en` (1957), autres formes (824, ex. `DON588`, `1998DON236`, `16-may-2019-monkeypox-singapore-en`).
6. **Valeurs `DonId` hétérogènes** : chaîne vide ou absente selon les années.

Conséquence pour le critère « écart 0 » de CONTEXTE : à définir. Si l'objectif est « tous les enregistrements de l'API = tous les éléments du site » (3199 = 3199), il est atteint. Si l'objectif est « les DON numérotés », il faudra filtrer, et le site OMS ne donne alors plus de total comparable. Voir les points à trancher.

### 2.5 Conditions de réutilisation

- Conditions du site OMS (`https://www.who.int/about/policies/terms-of-use`) : extraits « pour la recherche ou l'étude privée, **mais pas pour la vente ni pour une utilisation liée à des fins commerciales** » ; toute utilisation « autre que pour des fins éducatives ou autres fins non commerciales » nécessite une « autorisation écrite préalable » ; toute utilisation doit citer l'OMS et l'URL de l'article.
- Politique de droit d'auteur (`https://www.who.int/about/policies/publishing/copyright`) : les publications de l'OMS sont sous **CC BY-NC-SA 3.0 IGO** (non commercial, partage dans les mêmes conditions). « Permission is required for commercial uses ». Le logo OMS ne peut pas être utilisé sans autorisation écrite. Les publications ne peuvent pas servir à promouvoir ou cautionner des produits ou services.
- **Non vérifié** : si un DON entre dans la catégorie « publications » de la politique CC BY-NC-SA, ou seulement dans celle du site. Dans les deux cas, l'usage commercial exige une permission. Il n'existe pas de page de conditions spécifique à l'API trouvée. Pour lever le doute : formulaire de permission OMS indiqué sur la page de copyright.
- **Site public avec publicité** : l'usage est vraisemblablement qualifié de commercial. Sans autorisation écrite de l'OMS, la v1 ne devrait pas afficher de publicité à côté de contenus OMS, ni reproduire de texte complet. Liens, titres, dates et chiffres factuels : zone grise, à trancher.

### 2.6 Fixture

`fixtures/who_don_sample.json` : 5 enregistrements bruts, choisis pour couvrir les cas limites : `2026-DON620` (le plus récent), `2024-DON528`, `2022-DON398_1` (suffixe `_1`, `DonId` partagé), `2008_01_21-en` (forme ancienne, sans `DonId`), `1996_01_22a-en` (archive 1996 re-datée 2021). Le fichier contient un bloc `_meta` (URL, date de récupération, total) et un tableau `value` dont les enregistrements sont ceux de l'API, sans transformation. Les enregistrements ont été relus via `ConvertFrom-Json` puis réécrits via `ConvertTo-Json` : la structure et les valeurs sont conservées, la mise en forme des octets ne l'est pas.

## 3. Réseau Sentinelles (Sentiweb)

### 3.1 Accès

API REST documentée sur `https://www.sentiweb.fr/france/fr/?page=api`. Base : `https://www.sentiweb.fr/api/v1/datasets/rest`.

- `GET /version` → un identifiant (`1791390597` le 2026-10-13). Sert à savoir si les données ont changé.
- `GET /indicators` (en-tête `Accept: application/json`) → liste des indicateurs et de leurs jeux (`inc-{indicateur}-{geo}[-ds2]`).
- `GET /incidence?indicator={id}&geo={PAY|RDD|REG}&span={all|short|last}&$format={json|csv}` → séries d'incidence.
- `GET /dataset?id=inc-3-PAY-ds2&span=short` avec `Accept: text/csv` (forme documentée ; non testée séparément).
- `geo=FR` ou vide renvoie `{"message":"IllegalCall: Invalid geo"}` : les codes valides sont `PAY` (métropole), `RDD` (régions post-2016), `REG` (régions pré-2016).
- Le paramètre `disease`, que j'avais essayé d'abord, n'apparaît pas dans la doc lue et semble ignoré : c'est `indicator` qui définit la maladie.
- Semaines au format ISO `YYYYWW` (ex. `202640`). Dernière semaine disponible au 2026-10-13 : **202640**.

### 3.2 Indicateurs hebdomadaires utiles (couverture jusqu'à 202640)

| id | Indicateur | Début des jeux listés |
|---|---|---|
| 3 | Syndromes grippaux | 201601 (jeu `ds2`) ; l'endpoint `incidence` renvoie une période 198444→202640 |
| 6 | Diarrhée aiguë | 201606 |
| 7 | Varicelle | 201601 (l'endpoint `incidence` indique 199049→202640) |
| 25 | Infection respiratoire aiguë (IRA) | 202016 |

Les autres indicateurs sont annuels ou arrêtés (ex. rougeole : 1985-2008 ; oreillons, zona, Lyme, coqueluche : jusqu'à 2025 ; IST bactérienne 2020-2025). Rupture de série possible entre jeux historiques et `ds2` : **non vérifiée** (important pour la baseline saisonnière).

### 3.3 Limites d'usage (vérifiées)

La doc annonce des « limites d'usage plus restrictives ». Mesuré : en-têtes **`X-RateLimit-Limit: 15`**, **`X-RateLimit-Policy: 15;w=600`**, soit **15 requêtes par 600 s**. Mon 16e appel a reçu **HTTP 429** (`X-RateLimit-Reset: 542`). Le blocage répété peut devenir un blocage d'IP de plusieurs jours selon la doc. Conséquences :

- Un job quotidien doit faire une requête `/version`, puis ne télécharger que si elle a changé, en `span=short` ou `last` plutôt que `all`.
- Les runners GitHub Actions partagent des IP : la limite par IP peut être atteinte par d'autres. **Non vérifié.**
- Prévoir un budget de moins de 15 appels par exécution, avec retry sur 429 en respectant `X-RateLimit-Reset`.

### 3.4 Conditions de réutilisation

Texte officiel : `https://www.sentiweb.fr/france/fr/?page=database` (section « Conditions d'utilisation des données », page datée du 28/05/2024).

- Les données sont « la propriété de l'INSERM et de Sorbonne Université » et « gratuitement utilisables **à des fins non commerciales** ».
- « Les données récentes (moins de 3 semaines) sont soumises à l'interprétation de notre équipe. L'utilisation des données récentes n'est autorisée sous quelque forme que ce soit **qu'à partir de la publication du bulletin de la semaine correspondante**. »
- Conditions : citation **sans modification** des données ou des textes d'interprétation ; légendes de graphique modifiables si elles restent lisibles ; citation de la source : « réseau Sentinelles, IPLESP, INSERM/Sorbonne Université, https://www.sentiweb.fr/ ».
- Une API OData Sentinelles est annoncée comme arrêtée au 31/12/2024 : ne pas l'utiliser.
- **Une page avec publicité semble incompatible avec « à des fins non commerciales ».** À confirmer par écrit auprès du réseau Sentinelles (page Contacts du site). Et « sans modification » contredit toute transformation de la série (z-scores, baselines) : à clarifier pour les calculs dérivés.

## 4. Santé publique France (Odissé)

### 4.1 Accès

Portail Opendatasoft : `https://odisse.santepubliquefrance.fr`. API Explore v2.1.

- Catalogue : `GET /api/explore/v2.1/catalog/datasets?limit=100&offset=N` → `total_count` = **388** jeux (4 pages de 100). Le paramètre `select=dataset_id,metas` provoque un **HTTP 400** : ne pas l'utiliser.
- Enregistrements : `GET /api/explore/v2.1/catalog/datasets/{id}/records?limit=100&order_by=date_complet%20desc`. `limit` maximal 100 ; **`offset + limit ≤ 10000`** (HTTP 400 au-delà, message d'erreur reçu). Pour les gros jeux, utiliser l'export.
- Export complet : `.../datasets/{id}/exports/csv` (200, `text/csv`).
- Quota (en-têtes observés sur l'export) : `X-RateLimit-Limit: 50000`, remise à zéro quotidienne (`X-RateLimit-Reset: 2026-10-14 00:00:00+00:00`). Largement suffisant.
- `metas.default.modified` et `data_processed` donnent la date de dernière mise à jour de chaque jeu : utile pour la détection de changement.

### 4.2 Jeux candidats (identifiants exacts du catalogue, tous présents le 2026-10-13)

**Sous Licence Ouverte 2.0 :**

| Jeu | Champs | Mis à jour | Lignes |
|---|---|---|---|
| `grippe-passages-aux-urgences-et-actes-sos-medecins-france` (existent aussi `_reg`, `-departement`) | `date_complet`, `semaine`, `sursaud_cl_age_gene`, `taux_passages_grippe_sau`, `taux_hospit_grippe_sau`, `taux_actes_grippe_sos` | 2026-10-07 | 1800 |
| `bronchiolite-passages-aux-urgences-et-actes-sos-medecins-france` | `date_complet`, `semaine`, `sursaud_cl_age_gene`, `taux_passages_bronchio_sau`, `taux_hospit_bronchio_sau`, `taux_actes_bronchio_sos` | 2026-10-07 | 353 |
| `covid-19-passages-aux-urgences-et-actes-sos-medecins-france` | idem avec `covid` | 2026-10-07 | 1800 |
| `infections-respiratoires-aigues-ira-passages-aux-urgences-et-actes-sos-medecins-france` | non inspectés | 2026-10-07 | non vérifié |
| `mpox-incidence-selon-lage-france` | `date_complet`, `semaine`, `clage_mkp`, `n_conf`, `n_cum_conf` | 2026-10-07 | 985 |
| `rougeole-donnees-declaration-obligatoire` | `annee`, `libgeo`, `reglib`, `mdo_cl_age_rougeole`, `rou`, `population`, `tx`, `dep`, `reg` | 2026-05-18 | 19017 (annuel) |
| `legionellose-donnees-declaration-obligatoire` | `annee`, `reglib`, `libgeo`, `legio`, `taux`, `population`, `dep`, `reg` | 2026-09-04 | 2812 (annuel) |
| `arboviroses-donnees-declaration-obligatoire` | non inspectés | 2026-08-24 | non vérifié |
| `ira-cepidc`, `ira-hospit-casgraves`, `sum-eau-indicateurs` | non inspectés | 2026-10-05 à 10-09 | non vérifié |

Dernière semaine du jeu grippe France : `2026-S40` (`date_complet` = lundi de la semaine, `2026-09-28`), alors que le jeu a été modifié le 2026-10-07 : ~1 semaine de décalage entre la semaine épidémiologique et la publication.

**Sans licence déclarée dans les métadonnées (35 jeux)** : notamment `ira-virologie-renal` (mis à jour le 2026-10-13, 125 048 lignes), `ira-virologie-relab`, `ira-seuils` (seuils d'intensité, 61 lignes), `ira-ville-rusmg` et `ira-virologie-rusmg` (**données du Réseau Sentinelles** hébergées sur Odissé), `ira-point-de-situation`, `ma-region-epidemies-hivernales-grippe`. L'absence de licence n'est pas une autorisation. Voir les points à trancher.

Un jeu `ira-seuils` publie déjà des seuils d'intensité (`s0` à `s4_treseleve`, `smax`) : à comparer plus tard avec nos propres seuils.

### 4.3 Conditions de réutilisation

La Licence Ouverte 2.0 (texte officiel : `https://www.data.gouv.fr/pages/legal/licences/etalab-2.0`) accorde un droit non exclusif et gratuit de réutilisation, « **à des fins commerciales ou non** », dans le monde entier et sans limite de durée, y compris adaptation, transformation et diffusion. Le texte exige de mentionner la source (et la date de dernière mise à jour). Les modalités exactes de la mention sont dans le texte intégral, à relire avant rédaction des mentions légales. Une réutilisation avec publicité est donc permise pour les jeux effectivement sous cette licence.

## 5. ECDC

- Rapport hebdomadaire CDTR : `https://www.ecdc.europa.eu/en/publications-and-data/monitoring/weekly-threats-reports` liste des pages HTML du type `.../communicable-disease-threats-report-3-9-october-week-41` (semaine 41 la plus récente le 2026-10-13). Les slugs ne sont pas réguliers (`...-12-18-september-week-38`, `...-1-7-august-2026-week-32`) : prévoir de partir de la page de liste, pas de reconstruire l'URL.
- Pas d'API de rapport trouvée. Pas de champs structurés : texte narratif (HTML/PDF). Flux RSS par taxonomie : `https://www.ecdc.europa.eu/en/rss-feeds` (liste de `.../en/taxonomy/term/{id}/feed`). **Non vérifié** : lequel correspond au CDTR.
- `https://opendata.ecdc.europa.eu/covid19/nationalcasedeath/json/` répond (3,7 Mo, 12 648 lignes) mais la dernière `year_week` est **2023-47** : jeu figé.
- Atlas de surveillance `https://atlas.ecdc.europa.eu/public/index.aspx` : HTML interactif, **aucune API publique testée**.
- Licence (`https://www.ecdc.europa.eu/en/ecdc-intellectual-property-notices`) : contenu ECDC sous **CC BY 4.0**, réutilisation « for commercial or non-commercial purposes » à condition de citer l'ECDC comme créateur, de donner un lien vers la licence CC BY 4.0 et d'indiquer toute modification. Les contenus de tiers ne sont pas couverts. Pour les données des bases : mention imposée « Dataset provided by ECDC based on data provided by public health authorities, scientific institutes or health care providers in the relevant reporting countries and/or by WHO ». Le logo ECDC est interdit sans autorisation.
- **Verdict : hors v1** (cohérent avec CONTEXTE). Aucun accès automatisable fiable et structuré trouvé.

## 6. ProMED

- `https://www.promedmail.org/` (200) : l'accueil affiche « Login or Subscribe to unlock full articles ». Le contenu complet est donc **derrière un abonnement**.
- Pages « Terms & Conditions » (`https://www.promedmail.org/terms-conditions`) : seul le sommaire s'est affiché dans mon outil (clauses « Prohibited Uses », etc.). **Le texte des clauses n'a pas pu être lu : non vérifié.** Pour le vérifier : ouvrir la page dans un navigateur classique, ou écrire à ISID.
- Aucune API publique trouvée : `https://promedmail.org/feed/` renvoie 404.
- **Verdict : non, hors v1.** Pas d'accès automatisable fiable, contenu en partie payant, conditions d'usage non lues.

## 7. Hébergement gratuit : usage commercial

- **GitHub Pages** (`https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits`) : « GitHub Pages is not intended for or allowed to be used as a free web-hosting service to run your online business, e-commerce site, or any other website that is primarily directed at either facilitating commercial transactions or providing commercial software as a service (SaaS) ». Un site d'information avec publicité n'est pas explicitement visé, mais **la présentation de CONTEXTE (« usage commercial autorisé ») est inexacte** : la restriction existe et son application à un site à publicité est une interprétation à votre charge. Limites : site publié ≤ 1 Go, dépôt source recommandé ≤ 1 Go, bande passante « soft » 100 Go/mois, déploiement 10 minutes maximum, 10 builds/heure (ne s'applique pas à un workflow GitHub Actions personnalisé).
  Non vérifié : si les Pages d'un dépôt **privé** sont disponibles en offre gratuite (en général non : à confirmer dans la doc GitHub). Le dépôt `Trinita1983/virus-101` est actuellement lié en HTTPS ; sa visibilité (public/privé) n'a pas été vérifiée.
- **Cloudflare Pages** (`https://developers.cloudflare.com/pages/platform/limits/`) : Free = 500 builds/mois, 1 build à la fois, 20 000 fichiers, 25 MiB par fichier, 100 domaines personnalisés par projet, timeout de build 20 minutes. Le Self-Serve Subscription Agreement (`https://www.cloudflare.com/terms/`, dernière mise à jour 2025-09-12) ne contient pas d'interdiction générale d'usage commercial des services gratuits dans les extraits relus (recherche des mots « commercial », « Pages »). Il interdit de traiter des données de carte bancaire sur une propriété web utilisant des services gratuits et prévoit que les services gratuits peuvent être modifiés ou interrompus. **Non vérifié** : conditions spécifiques à Pages au-delà de ce contrat, et traitement de la publicité (non mentionnée dans les extraits). La lecture complète des 40 700 caractères du contrat n'a pas été faite.
- Les deux offres sont donc compatibles avec un site statique d'information. Cloudflare Pages est la moins ambiguë sur l'usage commercial d'après ce que j'ai pu lire.

## 8. Recommandations v1

1. **Santé publique France (Odissé), jeux sous Licence Ouverte 2.0** : seule source qui autorise à la fois l'automatisation et la réutilisation commerciale. À mettre au cœur de la v1.
2. **OMS DON** : technique prête (API stable, total égal au site). Licence non commerciale : **ne pas publier tant que la question de la publicité n'est pas tranchée**.
3. **Sentinelles** : API exploitable mais quota très bas (15 requêtes / 10 min) et licence non commerciale avec embargo des données récentes. À garder en v1 **uniquement** si le site n'a pas de publicité, ou après accord écrit.
4. **ECDC** et **ProMED** : hors v1.

## 9. Points que vous devez trancher

1. **Publicité : oui ou non ?** C'est la décision qui conditionne l'OMS (usage commercial interdit sans autorisation écrite) et Sentinelles (non commercial). Si publicité : demander des autorisations écrites à l'OMS et au réseau Sentinelles, ou se limiter à Odissé.
2. **Faut-il demander une autorisation à l'OMS ?** Je n'ai pas pu établir si un DON relève de la CC BY-NC-SA (publications) ou des seules conditions du site. Dans les deux cas : permission écrite pour un usage commercial.
3. **Sentinelles : « sans modification »** des données. Autorise-t-on nos calculs dérivés (baseline saisonnière, seuils, z-scores) ? À demander au réseau.
4. **Jeux Odissé sans licence déclarée** (35, dont `ira-virologie-renal`, `ira-ville-rusmg`, `ira-seuils`) : les exclure de la v1, ou écrire à SPF pour obtenir la licence ?
5. **Définition de « écart 0 » pour l'OMS** : 3199 enregistrements (tout ce que renvoie l'API) ou seulement les DON numérotés (avec `DonId`) ? Et que faire des 979 archives re-datées de juin 2021, des DON de 2020 re-datés de 2021-2022, et des `DonId` en doublon ?
6. **Clé d'identité d'un DON** : `Id` (GUID, unique sur 3199) plutôt que `DonId` (non unique) ? Je recommande `Id`.
7. **Hébergement** : GitHub Pages (restriction « primarily commercial transactions / SaaS », site d'information avec publicité = zone grise) ou Cloudflare Pages (pas d'interdiction trouvée) ? Et visibilité publique ou privée du dépôt ?
8. **Mentions légales** : relire le texte intégral de la Licence Ouverte 2.0 pour la formule d'attribution exacte avant de rédiger les mentions.
9. **Calendrier de publication** : Sentinelles interdit l'usage des données récentes avant la publication du bulletin de la semaine (mercredi après-midi). Accepte-t-on de n'afficher les données de la semaine qu'à partir de cette publication ?

## 10. Décisions prises (2026-10-13)

| # | Point | Décision |
|---|---|---|
| 1 | Publicité | **Aucune publicité en v1.** Site d'information gratuit. À rouvrir seulement avec autorisations écrites (OMS, Sentinelles). |
| 2 | Autorisation OMS | **Non demandée** (pas d'usage commercial). Obligations : citer l'OMS et l'URL de chaque DON, ne pas utiliser le logo OMS. |
| 3 | Calculs dérivés sur Sentinelles | **Acceptés.** Afficher les chiffres Sentinelles tels quels, présenter les calculs (seuils, baseline) à part, et écrire au réseau Sentinelles pour confirmation. |
| 4 | Jeux Odissé sans licence (35) | **Exclus de la v1.** Seuls les jeux sous Licence Ouverte 2.0 sont utilisés. |
| 5 | Écart 0 OMS et clé d'identité | Critère : **3199 enregistrements** de l'API = total du site. Clé d'identité : **`Id`** (GUID), pas `DonId`. |
| 6 | Hébergement | **Cloudflare Pages.** |

Points restant ouverts : relire le texte intégral de la Licence Ouverte 2.0 pour la formule d'attribution (§9.8) ; décider de l'affichage des données Sentinelles avant publication du bulletin hebdomadaire (§9.9).
