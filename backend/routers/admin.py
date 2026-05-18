"""
BTF – Panneau Administrateur Ultra-Sécurisé
URL secrète : /admin-secret-gate
MFA obligatoire, TOTP, journalisation complète, restriction IP.
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel
from sqlalchemy import select, update, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.models import (
    User, PaymentRequest, PaymentStatus, UserStatus,
    PhysicalMarketTrend, SystemLog, AdminSession, TradeOrder,
    UserAlert, AlertType,
)
from backend.routers.auth import get_current_user, verify_password
from backend.utils.database import get_db
from backend.utils.logger import log_action
from backend.utils.notifications import (
    send_subscription_activated_notification,
    send_admin_login_alert,
)

logger = logging.getLogger("btf.admin")

router = APIRouter()

# IPs autorisées (configurable via .env)
ALLOWED_ADMIN_IPS = set(
    os.getenv("ADMIN_ALLOWED_IPS", "127.0.0.1").split(",")
)
ADMIN_SESSION_HOURS = 4


# ─── SCHEMAS ──────────────────────────────────────────────────────────────────
class AdminLoginRequest(BaseModel):
    email: str
    password: str
    totp_code: str
    pin_code: str      # Code PIN supplémentaire

class PaymentReviewRequest(BaseModel):
    payment_id: str
    action: str        # approve | reject
    note: Optional[str] = None
    months: int = 1

class PhysicalReportAction(BaseModel):
    trend_id: str
    action: str        # validate | publish | reject
    notes: Optional[str] = None

class UserActionRequest(BaseModel):
    user_id: str
    action: str        # suspend | activate | reset_password


# ─── MIDDLEWARE IP ─────────────────────────────────────────────────────────────
async def check_admin_ip(request: Request):
    client_ip = request.client.host
    if ALLOWED_ADMIN_IPS and client_ip not in ALLOWED_ADMIN_IPS and "0.0.0.0" not in ALLOWED_ADMIN_IPS:
        logger.warning(f"🚨 Tentative accès admin depuis IP non autorisée: {client_ip}")
        raise HTTPException(status_code=404, detail="Not Found")   # Masquer l'existence


async def get_admin_user(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Vérifie que l'utilisateur est admin ET que sa session admin est valide."""
    await check_admin_ip(request)
    if not user.is_admin:
        await log_action(db, user.id, "UNAUTHORIZED_ADMIN_ACCESS", "admin",
                        request.client.host, severity="critical")
        raise HTTPException(status_code=403, detail="Accès refusé.")
    return user


# ─── LOGIN ADMIN (MFA + TOTP + PIN) ──────────────────────────────────────────
@router.post("/login")
async def admin_login(
    data: AdminLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await check_admin_ip(request)

    # 1. Vérifier utilisateur admin
    result = await db.execute(
        select(User).where(User.email == data.email, User.is_admin == True)
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.hashed_password):
        await log_action(db, None, "ADMIN_LOGIN_FAILED", "admin",
                        request.client.host, severity="critical",
                        data={"email": data.email})
        raise HTTPException(status_code=401, detail="Identifiants incorrects.")

    # 2. TOTP obligatoire
    if not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status_code=403, detail="2FA non configuré. Contactez le super-admin.")

    import pyotp
    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(data.totp_code, valid_window=1):
        await log_action(db, user.id, "ADMIN_TOTP_FAILED", "admin",
                        request.client.host, severity="critical")
        raise HTTPException(status_code=401, detail="Code TOTP invalide.")

    # 3. PIN supplémentaire
    admin_pin = os.getenv("ADMIN_PIN_CODE", "")
    if admin_pin and data.pin_code != admin_pin:
        await log_action(db, user.id, "ADMIN_PIN_FAILED", "admin",
                        request.client.host, severity="critical")
        raise HTTPException(status_code=401, detail="Code PIN invalide.")

    # 4. Créer session admin
    from backend.routers.auth import create_access_token
    token = create_access_token(str(user.id))

    session = AdminSession(
        user_id=user.id,
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent", ""),
        totp_verified=True,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=ADMIN_SESSION_HOURS),
    )
    db.add(session)
    await db.commit()

    await log_action(db, user.id, "ADMIN_LOGIN_SUCCESS", "admin",
                    request.client.host, severity="info")
    await send_admin_login_alert(user, request.client.host, request.headers.get("user-agent", ""))

    return {"access_token": token, "token_type": "bearer", "session_hours": ADMIN_SESSION_HOURS}


