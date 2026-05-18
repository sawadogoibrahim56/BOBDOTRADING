"""BTF – Router Utilisateurs"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.models import User, UserApiKey, UserAlert, RiskProfile
from backend.routers.auth import get_current_user, hash_password
from backend.utils.database import get_db
from cryptography.fernet import Fernet
import os

router = APIRouter()
_fernet = Fernet(os.getenv("ENCRYPTION_KEY", Fernet.generate_key()))

class ProfileUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    country: str | None = None
    trading_mode: str | None = None

class ApiKeyCreate(BaseModel):
    exchange: str
    api_key: str
    api_secret: str
    passphrase: str | None = None
    label: str | None = None

@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    return {"id":str(user.id),"email":user.email,"full_name":user.full_name,
            "phone":user.phone,"country":user.country,"status":user.status,
            "trading_mode":user.trading_mode,"autonomous_enabled":user.autonomous_enabled,
            "totp_enabled":user.totp_enabled,"is_admin":user.is_admin,
            "trial_ends_at":user.trial_ends_at.isoformat() if user.trial_ends_at else None,
            "subscription_ends_at":user.subscription_ends_at.isoformat() if user.subscription_ends_at else None}

@router.put("/me")
async def update_me(data: ProfileUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if data.full_name: user.full_name = data.full_name
    if data.phone is not None: user.phone = data.phone
    if data.country: user.country = data.country
    if data.trading_mode: user.trading_mode = data.trading_mode
    await db.commit()
    return {"message": "Profil mis à jour."}

@router.post("/api-keys")
async def add_api_key(data: ApiKeyCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    enc_key    = _fernet.encrypt(data.api_key.encode()).decode()
    enc_secret = _fernet.encrypt(data.api_secret.encode()).decode()
    enc_pp     = _fernet.encrypt(data.passphrase.encode()).decode() if data.passphrase else None
    key = UserApiKey(user_id=user.id, exchange=data.exchange, label=data.label,
                     encrypted_api_key=enc_key, encrypted_api_secret=enc_secret, encrypted_passphrase=enc_pp)
    db.add(key)
    await db.commit()
    return {"message": f"Clé {data.exchange} ajoutée."}

@router.get("/api-keys")
async def list_api_keys(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserApiKey).where(UserApiKey.user_id == user.id))
    keys = result.scalars().all()
    return [{"id":str(k.id),"exchange":k.exchange,"label":k.label,"is_valid":k.is_valid,
             "permissions":k.permissions,"created_at":k.created_at.isoformat() if k.created_at else None} for k in keys]

@router.delete("/api-keys/{key_id}")
async def delete_api_key(key_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserApiKey).where(UserApiKey.id==key_id, UserApiKey.user_id==user.id))
    key = result.scalar_one_or_none()
    if not key: raise HTTPException(status_code=404, detail="Clé introuvable.")
    await db.delete(key); await db.commit()
    return {"message": "Clé supprimée."}

@router.get("/alerts")
async def get_alerts(limit: int = 30, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import desc
    result = await db.execute(select(UserAlert).where(UserAlert.user_id==user.id).order_by(desc(UserAlert.created_at)).limit(limit))
    alerts = result.scalars().all()
    return [{"id":str(a.id),"type":a.alert_type,"title":a.title,"message":a.message,
             "is_read":a.is_read,"created_at":a.created_at.isoformat() if a.created_at else None} for a in alerts]
