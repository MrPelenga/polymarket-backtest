# Une IA peut-elle vraiment transformer 50 $ en 5 000 $ sur Polymarket ?

Backtest sur données publiques d'une stratégie de paris virale, avec un tableau de bord Power BI.

## Le point de départ

Mi-septembre 2026, un post viral affirme qu'un agent IA, lâché avec 50 $ sur Polymarket, affichait 5 273 $ deux jours plus tard. L'agent suivait des règles simples : ne parier que si son estimation s'écarte du prix d'au moins 8 points, miser la moitié du critère de Kelly plafonnée à 6 % de la cagnotte, cinq paris ouverts au maximum, arrêt complet à −40 % depuis le plus haut.

Aucun relevé public ne prouve ce chiffre. Plutôt que de le croire ou de le rejeter, ce projet **rejoue ces règles sur l'historique réel des marchés** pour mesurer ce qu'elles donnent.

> Aucun pari réel n'est placé. Polymarket est bloqué en France depuis juillet 2026 (décision de l'ANJ) : le projet n'utilise que les données publiques, en lecture seule.

## Méthode

1. **Collecte** (`pmbt/collect.py`) : les 292 322 marchés clos entre janvier 2025 et octobre 2026 avec plus de 5 000 $ de volume, via l'API publique Gamma. On garde les marchés à deux issues (Oui/Non, ou « équipe A vs B ») ouverts au moins 2,5 jours : 115 764 marchés. Pour un échantillon de 10 000, réparti par mois, l'API CLOB donne le prix de la première issue à J-7, J-3, J-2 et J-1 avant la clôture.
2. **Estimation** (`pmbt/strategies.py`) : l'article ne dit pas comment l'IA calcule sa probabilité, et on ne peut pas rejouer ce qui se disait sur X il y a un an. On compare donc trois estimateurs reproductibles :
   - **Calibration** : corrige le prix selon les écarts entre prix et résultats constatés en 2025, appliqués à 2026 (aucune information du futur).
   - **Momentum** : prolonge la tendance du prix entre J-2 et J-1.
   - **Aléatoire** : pile ou face avec les mêmes règles de mise, joué 300 fois. C'est la référence.
3. **Simulation** (`pmbt/simulate.py`) : la cagnotte est rejouée dans l'ordre chronologique, l'argent misé reste bloqué jusqu'à la résolution, et toutes les règles de l'article s'appliquent. Une variante « Momentum, Kelly plein, sans garde-fous » montre ce que les règles de survie changent.
4. **Export** (`pmbt/backtest.py`) : tables en schéma en étoile pour Power BI dans `data/powerbi/`, et un résumé `data/summary.json` pour le portfolio.

### Hypothèses à connaître

| Hypothèse | Valeur | Pourquoi |
|---|---|---|
| Moment de la décision | 24 h avant la clôture | Une décision par marché, prise sur le prix de ce moment-là |
| Durée minimale d'un marché | 2,5 jours | Les marchés de quelques minutes (« Bitcoin monte ou baisse entre 10 h et 10 h 15 ») n'ont pas de prix la veille |
| Apprentissage / test | 2025 / 2026 | La calibration est apprise sur 2025 et jouée sur 2026, sans information du futur |
| Glissement | +1 point sur le prix payé | L'historique donne le dernier prix, pas l'écart achat/vente |
| Mise minimale | 1 $ | Sous ce montant, un ordre n'est pas réaliste |
| Liquidité | volume total ≥ 5 000 $ | La liquidité à l'instant T n'est pas disponible dans l'historique |
| Sortie | à la résolution | L'article sort parfois avant ; c'est une simplification |

## Résultats

Données extraites le 4 novembre 2026 : 9 986 marchés avec un prix la veille de leur clôture, dont 7 498 en 2025 (apprentissage) et 2 488 en 2026 (test).

| Stratégie (2026, règles de l'article) | Paris | Réussite | Plus haut | Cagnotte finale |
|---|---|---|---|---|
| Calibration | 0 | – | 50 $ | 50,00 $ |
| Momentum | 132 | 67,4 % | 72,88 $ | 43,62 $ (arrêt le 4 mars) |
| Momentum, Kelly plein sans garde-fous | 97 | 67,0 % | 78,25 $ | 0,23 $ |
| Aléatoire (médiane de 300 tirages) | 28 | 35,7 % | 51,41 $ | 26,54 $ |

Ce qu'on en retient :

- **Le marché est bien calibré.** Sur 2025, aucune tranche de prix ne s'écarte de la fréquence réelle de plus de 4 points. Une correction statistique n'atteint jamais le seuil de 8 points de l'article : la stratégie Calibration ne parie pas une seule fois.
- **Gagner souvent ne veut pas dire gagner.** Momentum gagne 2 paris sur 3, mais surtout sur des favoris qui rapportent peu ; quelques pertes suffisent à déclencher l'arrêt à −40 %.
- **Les garde-fous limitent la casse, pas plus.** Avec la même estimation mais sans plafond ni arrêt, la cagnotte tombe à 0,23 $.
- **Le hasard ne gagne jamais ici.** Sur 300 tirages, aucun ne finit au-dessus de 50 $ (meilleur : 45,94 $). Le glissement d'un point et l'arrêt à −40 % suffisent à rendre l'espérance négative. Le meilleur tirage a pourtant touché 72,14 $ en cours de route : une capture d'écran prise au bon moment raconte une tout autre histoire.
- **Le pivot vers la météo ne trouve pas d'or.** Sur 2026, la tranche de prix la plus mal calibrée en météo ne s'écarte que de 4,2 points.

Ces résultats ne prouvent pas qu'aucune IA ne peut battre le marché. Ils montrent que les règles de mise de l'article ne créent pas d'avantage à elles seules, et qu'un avantage de 8 points est rare sur des marchés aussi bien calibrés.

## Lancer le projet

```bash
pip install -r requirements.txt
python -m pytest -q            # tests des règles de mise et des estimateurs
python run_pipeline.py all     # collecte (≈ 40 min) puis backtest
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
