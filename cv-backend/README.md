# CVBase — Plateforme de CV en ligne (Flask)

Site web en Python (Flask) permettant aux utilisateurs de :
- créer un compte et se connecter (mot de passe hashé) ;
- renseigner leurs informations professionnelles (résumé, expérience, formation, compétences...) ;
- téléverser leur CV (PDF, DOC, DOCX) ;
- obtenir un lien public partageable vers leur profil.

## Installation

```bash
# 1. Créer un environnement virtuel (recommandé)
python -m venv venv
source venv/bin/activate   # sous Windows : venv\Scripts\activate

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Configurer les variables d'environnement optionnelles
copy ..\.env.example .env   # ou créez votre propre fichier .env sur Windows

# 4. Lancer l'application
python app.py
```

L'application est ensuite accessible sur : http://127.0.0.1:5000

La base de données SQLite (`cv_site.db`) et le dossier `uploads/` sont créés automatiquement au premier lancement.

## Authentification OAuth et email réel

L'application supporte maintenant :
- Google OAuth si `GOOGLE_CLIENT_ID` et `GOOGLE_CLIENT_SECRET` sont définis ;
- Microsoft OAuth si `MICROSOFT_CLIENT_ID` et `MICROSOFT_CLIENT_SECRET` sont définis ;
- envoi d'email SMTP si `MAIL_SERVER`, `MAIL_USERNAME` et `MAIL_PASSWORD` sont configurés.

Si ces variables ne sont pas fournies, l'application reste fonctionnelle en mode prototype local avec une gestion de compte locale et des liens de vérification affichés dans l'interface.

### Exemple de variables d'environnement

```env
SECRET_KEY=change-me
DATABASE_URL=sqlite:///cv_site.db
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
MICROSOFT_CLIENT_ID=...
MICROSOFT_CLIENT_SECRET=...
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=votre-email@gmail.com
MAIL_PASSWORD=motdepasse-app
MAIL_USE_TLS=true
MAIL_DEFAULT_SENDER=noreply@example.com
```

## Structure du projet

```
cv-website/
├── app.py                 # Application Flask (routes, modèles, logique)
├── requirements.txt       # Dépendances Python
├── templates/              # Pages HTML (Jinja2)
│   ├── base.html
│   ├── index.html
│   ├── register.html
│   ├── login.html
│   ├── dashboard.html
│   ├── profile.html
│   ├── public_profile.html
│   └── 404.html
├── static/
│   └── style.css          # Style de l'interface
└── uploads/                # CV téléversés par les utilisateurs
```

## Fonctionnalités principales

| Route | Description |
|---|---|
| `/` | Accueil, liste des profils publics récents |
| `/register` | Création de compte |
| `/login` / `/logout` | Connexion / déconnexion |
| `/dashboard` | Tableau de bord de l'utilisateur connecté |
| `/profile` | Formulaire pour modifier ses informations et téléverser son CV |
| `/cv/<user_id>` | Page publique du profil (à partager) |
| `/uploads/<filename>` | Téléchargement du CV (réservé au propriétaire) |

## Points à adapter avant une mise en production

1. **Clé secrète** : remplacez `SECRET_KEY` dans `app.py` par une valeur aléatoire et gardée privée (variable d'environnement recommandée).
2. **Base de données** : SQLite convient pour un usage local/démo ; pour de la production, migrez vers PostgreSQL ou MySQL.
3. **HTTPS** : à déployer derrière un serveur (Nginx + Gunicorn, par exemple) avec certificat SSL.
4. **Validation** : ajoutez une validation plus poussée des emails et une confirmation d'inscription par email si besoin.
5. **Stockage des fichiers** : pour un vrai déploiement, envisagez un stockage externe (S3, etc.) plutôt que le disque local.

## Idées d'améliorations possibles

- Export du profil en PDF stylisé.
- Recherche et filtrage des profils publics par compétence.
- Plusieurs CV par utilisateur (versions différentes).
- Statistiques de vues sur le profil public.
