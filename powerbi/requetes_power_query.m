// =============================================================================
// Requêtes Power Query des 7 tables, indépendantes des paramètres régionaux.
//
// Les CSV écrivent les décimales avec un point (0.0197). Avec les paramètres
// régionaux français, Power BI attend une virgule et lit mal ces nombres.
// Chaque requête ci-dessous convertit explicitement les colonnes avec la
// culture "en-US" : le fichier .pbix peut rester en français, l'affichage
// des nombres dans les visuels reste lui aussi en français (0,0197).
//
// Avant de coller les requêtes :
//   Accueil > Gérer les paramètres > Nouveau paramètre
//   Nom : DossierDonnees   Type : Texte
//   Valeur actuelle : le chemin du dossier des CSV, terminé par une barre
//   oblique inverse, ex. C:\Users\Gabriel\Documents\kit-powerbi-polymarket\donnees\
//
// Puis, pour chaque table : clic droit sur la requête > Éditeur avancé,
// remplacer tout le texte par le bloc correspondant, OK.
// Garder exactement le même nom de requête : les relations sont conservées.
// =============================================================================


// ---------- marches ----------------------------------------------------------
let
    Source = Csv.Document(File.Contents(DossierDonnees & "marches.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Entetes = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Types = Table.TransformColumnTypes(Entetes, {
        {"market_id", type text}, {"question", type text}, {"evenement", type text},
        {"categorie", type text}, {"date_cloture", type datetime}, {"volume", type number},
        {"resultat_yes", Int64.Type}, {"periode", type text},
        {"prix_j7", type number}, {"prix_j3", type number}, {"prix_j2", type number},
        {"prix_j1", type number}, {"tranche_prix_decision", type text}
    }, "en-US")
in
    Types


// ---------- paris --------------------------------------------------------------
let
    Source = Csv.Document(File.Contents(DossierDonnees & "paris.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Entetes = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Types = Table.TransformColumnTypes(Entetes, {
        {"strategie", type text}, {"market_id", type text},
        {"date_entree", type datetime}, {"date_cloture", type datetime}, {"sens", type text},
        {"prix_yes", type number}, {"prix_paye", type number}, {"proba_estimee", type number},
        {"ecart_points", type number}, {"pct_cagnotte", type number}, {"mise", type number},
        {"resultat_yes", Int64.Type}, {"gagne", Int64.Type}, {"gain", type number},
        {"cagnotte_apres", type number}
    }, "en-US"),
    Jour = Table.AddColumn(Types, "Jour", each DateTime.Date([date_entree]), type date)
in
    Jour


// ---------- cagnotte -----------------------------------------------------------
let
    Source = Csv.Document(File.Contents(DossierDonnees & "cagnotte.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Entetes = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Types = Table.TransformColumnTypes(Entetes, {
        {"date", type datetime}, {"cagnotte", type number}, {"strategie", type text}
    }, "en-US"),
    Jour = Table.AddColumn(Types, "Jour", each DateTime.Date([date]), type date),
    // Ordre des points dans le fichier : départage les paris résolus à la même minute
    Ordre = Table.AddIndexColumn(Jour, "ordre", 1, 1, Int64.Type)
in
    Ordre


// ---------- calibration --------------------------------------------------------
let
    Source = Csv.Document(File.Contents(DossierDonnees & "calibration.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Entetes = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Types = Table.TransformColumnTypes(Entetes, {
        {"tranche", type text}, {"n", Int64.Type}, {"prix_moyen", type number},
        {"freq_reelle", type number}, {"periode", type text}, {"categorie", type text}
    }, "en-US")
in
    Types


// ---------- strategies ---------------------------------------------------------
let
    Source = Csv.Document(File.Contents(DossierDonnees & "strategies.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Entetes = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Types = Table.TransformColumnTypes(Entetes, {
        {"strategie", type text}, {"estimateur", type text}, {"regles", type text},
        {"description", type text}
    }, "en-US")
in
    Types


// ---------- resultats ----------------------------------------------------------
let
    Source = Csv.Document(File.Contents(DossierDonnees & "resultats.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Entetes = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Types = Table.TransformColumnTypes(Entetes, {
        {"strategie", type text}, {"cagnotte_finale", type number}, {"roi_pct", type number},
        {"nb_paris", Int64.Type}, {"taux_reussite_pct", type number},
        {"drawdown_max_pct", type number}, {"plus_haut", type number}, {"arret_date", type date},
        {"ignores_ecart_insuffisant", Int64.Type}, {"ignores_limite_paris_ouverts", Int64.Type},
        {"ignores_mise_trop_faible", Int64.Type}
    }, "en-US")
in
    Types


// ---------- aleatoire_tirages --------------------------------------------------
let
    Source = Csv.Document(File.Contents(DossierDonnees & "aleatoire_tirages.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Entetes = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Types = Table.TransformColumnTypes(Entetes, {
        {"tirage", Int64.Type}, {"cagnotte_finale", type number}, {"nb_paris", Int64.Type},
        {"plus_haut", type number}
    }, "en-US")
in
    Types
