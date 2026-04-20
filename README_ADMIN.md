# Guide de Déploiement & Administration - Agent Local Raguia

Ce document fournit les procédures de déploiement de l'agent local Raguia chez un client.

## 1. Installation Automatisée (Autonome)

Vous n'avez **plus besoin d'installer Python ou d'autres outils manuellement**. Les scripts d'installation se chargent de tout télécharger de manière autonome.

### macOS / Linux
Ouvrez le terminal dans le dossier `raguia_local_agent` et exécutez la commande avec vos identifiants :
```bash
./install.sh "https://raguia.client-domaine.com" "VOTRE_JETON_SAAS" "/chemin/vers/dossier/cible"
```

### Windows
Ouvrez PowerShell ou l'Invite de commandes dans le dossier `raguia_local_agent` et exécutez :
```powershell
.\install.bat "https://raguia.client-domaine.com" "VOTRE_JETON_SAAS" "C:\chemin\vers\dossier\cible"
```

*L'installation va créer un dossier caché `.raguia_agent` contenant la configuration et les commandes de contrôle de l'agent.*

## 2. Commandes de Contrôle (Scripts Générés)

Une fois l'installation terminée, vous trouverez trois scripts générés dans le dossier `.raguia_agent` :

- `./start.sh` (ou `start.bat`) : **Lancer l'agent**. Il démarre la surveillance active du dossier en arrière-plan et affiche l'icône dans la barre des tâches (système tray). C'est ce script qui doit être configuré au démarrage de la machine.
- `./test.sh` (ou `test.bat`) : **Tester la connexion**. Utile pour diagnostiquer si l'agent arrive à contacter l'API (erreurs réseau ou jeton expiré) sans lancer le moteur de synchronisation.
- `./stop.sh` (ou `stop.bat`) : **Arrêter l'agent**. Tue proprement le processus Python en cours de l'agent.

## 3. Configuration au Démarrage (Obligatoire)

Pour que l'agent se lance automatiquement au redémarrage du serveur ou du poste client :

- **Windows** : Touche Win + R -> `shell:startup`. Créez un raccourci pointant vers `.raguia_agent\start.bat`.
- **macOS** : Créez un `.plist` dans `~/Library/LaunchAgents/` exécutant le `.raguia_agent/start.sh`.
- **Linux** : Créez un service `systemd` exécutant le `.raguia_agent/start.sh`.

## 4. Dépannage Administrateur

- **Erreurs 401/403** : Vérifier le jeton API et l'exactitude de l'URL (`api_url`). Testez avec `./test.sh`.
- **Fichiers ignorés** : L'agent ignore volontairement les fichiers temporaires (`~$*.docx`, `.tmp`).
- **Logs** : Situés par défaut dans un fichier `.raguia_agent/raguia_agent.log` ou le dossier `.raguia/` de l'utilisateur.
