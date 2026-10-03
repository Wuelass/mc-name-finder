# MC Name Finder

**Trouve un pseudo Minecraft Java à partir de mots anglais et français.**

[English](../README.md) · [Référence CLI](usage.md) · [Configuration du token](authentication.md)

Le projet génère des candidats de **2 à 6 lettres**, enlève les accents (`été → ete`, `cœur → coeur`), vérifie les profils Minecraft existants, puis permet de confirmer une sélection avec ton token Minecraft Services.

> **« Aucun profil trouvé » ne veut pas dire « disponible ».** Un pseudo peut encore être réservé ou interdit. Seul le statut `AVAILABLE`, obtenu par une vérification authentifiée, confirme sa disponibilité à l'heure du test. Ce résultat ne réserve pas le pseudo.

## Installation sous Windows

Python **3.10 ou plus récent** est nécessaire. Dans PowerShell :

```powershell
git clone https://github.com/Wuelass/mc-name-finder.git
cd mc-name-finder
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
Copy-Item .env.example .env
```

Commence par un petit scan de mots assez courants :

```powershell
.\.venv\Scripts\mc-name-finder.exe scan --min-length 3 --max-length 6 --min-frequency 3 --limit 500
```

Aucune activation PowerShell ni modification de sa politique d'exécution n'est nécessaire.

## Installation sous Linux / macOS

```bash
git clone https://github.com/Wuelass/mc-name-finder.git
cd mc-name-finder
python3 -m venv .venv
.venv/bin/python -m pip install -e .
cp .env.example .env
chmod 600 .env
.venv/bin/mc-name-finder scan --min-length 3 --max-length 6 --min-frequency 3 --limit 500
```

Sous Debian/Ubuntu, le paquet `python3-venv` peut être nécessaire.

## Scanner les mots

Les exemples suivants supposent l'environnement virtuel activé. Sinon, utilise le chemin de l'exécutable indiqué ci-dessus.

```bash
# Tous les candidats des corpus anglais/français de 2 à 6 lettres
mc-name-finder scan

# Mots français de 4 lettres uniquement
mc-name-finder scan --languages fr --min-length 4 --max-length 4 --output results/francais

# Aperçu hors ligne : aucune requête Minecraft
mc-name-finder scan --dry-run --limit 100 --output results/apercu

# Continuer un scan interrompu, en conservant les observations déjà faites
mc-name-finder scan --resume

# Refaire toutes les vérifications avec un nouveau scan
mc-name-finder scan --overwrite

# Utiliser ton propre dictionnaire UTF-8, un mot par ligne
mc-name-finder scan --words examples/words.txt --output results/personnel
```

Les mots de **2 lettres** sont listés comme `IMPOSSIBLE_LENGTH` : ils ne peuvent pas devenir de nouveaux pseudos Java. Le scan complet peut être long. `--limit` et `--min-frequency` réduisent la sélection.

Les listes intégrées viennent de **wordfreq**, un corpus de fréquences. Elles ne représentent pas tous les mots d'un dictionnaire et peuvent inclure abréviations, noms propres ou conjugaisons. Pour une liste strictement choisie, utilise `--words`. Les chiffres, espaces, tirets, apostrophes et underscores sont exclus.

## Mettre ton token dans .env

Ouvre le fichier `.env` local et remplis uniquement :

```dotenv
MC_ACCESS_TOKEN=ton_token_minecraft_services
```

Ce n'est **pas** ton mot de passe Microsoft. Il faut un token d'accès **Minecraft Services**, sans le préfixe `Bearer `. Le projet ne gère pas la connexion Microsoft ni le renouvellement du token. Les jetons expirent : remplace le tien s'il est refusé. Consulte la [documentation d'authentification](authentication.md).

Le scan public fonctionne sans token. `.env` est exclu de Git ; `.env.example`, vide, est le seul modèle publié.

```bash
# Confirmer les 20 meilleurs candidats sans refaire le scan public
mc-name-finder confirm --top 20

# Confirmer des pseudos présents dans ton rapport
mc-name-finder confirm --names example another

# Rafraîchir une ancienne confirmation
mc-name-finder confirm --names example --refresh
```

Les noms ci-dessus sont des exemples de commande, pas des pseudos annoncés disponibles. Le programme ne change pas ton pseudo et ne récupère aucun nom automatiquement.

## Comprendre les résultats

| Statut | Signification |
|---|---|
| `UNKNOWN` | Pas encore vérifié par l'API publique |
| `IMPOSSIBLE_LENGTH` | Deux lettres : exclu des vérifications de disponibilité |
| `TAKEN` | Un profil utilise actuellement ce nom |
| `UNREGISTERED` | Aucun profil actuel détecté ; peut encore être réservé ou interdit |
| `NOT_CHECKED` | Pas de confirmation authentifiée |
| `AVAILABLE` | Disponibilité confirmée à l'instant de la vérification |
| `DUPLICATE` | L'API authentifiée indique que le nom n'est pas disponible |
| `NOT_ALLOWED` | L'API authentifiée refuse ce nom |

Dans `results/`, tu trouveras `results.csv`, `results.json`, `NOTICE.txt`, et des listes `unregistered_N_letters.txt` / `available_exact_N_letters.txt` par longueur. Le CSV s'ouvre dans un tableur et conserve les mots d'origine.

Chaque vérification possède sa propre date UTC (`lookup_checked_at_utc`, `exact_checked_at_utc`). La date d'export est différente. Une reprise conserve les anciennes dates : pour une information fraîche, relance un scan ou une confirmation avec `--refresh`. Les listes texte doivent rester accompagnées du rapport et de sa notice.

## Fiabilité et développement

Les requêtes publiques sont espacées d'au moins 1 seconde ; les confirmations d'au moins 16 secondes. Ces valeurs sont conservatrices et ne garantissent aucun quota. Le programme respecte `Retry-After`, limite les tentatives, sauvegarde les résultats à l'arrêt et ne transforme jamais une erreur API en disponibilité.

Le scan écrit un checkpoint tous les 10 lots réussis ; la confirmation après chaque nom. Ctrl+C sauvegarde le travail terminé. Une coupure brutale peut perdre les derniers lots. Utilise un seul processus par dossier de sortie et évite plusieurs confirmations parallèles sur le même compte.

Les tests et la CI vérifient le comportement sans utiliser de vrai token. Le code est sous licence MIT ; les données wordfreq gardent leurs propres conditions. Voir [les attributions](../THIRD_PARTY_NOTICES.md).
