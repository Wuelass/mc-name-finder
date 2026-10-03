# Tutoriel : récupérer automatiquement un pseudo Minecraft

Ce guide utilise **Windows / PowerShell**. Pour Linux/macOS, les commandes équivalentes sont à la fin.

Le programme surveille un seul pseudo sur ton compte Java. Avec `--claim`, il tente de remplacer ton pseudo actuel dès que Minecraft répond `AVAILABLE`, puis vérifie le résultat et s’arrête. Il ne peut pas garantir de gagner face à quelqu’un qui tente le même nom.

## 1. Installer les prérequis et mettre le projet à jour

Il faut **Python 3.10+** et **Node.js 20+ avec npm**. Installe la version LTS de Node.js depuis [nodejs.org](https://nodejs.org/en/download), puis ferme et rouvre PowerShell. Node sert à la connexion Microsoft et au renouvellement de session.

Dans le dossier de ton dépôt existant :

```powershell
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install -e .
node --version
npm --version
```

Si tu n’as pas encore le projet ou l’environnement virtuel :

```powershell
git clone https://github.com/Wuelass/mc-name-finder.git
cd mc-name-finder
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

La mise à jour par `pip` est nécessaire pour installer la nouvelle dépendance de verrouillage, même si les sources étaient déjà installées en mode éditable.

## 2. Connecter ton compte Minecraft

```powershell
.\.venv\Scripts\mc-name-finder.exe login
```

Au premier lancement, l’app installe sa bibliothèque de connexion. Elle affiche ensuite **un lien Microsoft et un code**, puis tente d’ouvrir le navigateur.

1. Ouvre le lien affiché si le navigateur ne s’ouvre pas.
2. Entre le code de connexion affiché dans PowerShell.
3. Choisis le compte Microsoft qui possède ton Minecraft Java.
4. Termine la connexion et laisse PowerShell ouvert jusqu’au retour du résultat.

Microsoft peut afficher **« Minecraft for Nintendo Switch »** : c’est le client utilisé par la bibliothèque PrismarineJS pour ce flux. Tu n’as pas besoin d’une Switch. Vérifie que tu es sur une page Microsoft ; ton mot de passe se saisit uniquement chez Microsoft.

L’app doit ensuite afficher le vrai pseudo Java connecté. **Tu n’as aucun token à copier dans `.env` pour cette méthode.** La session est conservée localement hors du dépôt et renouvelée quand le service le permet.

## 3. Vérifier ton compte avant d’armer le changement

```powershell
.\.venv\Scripts\mc-name-finder.exe account
```

Vérifie le pseudo affiché et :

```text
Name change allowed: True
```

Si c’est `False`, le compte ne peut pas changer de nom pour le moment. Le mode automatique refusera de démarrer. Utilise le compte/licence prévu pour ce changement.

## 4. Choisir le pseudo et lancer la surveillance

Remplace `PSEUDO_CIBLE` par celui que tu veux prendre, et `TON_PSEUDO_ACTUEL` par le nom affiché à l’étape précédente :

```powershell
.\.venv\Scripts\mc-name-finder.exe watch PSEUDO_CIBLE --claim --expected-profile TON_PSEUDO_ACTUEL
```

**Cette commande autorise réellement le changement du pseudo du compte connecté.** Si le nom est déjà libre, la tentative peut partir dès le premier contrôle. Un nom cible peut contenir 3 à 16 lettres ASCII, chiffres ou underscores. Il n’a pas besoin d’apparaître dans les résultats d’un scan.

Pendant l’attente, tu verras des lignes de ce type :

```text
Account: TON_PSEUDO_ACTUEL · target: PSEUDO_CIBLE · automatic claim: ON
PSEUDO_CIBLE: DUPLICATE
PSEUDO_CIBLE: AVAILABLE
Attempting to change your name to PSEUDO_CIBLE…
SUCCESS: your Minecraft name is now PSEUDO_CIBLE.
```

Cet exemple illustre un scénario réussi ; il ne promet pas que le nom sera disponible ou que la tentative gagnera.

L’app espace les vérifications d’au moins 16 secondes et respecte les pauses demandées par le serveur. Après `AVAILABLE`, elle revérifie le compte et son éligibilité, tente le changement puis confirme le profil. Si `NOT_ALLOWED` apparaît, elle s’arrête : Minecraft refuse ce nom.

Pour observer sans changer ton compte :

```powershell
.\.venv\Scripts\mc-name-finder.exe watch PSEUDO_CIBLE
```

## 5. Démarrer près d’une heure estimée de libération

Tu peux préparer la commande à l’avance et commencer les contrôles un peu avant l’heure estimée. Exemple de début de surveillance le **15 octobre 2026 à 23 h 11 min 46 s, avec un décalage UTC+2**, pendant 10 minutes :

```powershell
.\.venv\Scripts\mc-name-finder.exe watch PSEUDO_CIBLE --claim --expected-profile TON_PSEUDO_ACTUEL --start-at "2026-10-15T23:11:46+02:00" --max-minutes 10
```

Remplace la date, l’heure et le décalage par tes valeurs. `+02:00` correspond à UTC+2 ; `+01:00` à UTC+1. Une heure sans décalage est refusée pour éviter les ambiguïtés. `--start-at` indique **quand commencer à vérifier**, pas un instant garanti de récupération. Les 10 minutes commencent après l’attente programmée.

Le programme authentifie le compte avant l’attente et renouvelle son token au besoin quand les contrôles commencent. Une demande de reconnexion Microsoft interactive arrête la surveillance : refais `login`, puis relance la commande.

## 6. Garder le programme actif et lire le résultat

Laisse **PowerShell ouvert, le PC allumé, connecté et sans veille** pendant la surveillance. Fermer la fenêtre, éteindre le PC ou interrompre le processus arrête les tentatives. Le logiciel ne crée pas de tâche Windows en arrière-plan.

- **Ctrl+C** : arrêter la surveillance.
- **SUCCESS** : le profil confirme le nouveau pseudo.
- **TIMED_OUT** : la durée prévue est terminée ; ce n’est pas une récupération réussie.
- **Changement refusé** : la tentative s’arrête, par exemple si le nom a été pris entre la vérification et le changement.
- **Résultat incertain / non vérifié** : le serveur a pu recevoir la modification sans que l’app puisse confirmer le résultat. Elle n’envoie pas une seconde modification à l’aveugle. Vérifie ton profil sur Minecraft.net puis lance `account` avant de relancer `watch`.

L’état le plus récent est enregistré dans `%LOCALAPPDATA%\MCNameFinder\accounts\default\watch.json`, sans token. Les fichiers du sous-dossier `tokens` contiennent la session : ne les partage pas. Les permissions Windows sont restreintes à ton utilisateur ; ces fichiers ne sont pas chiffrés.

## Plusieurs comptes

Connecte chaque compte sous un alias différent :

```powershell
.\.venv\Scripts\mc-name-finder.exe login --account secondaire
.\.venv\Scripts\mc-name-finder.exe account --account secondaire
.\.venv\Scripts\mc-name-finder.exe watch PSEUDO_CIBLE --account secondaire --claim --expected-profile PSEUDO_ACTUEL_DU_SECOND_COMPTE
```

Un alias est une étiquette locale, pas une adresse mail. Le logiciel verrouille chaque UUID pour éviter deux surveillances simultanées du même profil dans le même dossier de données. Évite également d’autres outils de changement/confirmation sur ce compte pendant l’attente.

## Linux / macOS

Avec Python et Node.js 20+ disponibles, dans le dépôt :

```bash
git pull --ff-only
.venv/bin/python -m pip install -e .
.venv/bin/mc-name-finder login --no-browser
.venv/bin/mc-name-finder account
.venv/bin/mc-name-finder watch PSEUDO_CIBLE --claim --expected-profile TON_PSEUDO_ACTUEL
```

Crée d’abord `.venv` avec `python3 -m venv .venv` si nécessaire. Le lien et le code Microsoft peuvent être ouverts sur ton PC pendant que le processus tourne sur ton serveur. Les sessions se trouvent par défaut dans `~/.config/mc-name-finder/` (ou sous `$XDG_CONFIG_HOME`). La surveillance ne se transforme pas automatiquement en service : garde le processus actif, par exemple dans une session `tmux`.

Pour supprimer la session locale : `mc-name-finder logout`. Pour les erreurs d’authentification, consulte [le guide de connexion](authentication.md).
