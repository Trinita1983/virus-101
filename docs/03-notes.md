# Phase 3 : notes

Rédigé le 2026-10-14. Rien dans le schéma n'a été modifié.

## 1. Le schéma peut-il stocker la précision d'un chiffre ? Non

**Constat** (`db/schema.sql`, table `report_figures`, D23). Une ligne porte `value INTEGER NOT NULL`, `measure`, `case_definition` (`total`, `confirme`, `probable`, `suspect`, `non_precise`), `period_start`, `as_of`, `method`, `status` et `evidence TEXT NOT NULL` (la phrase source). Aucune colonne ne dit si la valeur est exacte, approchée (`environ`), une borne basse (`au_moins`), une borne haute (`au_plus`) ou une borne de fourchette. Trois conséquences :

1. **« about 200 » et « 200 » sont indiscernables** dans les colonnes ; le mot d'approximation n'existe que dans `evidence`, en texte libre, non interrogeable. Le site ne pourrait pas écrire « environ » ou « au moins » sans relire la phrase, et la règle de CONTEXTE (ne jamais perdre un qualificatif en silence) ne serait pas tenue par la structure.
2. **Une fourchette ne peut pas être stockée en deux lignes.** L'index unique `report_figures_one_value` (I36) porte sur (version brute, rapport, pays, mesure, définition, `period_start`, `as_of`). Les deux bornes d'une fourchette ont les mêmes valeurs pour toutes ces colonnes : la seconde insertion est refusée. Une borne serait donc perdue ou écrasée.
3. `case_definition` décrit le type de cas (confirmé, suspect...), pas la précision du nombre : y loger `environ` mélangerait deux notions.

**Proposition** (à valider ; non appliquée). Ajouter la colonne et l'inclure dans l'unicité :

```sql
ALTER TABLE report_figures ADD COLUMN precision TEXT NOT NULL DEFAULT 'exact'
    CHECK (precision IN ('exact', 'environ', 'au_moins', 'au_plus',
                         'fourchette_basse', 'fourchette_haute'));
DROP INDEX report_figures_one_value;
CREATE UNIQUE INDEX report_figures_one_value ON report_figures (
    raw_payload_id, report_id, COALESCE(country_iso3, ''), measure, case_definition,
    COALESCE(period_start, ''), COALESCE(as_of, ''), precision);
```

Vérifié le 2026-10-14 sur une base en mémoire créée depuis `db/schema.sql` : le `ALTER TABLE ... ADD COLUMN` est accepté sur la table `STRICT` (valeur par défaut `exact`, donc aucune ligne existante à reprendre) et la vue `report_figures_current` fonctionne après la modification. Pas de reconstruction de table. Les valeurs sont celles de la colonne `precision` du jeu de référence (`docs/03-guide-etiquetage.md`).

**Ce qu'il resterait à faire si vous acceptez** : mettre à jour `db/schema.sql`, le texte de I36 dans `docs/01-invariants.md`, les listes de `db/check_schema.py` et `db/check_invariants.py` qui citent l'index, et la liste des écarts de portabilité PostgreSQL (`architecture` §6) si nécessaire. Une borne supérieure stricte (« fewer than 30 ») est rangée en `au_plus` avec la valeur écrite ; la stricte inégalité n'est pas représentée, ni dans le guide ni dans cette proposition.
