"""
BTF – Gardien du Risque (Module D)
Priorité absolue : protéger le capital utilisateur.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.models import (
    RiskProfile, TradeOrder, OrderStatus, User, UserAlert, AlertType
)
from backend.utils.notifications import send_emergency_stop_alert

logger = logging.getLogger("btf.risk")

MAX_RISK_PER_TRADE_PCT = 1.0    # 1% du capital maximum
MAX_DAILY_DRAWDOWN_PCT = 2.0    # 2% drawdown → arrêt d'urgence 24h


class RiskManager:
    """
    Gardien du Risque – Veto absolu sur tous les ordres.
    Calculs de risque, validation et arrêt d'urgence.
    """

    @staticmethod
    def calculate_risk(
        capital: float,
        entry_price: float,
        stop_loss: Optional[float],
        quantity: float,
        max_risk_pct: float = MAX_RISK_PER_TRADE_PCT,
    ) -> dict:
        """
        Calcule le risque réel d'un trade.
        Retourne le % de risque, le montant risqué, et le ratio R/R.
        """
        if not stop_loss or entry_price <= 0 or capital <= 0:
            return {
                "risk_percent": 0.0,
                "risk_amount": 0.0,
                "rr_ratio": "N/A",
                "valid": True,
                "reason": "Pas de Stop-Loss défini",
            }

        risk_per_unit = abs(entry_price - stop_loss)
        total_risk = risk_per_unit * quantity
        risk_percent = (total_risk / capital) * 100

        valid = risk_percent <= max_risk_pct
        reason = "" if valid else f"Risque {risk_percent:.2f}% > maximum {max_risk_pct}%"

        # Max position recommandée
        max_position = (capital * max_risk_pct / 100) / risk_per_unit if risk_per_unit > 0 else 0

        return {
            "risk_percent": round(risk_percent, 4),
            "risk_amount": round(total_risk, 4),
            "rr_ratio": RiskManager._calc_rr(entry_price, stop_loss, None),
            "max_position": round(max_position, 6),
            "valid": valid,
            "reason": reason,
        }

    @staticmethod
    def _calc_rr(entry: float, stop_loss: Optional[float], take_profit: Optional[float]) -> str:
        if not stop_loss or not take_profit or entry <= 0:
            return "N/A"
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        if risk == 0:
            return "∞"
        ratio = reward / risk
        return f"1:{ratio:.2f}"

    @staticmethod
    def validate_order(order_data: dict, risk_profile: RiskProfile, portfolio_value: float) -> dict:
        """
        Validation complète d'un ordre avant exécution.
        Droit de veto absolu.
        """
        errors = []

        # 1. Vérifier arrêt d'urgence
        if risk_profile.emergency_stopped:
            return {
                "approved": False,
                "veto": True,
                "reason": "🛑 VETO: Arrêt d'urgence actif. Trading bloqué 24h.",
            }

        # 2. Stop-Loss obligatoire
        if risk_profile.require_stop_loss and not order_data.get("stop_loss"):
            errors.append("Stop-Loss manquant (obligatoire)")

        # 3. Risque par trade
        risk_calc = RiskManager.calculate_risk(
            capital=portfolio_value,
            entry_price=order_data.get("price", 0),
            stop_loss=order_data.get("stop_loss"),
            quantity=order_data.get("quantity", 0),
            max_risk_pct=risk_profile.max_risk_per_trade,
        )
        if not risk_calc["valid"]:
            errors.append(risk_calc["reason"])

        # 4. Drawdown quotidien
        remaining_drawdown = risk_profile.max_daily_drawdown - risk_profile.current_daily_drawdown
        if remaining_drawdown <= 0:
            errors.append(f"Drawdown quotidien max atteint ({risk_profile.max_daily_drawdown}%)")

        if errors:
            return {"approved": False, "veto": True, "reason": " | ".join(errors)}

        return {
            "approved": True,
            "veto": False,
            "risk_percent": risk_calc["risk_percent"],
            "rr_ratio": risk_calc["rr_ratio"],
        }


class DrawdownMonitor:
    """
    Surveillance du drawdown en temps réel.
    Déclenche l'arrêt d'urgence si drawdown ≥ 2%.
    """

    @staticmethod
    async def check_and_update(
        user: User,
        pnl_delta: float,
        portfolio_value: float,
        db: AsyncSession,
    ) -> bool:
        """
        Met à jour le drawdown et vérifie le seuil d'urgence.
        Retourne True si arrêt d'urgence déclenché.
        """
        result = await db.execute(select(RiskProfile).where(RiskProfile.user_id == user.id))
        risk = result.scalar_one_or_none()
        if not risk:
            return False

        if pnl_delta < 0 and portfolio_value > 0:
            drawdown_delta = abs(pnl_delta) / portfolio_value * 100
            risk.current_daily_drawdown += drawdown_delta

        if risk.current_daily_drawdown >= MAX_DAILY_DRAWDOWN_PCT and not risk.emergency_stopped:
            # ── ARRÊT D'URGENCE ─────────────────────────────────────────────
            risk.emergency_stopped = True
            risk.emergency_stop_at = datetime.now(timezone.utc)
            risk.emergency_resume_at = datetime.now(timezone.utc) + timedelta(hours=24)

            # Créer alerte
            alert = UserAlert(
                user_id=user.id,
                alert_type=AlertType.EMERGENCY_STOP,
                title="🛑 Arrêt d'Urgence Automatique",
                message=(
                    f"Drawdown quotidien de {risk.current_daily_drawdown:.2f}% atteint. "
                    f"Trading bloqué 24h jusqu'au {risk.emergency_resume_at.isoformat()}."
                ),
            )
            db.add(alert)
            await db.commit()
            await send_emergency_stop_alert(user, risk.current_daily_drawdown, risk.emergency_resume_at)
            logger.warning(f"🛑 ARRÊT D'URGENCE – User {user.id} – Drawdown {risk.current_daily_drawdown:.2f}%")
            return True

        await db.commit()
        return False

    @staticmethod
    async def reset_daily(user_id: str, db: AsyncSession):
        """Réinitialisation quotidienne du drawdown (00:00 UTC)."""
        result = await db.execute(select(RiskProfile).where(RiskProfile.user_id == user_id))
        risk = result.scalar_one_or_none()
        if risk:
            risk.current_daily_drawdown = 0.0
            risk.daily_reset_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info(f"✅ Drawdown reset – User {user_id}")
