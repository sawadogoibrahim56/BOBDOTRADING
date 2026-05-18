# 🚀 Bobdo Trading and Finance (BTF)
> **L'argent simple, sécurisé et intelligent pour le Burkina et l'Afrique de l'Ouest.**

![Version](https://img.shields.io/badge/version-1.3.0-blue)
![Stack](https://img.shields.io/badge/stack-FastAPI%20%7C%20PostgreSQL%20%7C%20HTML5-green)
![License](https://img.shields.io/badge/license-Proprietary-red)

---

## 📋 Vue d'ensemble

BTF est un **Hedge & Trade Operating System** intelligent, autonome et sécurisé pour les marchés financiers africains.

| Feature | Détail |
|---------|--------|
| **Modèle** | SaaS – 7j essai gratuit → 5 000 F CFA/mois |
| **Marchés** | Crypto (Binance, OKX, Bybit, Kraken, KuCoin, Gate.io, Coinbase) + BRVM |
| **IA Autonome** | Analyse technique + NLP + Marché Physique → Exécution automatique |
| **Zone couverte** | UEMOA complète (8 pays) |
| **Capacité** | Jusqu'à 500 000 utilisateurs simultanés |
| **Sécurité** | JWT + TOTP 2FA + AES-256 + Rate Limiting + Audit immuable |

---

## 🏗️ Architecture

```
btf/
├── backend/                    # Python FastAPI
│   ├── main.py                 # Point d'entrée
│   ├── models/
│   │   └── models.py           # Modèles SQLAlchemy (12 tables)
│   ├── routers/
│   │   ├── auth.py             # JWT + TOTP 2FA + Brute-force protection
│   │   ├── trading.py          # Ordres, Mode Autonome, Portefeuille
│   │   ├── markets.py          # OHLCV, Tickers, Signaux IA
│   │   ├── physical_market.py  # Marché Physique UEMOA
│   │   ├── payments.py         # Orange Money, Wave, Moov Money
│   │   ├── risk.py             # Gardien du Risque
│   │   ├── users.py            # Profil, Clés API chiffrées
│   │   ├── admin.py            # Panneau Admin ultra-sécurisé
│   │   └── websocket_feed.py   # WebSocket tick-by-tick
│   ├── services/
│   │   ├── autonomous_trader.py # Cerveau IA principal
│   │   ├── technical_analysis.py# EMA, RSI, MACD, Bollinger, ATR
│   │   ├── nlp_sentiment.py    # Analyse sentiment + dictionnaire UEMOA
│   │   ├── risk_manager.py     # Gardien du risque + arrêt d'urgence
│   │   ├── physical_scanner.py # Scanner marché physique UEMOA
│   │   ├── market_scanner.py   # Scanner OHLCV via CCXT
│   │   └── exchange_connector.py# Connexion exchanges chiffrée
│   ├── middleware/
│   │   ├── security.py         # Headers sécurité + Rate Limiting
│   │   └── logging.py          # Audit logging
│   └── utils/
│       ├── database.py         # Connexion Supabase/PostgreSQL async
│       ├── scheduler.py        # Tâches périodiques (APScheduler)
│       ├── logger.py           # Journal d'audit immuable
│       └── notifications.py   # Email + SMS (SMTP + Twilio)
├── frontend/
│   ├── assets/
│   │   ├── css/btf.css         # Design System global
│   │   └── js/btf-api.js       # Client API centralisé + WebSocket
│   └── pages/
│       ├── login.html          # Connexion + TOTP 2FA
│       ├── register.html       # Inscription + essai 7j
│       ├── dashboard.html      # Dashboard principal
│       ├── markets.html        # Trading + Carnet d'ordres
│       ├── physical.html       # Marché Physique UEMOA
│       ├── settings.html       # Clés API + Risk + Sécurité
│       ├── payment.html        # Orange Money / Wave / Moov
│       └── admin.html          # Panneau Admin (URL secrète)
├── sql/
│   └── schema.sql              # Schéma PostgreSQL complet (RLS Supabase)
├── docker/
│   ├── Dockerfile.api          # Image Docker API
│   └── nginx.conf              # Reverse proxy + SSL + Rate limiting
├── docker-compose.yml          # Orchestration complète
├── requirements.txt            # Dépendances Python
└── .env.example                # Template variables d'environnement
```

---

## ⚡ Installation Rapide

### Pré-requis
- Python 3.12+
- PostgreSQL 15+ (ou compte Supabase)
- Docker & Docker Compose (recommandé)

### 1. Cloner et configurer

```bash
git clone https://github.com/btf/bobdo-trading-finance.git
cd btf

# Copier et remplir les variables d'environnement
cp .env.example .env
nano .env   # ← Remplir TOUTES les variables
```

### 2. Base de données

```bash
# Sur Supabase : créer un projet et exécuter
psql $DATABASE_URL < sql/schema.sql

# Ou avec Docker PostgreSQL local
docker run -d --name btf-db \
  -e POSTGRES_DB=btf_db \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=YOUR_PASSWORD \
  -p 5432:5432 postgres:15
psql postgresql://postgres:YOUR_PASSWORD@localhost:5432/btf_db < sql/schema.sql
```

### 3. Lancement avec Docker (recommandé)

```bash
docker-compose up -d
# L'application est disponible sur https://votre-domaine.bf
```

### 4. Lancement en développement

```bash
# Backend
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000

# Frontend : ouvrir frontend/pages/login.html dans un navigateur
# ou servir avec :
python -m http.server 3000 --directory frontend
```

---

## 🔐 Sécurité – Points Critiques

### Clés API Utilisateurs
- Chiffrées **AES-256 (Fernet)** avant stockage
- Jamais affichées en clair
- Droits limités : **Lecture + Trading uniquement** (JAMAIS de retrait)

### Numéros de Paiement
- Stockés **uniquement dans `.env`** – jamais en base de données
- Endpoint `/api/v1/payments/info` les retourne dynamiquement depuis l'environnement

### Panneau Admin (`/admin-secret-gate`)
- **Triple authentification** : Password + TOTP + PIN
- Restriction IP configurable via `ADMIN_ALLOWED_IPS`
- Notifications immédiates email+SMS sur chaque connexion
- Sessions de 4h maximum
- Journalisation immuable de toutes les actions

### Rate Limiting
- 200 requêtes/minute par IP (API générale)
- 10 requêtes/minute par IP (endpoints auth)

### JWT
- Access token : 60 minutes
- Refresh token : 30 jours
- Rotation automatique

---

## 🤖 Module IA Autonome

Le trader autonome tourne en boucle toutes les 60 secondes :

```
1. Fetch OHLCV via CCXT (WebSocket tick-by-tick)
2. Analyse Technique  → score [-1, +1]  (EMA, RSI, MACD, BB, ATR, Volume)
3. Analyse Sentiment NLP → score [-1, +1] (dictionnaire UEMOA francophone)
4. Score Combiné : 40% Tech + 30% NLP + 30% Fondamental
5. Confiance ≥ 65% → Générer signal (buy/sell)
6. Gardien du Risque → Validation / VETO
7. Exécution → tous utilisateurs avec mode autonome activé
8. Notification → Email + SMS + WebSocket temps réel
```

---

## 🛡️ Gardien du Risque (Module D)

| Règle | Valeur |
|-------|--------|
| Risque max par trade | **1% du capital** |
| Stop-Loss | **Obligatoire** sur chaque ordre |
| Drawdown quotidien | **Arrêt automatique à 2%** |
| Durée arrêt d'urgence | **24 heures** |
| Droit de veto | **Absolu** – même sur les ordres IA |

---

## 🌾 Marché Physique UEMOA (Module B)

Scanner actif sur **8 pays**, **15+ produits**, **5 axes logistiques** :

- 🚛 Abidjan → Ouagadougou (poisson, produits frais)
- 🌾 Hub Bobo-Dioulasso (maïs, sorgho, mil, riz)
- 🚢 Lomé → Ouagadougou
- 🐟 Dakar → Bamako
- 🐄 Sahel → Ouaga (bétail)

**Indice de Rareté** calculé dynamiquement (0-10) :
- 🔴 ≥ 7.5 : Critique
- 🟡 ≥ 5.0 : Élevé
- 🟠 ≥ 2.5 : Modéré
- 🟢 < 2.5 : Faible

---

## 💳 Paiement Mobile Money

| Méthode | Configuration |
|---------|---------------|
| Orange Money | `ORANGE_MONEY_NUMBER` dans `.env` |
| Wave | `WAVE_NUMBER` dans `.env` |
| Moov Money | `MOOV_MONEY_NUMBER` dans `.env` |

Workflow :
1. Utilisateur envoie le virement + soumet preuve
2. Admin reçoit notification immédiate
3. Admin valide dans le panneau (`/admin-secret-gate`)
4. Abonnement activé automatiquement + notification utilisateur

---

## 📊 Scalabilité

| Composant | Configuration |
|-----------|---------------|
| API Workers | 4 workers Uvicorn (uvloop + httptools) |
| DB Pool | NullPool (Supabase gère son pool) |
| WebSocket | Connection Manager centralisé |
| Cache | À ajouter : Redis pour 500K users |

Pour supporter **500 000 utilisateurs simultanés** en production :
```yaml
# docker-compose.yml – ajouter Redis
redis:
  image: redis:7-alpine
  command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru

# Augmenter les workers
CMD ["uvicorn", "backend.main:app", "--workers", "16", ...]
```

---

## 🚀 URLs Importantes

| URL | Description |
|-----|-------------|
| `https://btf.bf` | Application principale |
| `https://btf.bf/pages/login.html` | Connexion |
| `https://btf.bf/pages/dashboard.html` | Dashboard |
| `https://btf.bf/pages/markets.html` | Trading |
| `https://btf.bf/pages/physical.html` | Marché Physique |
| `https://btf.bf/pages/payment.html` | Paiement |
| `https://btf.bf/admin-secret-gate/login` | **Admin (SECRET)** |
| `https://btf.bf/health` | Health check |

---

## 📞 Support

**BTF – Bobdo Trading and Finance**
- Email : support@btf.bf
- Admin : admin@btf.bf

---

*© 2026 Bobdo Trading and Finance. Tous droits réservés.*
*Le trading comporte des risques. Les résultats passés ne garantissent pas les résultats futurs.*
