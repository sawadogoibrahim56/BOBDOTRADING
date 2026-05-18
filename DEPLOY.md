# 🚀 BTF – Guide de Déploiement Complet

## Méthode Recommandée : Render (Backend) + Netlify (Frontend) + Supabase (BDD)

**Tout est GRATUIT au démarrage.** Passer aux plans payants quand votre base d'utilisateurs grandit.

---

## ÉTAPE 1 — Supabase (Base de données PostgreSQL)

### 1.1 Créer un projet
1. Aller sur **https://supabase.com** → Sign Up (gratuit)
2. Cliquer **New Project**
3. Nom : `btf-production`
4. Mot de passe DB : générer un mot de passe fort → **le sauvegarder !**
5. Région : **West EU (Ireland)** ou la plus proche de vos utilisateurs
6. Cliquer **Create new project** → attendre 2 minutes

### 1.2 Initialiser la base de données
1. Dans Supabase → **SQL Editor** → **New Query**
2. Copier-coller tout le contenu de `sql/schema.sql`
3. Cliquer **Run** → vérifier qu'il n'y a pas d'erreur
4. ✅ Vos 12 tables sont créées avec RLS activé

### 1.3 Récupérer les informations de connexion
1. **Settings** → **Database** → copier **Connection String** (mode : URI)
   - Format : `postgresql://postgres:[PASSWORD]@db.[REF].supabase.co:5432/postgres`
   - Pour Python async, remplacer `postgresql://` par `postgresql+asyncpg://`
2. **Settings** → **API** → copier :
   - `Project URL` → c'est votre `SUPABASE_URL`
   - `anon public` key → `SUPABASE_ANON_KEY`
   - `service_role` key → `SUPABASE_SERVICE_KEY`

---

## ÉTAPE 2 — Render (Backend FastAPI)

### 2.1 Préparer GitHub
1. Créer un repo GitHub : `btf-backend`
2. Pusher votre code :
```bash
git init
git add .
git commit -m "BTF v1.3 initial"
git remote add origin https://github.com/VOTRE_USER/btf-backend.git
git push -u origin main
```

### 2.2 Créer le service sur Render
1. Aller sur **https://render.com** → Sign Up
2. **New +** → **Web Service**
3. Connecter votre repo GitHub `btf-backend`
4. Configuration :
   - **Name** : `btf-api`
   - **Region** : Frankfurt (plus proche Afrique)
   - **Branch** : `main`
   - **Runtime** : Python 3
   - **Build Command** : `pip install -r requirements.txt`
   - **Start Command** : `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - **Plan** : Free (ou Starter $7/mois pour éviter le sleep)

### 2.3 Variables d'environnement sur Render
Aller dans **Environment** → ajouter chaque variable :

| Variable | Valeur |
|----------|--------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:MOT_DE_PASSE@db.XXXX.supabase.co:5432/postgres` |
| `JWT_SECRET_KEY` | Générer avec : `python -c "import secrets; print(secrets.token_hex(64))"` |
| `ENCRYPTION_KEY` | Générer avec : `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `SUPABASE_URL` | `https://XXXX.supabase.co` |
| `SUPABASE_SERVICE_KEY` | `eyJ...` (service_role key) |
| `ORANGE_MONEY_NUMBER` | `+22670000000` |
| `WAVE_NUMBER` | `+22670000001` |
| `MOOV_MONEY_NUMBER` | `+22670000002` |
| `ADMIN_PIN_CODE` | Un code à 6 chiffres secret |
| `ADMIN_ALERT_EMAIL` | Votre email admin |
| `ADMIN_ALLOWED_IPS` | `0.0.0.0` (ou votre IP fixe) |
| `SMTP_HOST` | `smtp-relay.brevo.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | Votre email |
| `SMTP_PASSWORD` | Mot de passe SMTP |
| `FROM_EMAIL` | `noreply@btf.bf` |
| `ENVIRONMENT` | `production` |

5. Cliquer **Create Web Service** → attendre le déploiement (3-5 min)
6. Votre API est disponible sur : `https://btf-api.onrender.com`
7. Tester : `https://btf-api.onrender.com/health` → doit retourner `{"status":"ok"}`

---

## ÉTAPE 3 — Configurer l'URL API dans le Frontend

Ouvrir `frontend/assets/js/btf-config.js` et remplacer l'URL :

```javascript
// Remplacer par votre vraie URL Render :
window.BTF_API_URL = 'https://btf-api.onrender.com';
```

---

## ÉTAPE 4 — Netlify (Frontend Statique)

### 4.1 Option A : Drag & Drop (le plus simple)
1. Aller sur **https://netlify.com** → Sign Up
2. Aller sur **Sites** → glisser-déposer le dossier **`frontend/`**
3. Votre site est en ligne en 30 secondes !
4. Cliquer **Domain settings** pour mettre un nom de domaine

### 4.2 Option B : Via GitHub
1. **New site from Git** → connecter votre repo
2. **Base directory** : `frontend`
3. **Publish directory** : `frontend`
4. **Deploy site** !

### 4.3 Domaine personnalisé (optionnel)
- Acheter `btf.bf` chez un registrar burkinabè ou international
- Netlify : **Domain settings** → **Add custom domain** → suivre les instructions DNS

---

## ÉTAPE 5 — Render Static (Alternative tout-en-un)

Si vous voulez tout sur Render :

1. **New +** → **Static Site**
2. Connecter même repo
3. **Publish directory** : `frontend`
4. ✅ Frontend + Backend sur Render

---

## ÉTAPE 6 — Activer le compte Admin

Après déploiement :

1. Aller sur `https://VOTRE-SITE/pages/admin.html`
2. Dans Supabase SQL Editor, mettre à jour le mot de passe admin :
```sql
UPDATE users
SET hashed_password = crypt('VOTRE_MOT_DE_PASSE', gen_salt('bf'))
WHERE email = 'admin@btf.bf';

-- Activer TOTP pour l'admin (OBLIGATOIRE)
-- Connexion → Settings → Sécurité → Activer 2FA
```
3. Activer le TOTP depuis l'interface Settings

---

## ÉTAPE 7 — Vérifications Post-Déploiement

```bash
# 1. Health check API
curl https://btf-api.onrender.com/health
# Réponse attendue : {"status":"ok","service":"BTF","version":"1.3.0"}

# 2. Test inscription
curl -X POST https://btf-api.onrender.com/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Test User","email":"test@test.com","password":"testpass123"}'
# Réponse attendue : {"message":"Compte créé. Essai 7 jours activé.","user_id":"..."}
```

---

## Résumé des URLs

| Service | URL |
|---------|-----|
| **Frontend** | `https://btf.netlify.app` (ou votre domaine) |
| **Backend API** | `https://btf-api.onrender.com` |
| **Admin** | `https://btf.netlify.app/pages/admin.html` |
| **Health** | `https://btf-api.onrender.com/health` |
| **Supabase** | `https://supabase.com/dashboard` |

---

## Coûts (démarrage)

| Service | Plan | Coût |
|---------|------|------|
| Supabase | Free | 0€ (500MB DB) |
| Render Backend | Free | 0€ (sleep après 15min inactivité) |
| Render Starter | Starter | $7/mois (pas de sleep) |
| Netlify | Free | 0€ (100GB bandwidth) |
| **TOTAL démarrage** | | **0 à $7/mois** |

---

## Support

Pour toute question : **admin@btf.bf**

*BTF – Bobdo Trading and Finance © 2026*
