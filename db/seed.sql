-- =============================================================================
-- Données de référence v1 (à exécuter après schema.sql)
-- =============================================================================
-- Faits issus de docs/00-sources.md (vérifiés le 2026-10-13) et des décisions
-- de la section 10 de ce document.

INSERT INTO sources (code, name, publisher, homepage_url, api_base_url, reliability,
                     license_name, license_url, commercial_use, attribution,
                     publication_frequency, max_staleness_days, is_active, notes)
VALUES
('oms_don',
 'Disease Outbreak News',
 'Organisation mondiale de la Santé',
 'https://www.who.int/emergencies/disease-outbreak-news',
 'https://www.who.int/api/news/diseaseoutbreaknews',
 'officielle',
 'Conditions d''utilisation du site OMS (usage non commercial)',
 'https://www.who.int/about/policies/terms-of-use',
 'sur_autorisation',
 'Source : Organisation mondiale de la Santé (OMS), Disease Outbreak News. Lien vers l''article d''origine sur who.int.',
 'irreguliere', 45, 1,
 'Publications OMS sous CC BY-NC-SA 3.0 IGO (https://www.who.int/about/policies/publishing/copyright). Logo OMS interdit sans autorisation écrite. v1 sans publicité : pas de demande d''autorisation (décision 2026-10-13).'),

('sentinelles',
 'Réseau Sentinelles (Sentiweb)',
 'Réseau Sentinelles, IPLESP (INSERM / Sorbonne Université)',
 'https://www.sentiweb.fr',
 'https://www.sentiweb.fr/api/v1/datasets/rest',
 'officielle',
 'Conditions d''utilisation des données Sentinelles (usage non commercial, citation sans modification)',
 'https://www.sentiweb.fr/france/fr/?page=database',
 'interdit',
 'réseau Sentinelles, IPLESP (INSERM/Sorbonne Université), https://www.sentiweb.fr',
 'hebdomadaire', 14, 1,
 'Quota API mesuré : 15 requêtes / 600 s par IP (HTTP 429 au-delà, blocage d''IP possible). Données de moins de 3 semaines utilisables seulement après publication du bulletin. Couverture : France métropolitaine uniquement.'),

('spf_odisse',
 'Odissé',
 'Santé publique France',
 'https://odisse.santepubliquefrance.fr',
 'https://odisse.santepubliquefrance.fr/api/explore/v2.1',
 'officielle',
 'Licence Ouverte 2.0',
 'https://www.data.gouv.fr/pages/legal/licences/etalab-2.0',
 'autorise',
 'Santé publique France, Odissé, jeu de données cité avec sa date de dernière mise à jour.',
 'hebdomadaire', 14, 1,
 'Seuls les jeux dont la métadonnée license vaut « Licence ouverte 2.0 » sont ingérés ; les 35 jeux sans licence sont exclus (décision 2026-10-13).');

-- Référentiel des maladies : liste initiale, à compléter avec les règles de
-- classification des titres OMS (phase 3).
INSERT INTO diseases (code, label_fr, label_en) VALUES
('grippe',                 'Grippe',                                   'Influenza'),
('grippe_aviaire',         'Grippe aviaire (infection humaine)',       'Avian influenza'),
('bronchiolite',           'Bronchiolite',                             'Bronchiolitis'),
('covid19',                'COVID-19',                                 'COVID-19'),
('ira',                    'Infection respiratoire aiguë',             'Acute respiratory infection'),
('diarrhee_aigue',         'Diarrhée aiguë',                           'Acute diarrhoea'),
('varicelle',              'Varicelle',                                'Chickenpox'),
('mpox',                   'Mpox',                                     'Mpox'),
('rougeole',               'Rougeole',                                 'Measles'),
('legionellose',           'Légionellose',                             'Legionellosis'),
('cholera',                'Choléra',                                  'Cholera'),
('ebola',                  'Maladie à virus Ebola',                    'Ebola disease'),
('pneumonie_indeterminee', 'Pneumonie d''étiologie indéterminée',      'Pneumonia of undetermined etiology');
