# Une IA peut-elle vraiment transformer 50 $ en 5 000 $ sur Polymarket ?

Backtest sur données publiques d'une stratégie de paris virale, avec un tableau de bord Power BI.

## Le point de départ

Mi-septembre 2026, un post viral affirme qu'un agent IA, lâché avec 50 $ sur Polymarket, affichait 5 273 $ deux jours plus tard. L'agent suivait des règles simples : ne parier que si son estimation s'écarte du prix d'au moins 8 points, miser la moitié du critère de Kelly plafonnée à 6 % de la cagnotte, cinq paris ouverts au maximum, arrêt complet à −40 % depuis le plus haut.

Aucun relevé public ne prouve ce chiffre. Plutôt que de le croire ou de le rejeter, ce projet **rejoue ces règles sur l'historique réel des marchés** pour mesurer ce qu'elles donnent.

> Aucun pari réel n'est placé. Polymarket est bloqué en France depuis juillet 2026 (décision de l'ANJ) : le projet n'utilise que les données publiques, en lecture seule.

## Méthode

1. **Collecte** (`pmbt/collect.py`) : marchés binaires (Oui/Non) résolus entre janvier 2025 et octobre 2026, avec plus de 5 000 $ de volume, via l'API publique Gamma ; puis prix du « Oui » à J-7, J-3 et J-1 avant la clôture via l'API CLOB.
2. **Estimation** (`pmbt/strategies.py`) : l'article ne dit pas comment l'IA calcule sa probabilité, et on ne peut pas rejouer ce qui se disait sur X il y a un an. On compare donc trois estimateurs reproductibles :
   - **Calibration** : corrige le prix selon les écarts entre prix et résultats constatés en 2025, appliqués à 2026 (aucune information du futur).
   - **Momentum** : prolonge la tendance du prix entre J-7 et J-3.
   - **Aléatoire** : pile ou face avec les mêmes règles de mise, joué 300 fois. C'est la référence.
3. **Simulation** (`pmbt/simulate.py`) : la cagnotte est rejouée dans l'ordre chronologique, l'argent misé reste bloqué jusqu'à la résolution, et toutes les règles de l'article s'appliquent. Une variante « Kelly plein, sans garde-fous » montre ce que les règles de survie changent.
4. **Export** (`pmbt/backtest.py`) : tables en schéma en étoile pour Power BI dans `data/powerbi/`, et un résumé `data/summary.json` pour le portfolio.

### Hypothèses à connaître

| Hypothèse | Valeur | Pourquoi |
|---|---|---|
| Moment de la décision | 72 h avant la clôture | Une décision par marché, prise sur le prix de ce moment-là |
| Glissement | +1 point sur le prix payé | L'historique donne le dernier prix, pas l'écart achat/vente |
| Mise minimale | 1 $ | Sous ce montant, un ordre n'est pas réaliste |
| Liquidité | volume total ≥ 5 000 $ | La liquidité à l'instant T n'est pas disponible dans l'historique |
| Sortie | à la résolution | L'article sort parfois avant ; c'est une simplification |

## Lancer le projet

```bash
pip install -r requirements.txt
python -m pytest -q            # tests des règles de mise et des estimateurs
python run_pipeline.py all     # collecte (≈ 15 min) puis backtest
python run_pipeline.py backtest  # backtest seul, sur les données déjà collectées
```

Le pipeline tourne aussi sur GitHub Actions à chaque modification du code : tests, collecte, backtest, puis publication des données dans `data/`.

## Power BI

Le dossier [`powerbi/`](powerbi/) contient le guide d'assemblage du rapport, les mesures DAX et la maquette des quatre pages (vue globale, catégories, calibration, journal des paris).

## Structure

```
pmbt/            code Python (collecte, estimateurs, simulation, export)
tests/           tests unitaires (pytest)
data/raw/        données collectées
data/powerbi/    tables prêtes pour Power BI
powerbi/         guide, mesures DAX, thème
```

Rien ici n'est un conseil en investissement.
