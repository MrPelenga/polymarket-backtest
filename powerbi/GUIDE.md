# Assembler le rapport Power BI

Compter environ une heure. Tout se fait dans Power BI Desktop (gratuit, Windows).

## 1. Importer les tables

**Accueil > Obtenir les données > Texte/CSV**, puis importer les 7 fichiers de `data/powerbi/` :

| Fichier | Rôle | Une ligne = |
|---|---|---|
| `marches.csv` | dimension | un marché (question, catégorie, prix J-7/J-3/J-2/J-1, résultat) |
| `strategies.csv` | dimension | une stratégie testée |
| `paris.csv` | fait | un pari simulé |
| `cagnotte.csv` | fait | un point de la courbe de cagnotte |
| `calibration.csv` | fait | une tranche de prix (période × catégorie) |
| `aleatoire_tirages.csv` | fait | un des 300 tirages de la stratégie aléatoire |
| `resultats.csv` | référence | le résumé chiffré par stratégie (pour contrôler les mesures) |

Dans **Transformer les données** (Power Query) :

- Choisir **Fichier > Options > Paramètres régionaux : Anglais (États-Unis)** pour ce fichier, sinon les décimales à point sont mal lues. Ou, colonne par colonne : *Modifier le type > Utilisation des paramètres régionaux > Anglais (États-Unis)*.
- Mettre en type **Date/Heure** : `marches[date_cloture]`, `paris[date_entree]`, `paris[date_cloture]`, `cagnotte[date]`.
- Ajouter une colonne `Jour` (type Date) dans `cagnotte` et `paris` : sélectionner `date` (ou `date_entree`), *Ajouter une colonne > Date > Date uniquement*, puis renommer la colonne en `Jour`. Ne pas la nommer `Date` : Power BI ne distingue pas les majuscules et la confondrait avec la colonne `date` existante.
- `market_id` en **Texte** dans `marches` et `paris`.

## 2. Table Calendrier

**Modélisation > Nouvelle table** :

```DAX
Calendrier =
ADDCOLUMNS (
    CALENDAR ( DATE ( 2025, 1, 1 ), DATE ( 2026, 12, 31 ) ),
    "Année", YEAR ( [Date] ),
    "Mois", FORMAT ( [Date], "mmm yyyy" ),
    "MoisTri", YEAR ( [Date] ) * 100 + MONTH ( [Date] )
)
```

Marquer comme table de dates, et trier `Mois` par `MoisTri`.

## 3. Relations (vue Modèle)

| De (plusieurs) | Vers (un) |
|---|---|
| `paris[market_id]` | `marches[market_id]` |
| `paris[strategie]` | `strategies[strategie]` |
| `cagnotte[strategie]` | `strategies[strategie]` |
| `resultats[strategie]` | `strategies[strategie]` |
| `cagnotte[Jour]` | `Calendrier[Date]` |
| `paris[Jour]` | `Calendrier[Date]` |

Toutes en filtrage **unidirectionnel**. `calibration` et `aleatoire_tirages` restent isolées : elles sont filtrées par leurs propres segments.

## 4. Mesures

Créer une table vide `_Mesures` (*Accueil > Entrer des données*, nommer la table `_Mesures`, *Charger*).

**Méthode rapide (recommandée)** : ouvrir la **vue TMDL** (icône à gauche, sous la vue Modèle), coller tout le contenu de [`mesures.tmdl`](mesures.tmdl), puis cliquer sur **Appliquer**. Les 24 mesures sont créées d'un coup, rangées en dossiers et déjà formatées. Il faut que les 7 tables, la table `Calendrier` et les colonnes `Jour` existent avant.

**Méthode manuelle** : coller les mesures de [`mesures.dax`](mesures.dax) une par une (*Nouvelle mesure*). Formats : pourcentages pour `ROI…`, `Taux de réussite`, `Drawdown…`, `Part des tirages gagnants` ; devise $ pour les montants.

**Contrôle** : dans un tableau avec `strategies[strategie]`, `Cagnotte finale`, `Nb paris` et `Taux de réussite`, les valeurs doivent être identiques à celles de `resultats.csv`.

## 5. Les quatre pages

Thème : *Affichage > Thèmes > Parcourir* et choisir [`theme.json`](theme.json).

### Page 1 · Vue globale
- Segment `strategies[strategie]` (boutons).
- 5 cartes : `Cagnotte finale`, `ROI cagnotte`, `Nb paris`, `Taux de réussite`, `Drawdown max`.
- Graphique en courbes : axe `Calendrier[Date]`, valeur `Cagnotte à date`, légende `strategies[strategie]`. Ajouter une ligne constante à 50 (*Analytique > Ligne constante*).
- Zone de texte : la question du projet et la conclusion en une phrase.

### Page 2 · Par catégorie
- Barres horizontales : `marches[categorie]` × `ROI sur mises`, filtre de page `strategie = calibration`.
- Matrice : lignes `marches[categorie]`, colonnes `strategies[strategie]`, valeurs `Nb paris`, `Taux de réussite`, `ROI sur mises`.
- Barres : `marches[categorie]` × `Brier marché J-1` (quelle catégorie le marché prédit le mieux).
- C'est la page qui teste le « pivot météo » de l'article.

### Page 3 · Calibration
- Segments `calibration[periode]` et `calibration[categorie]` (sélection unique, `Toutes` par défaut).
- Nuage de points : X = `Prix moyen`, Y = `Fréquence réelle`, détails = `calibration[tranche]`, taille = somme de `n`. Ajouter la diagonale (*Analytique > Ligne de tendance* sur une série y = x, ou une image de fond).
- Barres : `calibration[tranche]` × `Écart de calibration (points)`.
- Lecture : un point sous la diagonale = le marché surestime cette tranche.

### Page 4 · Journal et hasard
- Tableau : `paris[date_entree]`, `marches[question]`, `marches[categorie]`, `paris[sens]`, `paris[prix_paye]`, `paris[proba_estimee]`, `paris[ecart_points]`, `paris[mise]`, `paris[gain]`, avec mise en forme conditionnelle sur `gain`.
- Histogramme : `aleatoire_tirages[cagnotte_finale]` regroupé en classes (*clic droit > Nouveau groupe > Taille de classe 25*), valeur = `Nb tirages`.
- Cartes : `Part des tirages gagnants`, `Tirage médian`, `Meilleur tirage`.
- Message : même au hasard, quelques tirages finissent très haut. Un seul résultat spectaculaire ne prouve pas une stratégie.

## 6. Publier

Enregistrer en `polymarket-backtest.pbix`, puis faire une capture de chaque page (PNG, 1600 px de large) pour le portfolio et le README.
