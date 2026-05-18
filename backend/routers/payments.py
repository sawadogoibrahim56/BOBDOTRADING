"""
BTF – Paiements : Orange Money, Wave, Moov Money
Numéros de réception uniquement dans les variables d'environnement.
Validation manuelle par l'administrateur.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.models import PaymentRequest, PaymentStatus, User
from backend.routers.auth import get_current_user
from backend.utils.database import get_db
from backend.utils.logger import log_action
from backend.utils.notifications import send_payment_received_notification

logger = logging.getLogger("btf.payments")
router = APIRouter()

SUBSCRIPTION_AMOUNT_FCFA = 5000.00

# Numéros de réception depuis .env UNIQUEMENT (jamais en base)
PAYMENT_NUMBERS = {
    "orange_money": os.getenv("ORANGE_MONEY_NUMBER", ""),
    "wave":         os.getenv("WAVE_NUMBER", ""),
    "moov_money":   os.getenv("MOOV_MONEY_NUMBER", ""),
}

PAYMENT_METHODS = ["orange_money", "wave", "moov_money"]


class PaymentInfoResponse(BaseModel):
    amount_fcfa: float
    methods: dict
    instructions: str


class PaymentSubmitResponse(BaseModel):
    payment_id: str
    status: str
    message: str


# ─── INFO PAIEMENT (retourner les numéros depuis .env) ────────────────────────
@router.get("/info", response_model=PaymentInfoResponse)
async def get_payment_info(user: User = Depends(get_current_user)):
    """
    Retourne les numéros de paiement depuis les variables d'environnement.
    Ces numéros ne sont JAMAIS stockés en base de données.
    """
    methods = {}
    for method, number in PAYMENT_NUMBERS.items():
        if number:
            label = {
                "orange_money": "Orange Money",
                "wave": "Wave",
                "moov_money": "Moov Money",
            }.get(method, method)
            methods[method] = {
                "label": label,
                "number": number,
                "instructions": f"Envoyez {SUBSCRIPTION_AMOUNT_FCFA:,.0f} F CFA au {number} via {label}",
            }

    return PaymentInfoResponse(
        amount_fcfa=SUBSCRIPTION_AMOUNT_FCFA,
        methods=methods,
        instructions=(
            "1. Choisissez votre méthode de paiement\n"
            "2. Envoyez exactement 5 000 F CFA au numéro indiqué\n"
            "3. Notez la référence de transaction\n"
            "4. Soumettez votre preuve de paiement ci-dessous\n"
            "5. L'activation se fait sous 24h ouvrées."
        ),
    )


# ─── SOUMETTRE PREUVE DE PAIEMENT ─────────────────────────────────────────────
@router.post("/submit", response_model=PaymentSubmitResponse)
async def submit_payment(
    payment_method: str = Form(...),
    sender_phone: str = Form(...),
    transaction_ref: str = Form(default=""),
    months: int = Form(default=1),
    proof_image: Optional[UploadFile] = File(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payment_method not in PAYMENT_METHODS:
        raise HTTPException(status_code=400, detail=f"Méthode de paiement invalide. Options: {PAYMENT_METHODS}")

    if months < 1 or months > 12:
        raise HTTPException(status_code=400, detail="Nombre de mois invalide (1-12).")

    # Vérifier pas de paiement en attente
    existing = await db.execute(
        select(PaymentRequest).where(
            PaymentRequest.user_id == user.id,
            PaymentRequest.status == PaymentStatus.PENDING,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Vous avez déjà un paiement en attente de validation."
        )

    # Upload preuve (Supabase Storage)
    proof_url = None
    if proof_image:
        proof_url = await _upload_proof_image(proof_image, str(user.id))

    # Créer la demande de paiement
    payment = PaymentRequest(
        user_id=user.id,
        amount_fcfa=SUBSCRIPTION_AMOUNT_FCFA * months,
        payment_method=payment_method,
        sender_phone=sender_phone,
        transaction_ref=transaction_ref or None,
        proof_image_url=proof_url,
        status=PaymentStatus.PENDING,
        period_months=months,
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)

    await log_action(db, user.id, "PAYMENT_SUBMITTED", "payments",
                    data={"method": payment_method, "months": months})
    await send_payment_received_notification(user, payment)

    return PaymentSubmitResponse(
        payment_id=str(payment.id),
        status="pending",
        message=(
            f"✅ Preuve de paiement reçue. L'administrateur va vérifier votre paiement "
            f"dans les 24h. Votre abonnement sera activé après confirmation."
        ),
    )


# ─── HISTORIQUE PAIEMENTS UTILISATEUR ─────────────────────────────────────────
@router.get("/history")
async def payment_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PaymentRequest)
        .where(PaymentRequest.user_id == user.id)
        .order_by(PaymentRequest.created_at.desc())
        .limit(20)
    )
    payments = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "amount_fcfa": float(p.amount_fcfa),
            "method": p.payment_method,
            "status": p.status,
            "period_months": p.period_months,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "reviewed_at": p.reviewed_at.isoformat() if p.reviewed_at else None,
            "admin_note": p.admin_note,
        }
        for p in payments
    ]


# ─── STATUT ABONNEMENT ────────────────────────────────────────────────────────
@router.get("/subscription-status")
async def subscription_status(user: User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    if user.status.value == "trial":
        days_left = max(0, (user.trial_ends_at - now).days) if user.trial_ends_at else 0
        return {
            "type": "trial",
            "active": days_left > 0,
            "days_remaining": days_left,
            "expires_at": user.trial_ends_at.isoformat() if user.trial_ends_at else None,
        }
    elif user.status.value == "active":
        days_left = max(0, (user.subscription_ends_at - now).days) if user.subscription_ends_at else 0
        return {
            "type": "paid",
            "active": days_left > 0,
            "days_remaining": days_left,
            "expires_at": user.subscription_ends_at.isoformat() if user.subscription_ends_at else None,
        }
    return {"type": "expired", "active": False, "days_remaining": 0}


# ─── UPLOAD IMAGE (Supabase Storage) ─────────────────────────────────────────
async def _upload_proof_image(file: UploadFile, user_id: str) -> str | None:
    """Upload vers Supabase Storage. Retourne l'URL publique."""
    try:
        import supabase
        from supabase import create_client
        url  = os.getenv("SUPABASE_URL", "")
        key  = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            return None
        client = create_client(url, key)
        content = await file.read()
        filename = f"proofs/{user_id}/{datetime.now(timezone.utc).timestamp()}_{file.filename}"
        client.storage.from_("payment-proofs").upload(filename, content)
        return client.storage.from_("payment-proofs").get_public_url(filename)
    except Exception as e:
        logger.warning(f"Upload preuve échoué: {e}")
        return None