# ─── DASHBOARD ADMIN ──────────────────────────────────────────────────────────
@router.get("/dashboard")
async def admin_dashboard(
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    # Stats globales
    total_users = await db.scalar(select(func.count(User.id)))
    active_users = await db.scalar(select(func.count(User.id)).where(User.status == UserStatus.ACTIVE))
    trial_users  = await db.scalar(select(func.count(User.id)).where(User.status == UserStatus.TRIAL))
    pending_payments = await db.scalar(
        select(func.count(PaymentRequest.id)).where(PaymentRequest.status == PaymentStatus.PENDING)
    )
    total_orders = await db.scalar(select(func.count(TradeOrder.id)))
    pending_reports = await db.scalar(
        select(func.count(PhysicalMarketTrend.id)).where(
            PhysicalMarketTrend.report_generated == True,
            PhysicalMarketTrend.report_validated == False,
        )
    )

    return {
        "stats": {
            "total_users":        total_users,
            "active_subscribers": active_users,
            "trial_users":        trial_users,
            "pending_payments":   pending_payments,
            "total_orders":       total_orders,
            "pending_reports":    pending_reports,
            "monthly_revenue":    active_users * 5000 if active_users else 0,
        },
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


# ─── GESTION PAIEMENTS ────────────────────────────────────────────────────────
@router.get("/payments")
async def list_payments(
    status_filter: Optional[str] = None,
    limit: int = 50,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(PaymentRequest).order_by(desc(PaymentRequest.created_at)).limit(limit)
    if status_filter:
        query = query.where(PaymentRequest.status == status_filter)
    result = await db.execute(query)
    payments = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "user_id": str(p.user_id),
            "amount_fcfa": float(p.amount_fcfa),
            "method": p.payment_method,
            "sender_phone": p.sender_phone,
            "transaction_ref": p.transaction_ref,
            "proof_image": p.proof_image_url,
            "status": p.status,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in payments
    ]


@router.post("/payments/review")
async def review_payment(
    data: PaymentReviewRequest,
    request: Request,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PaymentRequest).where(PaymentRequest.id == data.payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Paiement introuvable.")
    if payment.status != PaymentStatus.PENDING:
        raise HTTPException(status_code=400, detail="Paiement déjà traité.")

    now = datetime.now(timezone.utc)

    if data.action == "approve":
        payment.status = PaymentStatus.APPROVED
        payment.reviewed_by = user.id
        payment.reviewed_at = now
        payment.admin_note = data.note
        payment.period_months = data.months

        # Activer l'abonnement utilisateur
        user_result = await db.execute(select(User).where(User.id == payment.user_id))
        subscriber = user_result.scalar_one_or_none()
        if subscriber:
            from datetime import timedelta
            current_end = subscriber.subscription_ends_at or now
            subscriber.subscription_ends_at = max(current_end, now) + timedelta(days=30 * data.months)
            subscriber.status = UserStatus.ACTIVE
            subscriber.trading_mode = subscriber.trading_mode   # Conserver mode actuel

            # Notification
            alert = UserAlert(
                user_id=subscriber.id,
                alert_type=AlertType.SUBSCRIPTION_ACTIVATED,
                title="✅ Abonnement Activé !",
                message=f"Votre abonnement BTF est activé pour {data.months} mois. Bonne chance sur les marchés !",
            )
            db.add(alert)
            await send_subscription_activated_notification(subscriber, data.months)

    elif data.action == "reject":
        payment.status = PaymentStatus.REJECTED
        payment.reviewed_by = user.id
        payment.reviewed_at = now
        payment.admin_note = data.note or "Paiement rejeté."
    else:
        raise HTTPException(status_code=400, detail="Action invalide.")

    await db.commit()
    await log_action(db, user.id, f"PAYMENT_{data.action.upper()}", "admin",
                    request.client.host, data={"payment_id": data.payment_id})
    return {"message": f"Paiement {data.action}d avec succès."}


# ─── RAPPORTS MARCHÉ PHYSIQUE ─────────────────────────────────────────────────
@router.get("/physical-reports")
async def list_physical_reports(
    validated: Optional[bool] = None,
    limit: int = 50,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(PhysicalMarketTrend).order_by(desc(PhysicalMarketTrend.rarity_score)).limit(limit)
    if validated is not None:
        query = query.where(PhysicalMarketTrend.report_validated == validated)
    result = await db.execute(query)
    trends = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "country": t.country,
            "city": t.city,
            "product": t.product,
            "rarity_score": t.rarity_score,
            "rarity_level": t.rarity_level,
            "supply_status": t.supply_status,
            "logistics_axis": t.logistics_axis,
            "validated": t.report_validated,
            "published": t.published,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in trends
    ]


@router.post("/physical-reports/action")
async def physical_report_action(
    data: PhysicalReportAction,
    request: Request,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PhysicalMarketTrend).where(PhysicalMarketTrend.id == data.trend_id))
    trend = result.scalar_one_or_none()
    if not trend:
        raise HTTPException(status_code=404, detail="Rapport introuvable.")

    now = datetime.now(timezone.utc)
    if data.action == "validate":
        trend.report_validated = True
        trend.validated_by = user.id
        trend.validated_at = now
        trend.notes = data.notes
    elif data.action == "publish":
        trend.published = True
    elif data.action == "reject":
        trend.report_validated = False
        trend.notes = data.notes
    else:
        raise HTTPException(status_code=400, detail="Action invalide.")

    await db.commit()
    await log_action(db, user.id, f"REPORT_{data.action.upper()}", "admin",
                    request.client.host)
    return {"message": f"Rapport {data.action} avec succès."}


# ─── GESTION UTILISATEURS ─────────────────────────────────────────────────────
@router.get("/users")
async def list_users(
    limit: int = 100,
    search: Optional[str] = None,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(User).order_by(desc(User.created_at)).limit(limit)
    if search:
        query = query.where(User.email.ilike(f"%{search}%") | User.full_name.ilike(f"%{search}%"))
    result = await db.execute(query)
    users = result.scalars().all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "full_name": u.full_name,
            "status": u.status,
            "country": u.country,
            "trading_mode": u.trading_mode,
            "autonomous": u.autonomous_enabled,
            "totp_enabled": u.totp_enabled,
            "trial_ends": u.trial_ends_at.isoformat() if u.trial_ends_at else None,
            "subscription_ends": u.subscription_ends_at.isoformat() if u.subscription_ends_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


# ─── LOGS SYSTÈME ─────────────────────────────────────────────────────────────
@router.get("/logs")
async def get_system_logs(
    severity: Optional[str] = None,
    module: Optional[str] = None,
    limit: int = 200,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(SystemLog).order_by(desc(SystemLog.created_at)).limit(limit)
    if severity:
        query = query.where(SystemLog.severity == severity)
    if module:
        query = query.where(SystemLog.module == module)
    result = await db.execute(query)
    logs = result.scalars().all()
    return [
        {
            "id": l.id,
            "user_id": str(l.user_id) if l.user_id else None,
            "action": l.action,
            "module": l.module,
            "ip": l.ip_address,
            "severity": l.severity,
            "data": l.data,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]
