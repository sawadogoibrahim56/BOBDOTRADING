#!/usr/bin/env python3
"""
BTF – Script de configuration automatique
Lance : python setup.py
"""
import os
import sys
import secrets
import subprocess

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def section(title):
    print(f"\n{'='*55}")
    print(f"  {title}")
    print(f"{'='*55}")

def main():
    print("\n🚀 BTF – Bobdo Trading and Finance – Setup")
    print("   L'argent simple, sécurisé et intelligent\n")

    # ── 1. Vérifier Python ──────────────────────────────────────────
    section("1. Vérification Python")
    ver = sys.version_info
    if ver.major < 3 or ver.minor < 11:
        print(f"❌ Python 3.11+ requis. Vous avez {ver.major}.{ver.minor}")
        sys.exit(1)
    print(f"✅ Python {ver.major}.{ver.minor}.{ver.micro}")

    # ── 2. Installer les dépendances ────────────────────────────────
    section("2. Installation des dépendances")
    print("⏳ pip install -r requirements.txt ...")
    result = run("pip install -r requirements.txt -q")
    if result.returncode != 0:
        print(f"❌ Erreur: {result.stderr[:300]}")
        sys.exit(1)
    print("✅ Dépendances installées")

    # ── 3. Générer les clés de sécurité ─────────────────────────────
    section("3. Génération des clés de sécurité")
    jwt_key = secrets.token_hex(64)
    print(f"✅ JWT_SECRET_KEY générée ({len(jwt_key)} chars)")

    try:
        from cryptography.fernet import Fernet
        fernet_key = Fernet.generate_key().decode()
        print(f"✅ ENCRYPTION_KEY (Fernet) générée")
    except ImportError:
        fernet_key = "INSTALLER_cryptography_DABORD"
        print("⚠️  cryptography non installé – relancez après pip install")

    # ── 4. Créer .env depuis .env.example ──────────────────────────
    section("4. Configuration .env")
    if os.path.exists(".env"):
        print("⚠️  .env existe déjà – skipped (supprimez-le pour reconfigurer)")
    else:
        with open(".env.example", "r") as f:
            content = f.read()
        content = content.replace("MINIMUM_64_CARACTERES_ALEATOIRES", jwt_key)
        content = content.replace("CLE_FERNET_BASE64", fernet_key)
        with open(".env", "w") as f:
            f.write(content)
        print("✅ .env créé depuis .env.example")
        print("⚡ IMPORTANT : Éditez .env et remplissez DATABASE_URL, SUPABASE_*, ORANGE_MONEY_NUMBER, etc.")

    # ── 5. Initialiser la base de données ──────────────────────────
    section("5. Base de données")
    print("Pour initialiser la base de données, exécutez :")
    print("  psql $DATABASE_URL < sql/schema.sql")
    print("  OU collez le contenu de sql/schema.sql dans l'éditeur SQL de Supabase")

    # ── 6. Instructions de lancement ───────────────────────────────
    section("6. Lancement")
    print("""
Développement local :
  uvicorn backend.main:app --reload --port 8000

Render.com :
  1. Pusher le code sur GitHub
  2. New Web Service > connecter votre repo
  3. Build Command : pip install -r requirements.txt
  4. Start Command : uvicorn backend.main:app --host 0.0.0.0 --port $PORT
  5. Ajouter les variables d'environnement depuis .env
  6. Deploy !

Frontend (Netlify/Vercel/Render Static) :
  1. Déployer le dossier frontend/
  2. Mettre à jour API_BASE dans frontend/assets/js/btf-api.js
     avec l'URL de votre API Render

Supabase :
  1. Créer un projet sur supabase.com
  2. SQL Editor > Coller sql/schema.sql > Run
  3. Copier DATABASE_URL depuis Settings > Database
""")

    print("✅ Setup BTF terminé !")
    print("   Éditez .env puis lancez : uvicorn backend.main:app --reload\n")

if __name__ == "__main__":
    main()
