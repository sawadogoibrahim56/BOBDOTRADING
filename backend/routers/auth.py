"""
BTF – Authentification : JWT + TOTP 2FA + Blocage brute-force
"""

import os
import secrets
from datetime import datetime, timedelta, timezone

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.models import User, UserStatus, RiskProfile, Portfolio, TradingMode
from backend.utils.database import get_db
from backend.utils.logger import log_action
from backend.utils.notifications import send_login_alert

router = APIRouter()

# ─── CONFIG ───────────────────────────────────────────────────────────────────
SECRET_KEY      = os.getenv("JWT_SECRET_KEY", secrets.token_hex(64))
ALGORITHM       = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES  = 60
REFRESH_TOKEN_EXPIRE_DAYS    = 30
MAX_LOGIN_ATTEMPTS           = 5
LOCKOUT_MINUTES              = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ─── SCHEMAS ──────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    phone: str | None = None
    password: str
    country: str = "BF"

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    requires_totp: bool = False
    user_id: str

class TOTPVerifyRequest(BaseModel):
    user_id: str
    totp_code: str

class TOTPSetupResponse(BaseModel):
    secret: str
    qr_uri: str

class RefreshRequest(BaseModel):
    refresh_token: str


# ─── HELPERS ──────────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_token(data: dict, expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def create_access_token(user_id: str) -> str:
    return create_token({"sub": user_id, "type": "access"}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

def create_refresh_token(user_id: str) -> str:
    return create_token({"sub": user_id, "type": "refresh"}, timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalide ou expiré",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if not user_id or payload.get("type") != "access":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise credentials_exception
    return user


async def require_active_subscription(user: User = Depends(get_current_user)) -> User:
    now = datetime.now(timezone.utc)
    if user.status == UserStatus.TRIAL:
        if user.trial_ends_at and user.trial_ends_at < now:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Essai expiré. Souscrivez pour 5 000 F CFA/mois.",
            )
    elif user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Abonnement inactif. Veuillez renouveler.",
        )
    return user


# ─── ROUTES ───────────────────────────────────────────────────────────────────
@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    # Vérifier email unique
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email déjà utilisé.")

    user = User(
        full_name       = data.full_name,
        email           = data.email,
        phone           = data.phone,
        hashed_password = hash_password(data.password),
        country         = data.country,
        status          = UserStatus.TRIAL,
        trial_ends_at   = datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(user)
    await db.flush()

    # Créer portefeuille demo
    portfolio = Portfolio(user_id=user.id, mode=TradingMode.DEMO, demo_balance_fcfa=2_450_000)
    db.add(portfolio)

    # Créer profil de risque par défaut
    risk = RiskProfile(user_id=user.id)
    db.add(risk)

    await db.commit()
    await log_action(db, user.id, "REGISTER", "auth", request.client.host)
    return {"message": "Compte créé. Essai 7 jours activé.", "user_id": str(user.id)}


@router.post("/login")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    # Vérifier blocage
    now = datetime.now(timezone.utc)
    if user and user.locked_until and user.locked_until > now:
        raise HTTPException(status_code=423, detail=f"Compte bloqué jusqu'à {user.locked_until.isoformat()}")

    if not user or not verify_password(form_data.password, user.hashed_password):
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
                user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            await db.commit()
        await log_action(db, None, "LOGIN_FAILED", "auth", request.client.host, severity="warning")
        raise HTTPException(status_code=401, detail="Identifiants incorrects.")

    # Réinitialiser tentatives
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    user.last_login_ip = request.client.host
    await db.commit()

    if user.totp_enabled:
        # Retourner un token temporaire – nécessite validation TOTP
        temp_token = create_token({"sub": str(user.id), "type": "pre_totp"}, timedelta(minutes=5))
        await log_action(db, user.id, "LOGIN_NEEDS_TOTP", "auth", request.client.host)
        return {"requires_totp": True, "temp_token": temp_token, "user_id": str(user.id)}

    access = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))
    await log_action(db, user.id, "LOGIN_SUCCESS", "auth", request.client.host)
    await send_login_alert(user, request.client.host)

    return LoginResponse(
        access_token=access,
        refresh_token=refresh,
        requires_totp=False,
        user_id=str(user.id),
    )


@router.post("/totp/verify")
async def verify_totp(data: TOTPVerifyRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == data.user_id))
    user = result.scalar_one_or_none()
    if not user or not user.totp_secret:
        raise HTTPException(status_code=400, detail="TOTP non configuré.")

    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(data.totp_code, valid_window=1):
        raise HTTPException(status_code=401, detail="Code TOTP invalide.")

    access = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))
    return LoginResponse(access_token=access, refresh_token=refresh, user_id=str(user.id))


@router.post("/totp/setup")
async def setup_totp(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    secret = pyotp.random_base32()
    user.totp_secret = secret
    await db.commit()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=user.email, issuer_name="BTF")
    return TOTPSetupResponse(secret=secret, qr_uri=uri)


@router.post("/totp/enable")
async def enable_totp(code: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="Configurez le TOTP d'abord.")
    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(code, valid_window=1):
        raise HTTPException(status_code=401, detail="Code TOTP invalide.")
    user.totp_enabled = True
    await db.commit()
    return {"message": "2FA activé avec succès."}


@router.post("/refresh")
async def refresh_token(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(data.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise ValueError()
        user_id = payload["sub"]
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Refresh token invalide.")
    new_access = create_access_token(user_id)
    return {"access_token": new_access, "token_type": "bearer"}


@router.post("/logout")
async def logout(request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await log_action(db, user.id, "LOGOUT", "auth", request.client.host)
    return {"message": "Déconnexion réussie."}
