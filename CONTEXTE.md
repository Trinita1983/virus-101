# Observatoire des maladies infectieuses : contexte du projet

Tu es un architecte logiciel senior. Je développe seul, avec un budget quasi nul (outils gratuits ou open source uniquement), un site en français : « Observatoire des maladies infectieuses ». Il croise les alertes mondiales (OMS, ECDC) et la surveillance française (Santé publique France, Réseau Sentinelles) pour dire au grand public : « voici ce qui circule cette semaine, en France et dans le monde ».

## Principes

- Mise à jour quotidienne (pas de « temps réel » : SPF et Sentinelles publient à la semaine, avec révisions).
- Site statique régénéré par GitHub Actions, zéro serveur. Base SQLite versionnée dans le repo (ou publiée en release), schéma portable vers PostgreSQL.
- Honnêteté sur les limites = exigences d'interface : badge « données de la semaine X », date de mise à jour et source sur chaque chiffre, niveau de fiabilité visible (officielle / semi-officielle / presse / communautaire), mention « sous-déclaration probable » quand pertinent, message « pas de conseil médical ».
- Code documenté, typé, testé, maintenable par une seule personne.

## Stack imposée

Python 3.12, httpx, pydantic v2, pytest, SQLite. Frontend : Astro, Observable Plot, Leaflet. CI : GitHub Actions. Hébergement : GitHub Pages ou Cloudflare Pages (usage commercial autorisé). Ne propose pas d'alternative sans raison solide.

## Sources v1

1. OMS Disease Outbreak News (API OData publique) : https://www.who.int/api/news/diseaseoutbreaknews. Vérifie les champs réels en interrogeant l'API, n'invente rien.
2. Réseau Sentinelles (Sentiweb) : séries hebdomadaires.
3. Santé publique France (Odissé) : indique-moi les jeux de données exacts à utiliser ; si tu n'es pas sûr d'une URL, dis-le au lieu de l'inventer.
4. ECDC : v2.

Exclus de la v1 : ProMED (pas d'API publique, conditions d'usage restrictives à vérifier).

Licences : liste les conditions de réutilisation de chaque source (OMS : non commerciale à vérifier) et propose les mentions légales adaptées.

## Modèle de données

Deux concepts distincts, ne pas les mélanger :

- `reports` : événements narratifs (OMS DON) : texte, URL, date de publication, maladie, pays, JSON brut conservé, chiffres extraits (cas, décès) avec statut d'extraction (auto / validé / incertain).
- `observations` : séries hebdomadaires (SPF, Sentinelles) : maladie, zone, semaine ISO, valeur, type (incidence / cumul), confirmés vs suspects, date de survenue vs date de publication, version de la donnée (gestion des révisions).
- `sources` : fiabilité, licence, fréquence de publication.

## Détection d'anomalies

Baseline saisonnière (mêmes semaines des années précédentes), seuil chiffré justifié, et backtest rétrospectif (ex. grippe 2024-25) avec taux de faux positifs mesuré. Pas de simple « hausse semaine sur semaine ».

## Alertes et monitoring

Telegram en v1. Email en v2 avec double opt-in et désinscription (RGPD). Alerte si une source change de format ou ne répond plus.

## Livrables, dans cet ordre

1. Architecture complète avec schéma.
2. Schéma de base de données (SQL).
3. Pipeline d'ingestion OMS (code + tests).
4. Structure du site et composants frontend.
5. Plan de déploiement pas à pas.

## Critères d'acceptation du pipeline OMS

- Nombre de DON ingérés = nombre sur le site OMS (écart 0, pagination OData gérée).
- Relance idempotente : 0 doublon.
- Retries avec backoff, User-Agent explicite, JSON brut archivé.
- Tests sur fixtures, sans appel réseau.
- Extraction des chiffres : règles déterministes d'abord, repli LLM seulement si échec, toujours marquée « à valider ».

## Méthode de travail

Le projet avance par phases, chacune avec son propre prompt. Ne fais que ce que la phase demandée exige, puis arrête-toi et attends mon feu vert.

---

## Annexe : précisions décidées depuis

Cette annexe ne modifie pas le texte ci-dessus. Elle signale les points que des décisions ultérieures précisent ou corrigent, pour qu'un lecteur du contexte seul ne s'y trompe pas.

| Point du contexte | Précision | Référence |
|---|---|---|
| « Nombre de DON ingérés = nombre sur le site OMS (écart 0) » | Écart mesuré sur les DON présents dans l'API au moment de l'exécution ; les DON retirés par l'OMS sont suivis à part (absents, puis retirés après 3 exécutions complètes). Validé le 2026-10-14 | `docs/01-decisions.md` D24 |
| Hébergement « usage commercial autorisé » | Inexact pour GitHub Pages (restriction d'usage commercial). Retenu : Cloudflare Pages. v1 sans publicité | `docs/00-sources.md` §7 et §10 |
| Base « versionnée dans le repo (ou publiée en release) » | Publiée en release : 82 à 87 Mo mesurés, au-dessus de l'avertissement GitHub de 50 MiB | `docs/01-decisions.md` D1 |
| Chiffres extraits (cas, décès) dans `reports` | Table `report_figures` : un chiffre par pays, définition de cas et période, avec son statut | `docs/01-decisions.md` D23 |
| Alertes Telegram | Livraison « au moins une fois » : un doublon reste possible, accepté le 2026-10-14 | `docs/01-decisions.md` D19, R14 |
| Baseline « mêmes semaines des années précédentes » | Fenêtre de ±3 semaines autour de la même date, sur 5 ans, au moins 3 années : règle la semaine 53. Décidé le 2026-10-14 | `docs/01-decisions.md` D32 |
| ProMED et ECDC | Hors v1, confirmé par la vérification des sources | `docs/00-sources.md` §5, §6 |
