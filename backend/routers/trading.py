"""
BTF – Module Trading : Ordres, Mode Autonome, Exécution
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, validator
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.models import (
    TradeOrder, OrderSide, OrderType, OrderStatus, TradingMode,
    MarketType, RiskProfile, Portfolio, User, UserApiKey, UserAlert, AlertType,
)
from backend.routers.auth import get_current_user, require_active_subscription
from backend.services.risk_manager import RiskManager
from backend.services.exchange_connector import ExchangeConnector
from backend.utils.database import get_db
from backend.utils.logger import log_action
from backend.utils.notifications import send_order_notification

router = APIRouter()


# ─── SCHEMAS ──────────────────────────────────────────────────────────────────
class OrderRequest(BaseModel):
    exchange: str                       # binance, okx, bybit, brvm...
    symbol: str                         # BTC/USDT, SONATEL...
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    quantity: float
    price: Optional[float] = None       # None = market
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    market_type: MarketType = MarketType.CRYPTO

    @validator("quantity")
    def qty_positive(cls, v):
        if v <= 0:
            raise ValueError("La quantité doit être positive.")
        return v

    @validator("stop_loss", "take_profit", always=True)
    def sl_tp_numeric(cls, v):
        if v is not None and v <= 0:
            raise ValueError("Stop-Loss / Take-Profit doivent être positifs.")
        return v


class OrderResponse(BaseModel):
    order_id: str
    status: str
    message: str
    risk_percent: Optional[float]
    estimated_pnl_ratio: Optional[str]


class AutonomousToggle(BaseModel):
    enabled: bool
    confirm: bool = False   # L'utilisateur doit confirmer explicitement


# ─── HELPERS ──────────────────────────────────────────────────────────────────
async def get_user_risk_profile(user_id, db: AsyncSession) -> RiskProfile:
    result = await db.execute(select(RiskProfile).where(RiskProfile.user_id == user_id))
    return result.scalar_one_or_none()


async def get_user_portfolio(user_id, db: AsyncSession) -> Portfolio:
    result = await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
    return result.scalar_one_or_none()


# ─── ROUTES ───────────────────────────────────────────────────────────────────
@router.post("/order", response_model=OrderResponse)
async def place_order(
    data: OrderRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db),
):
    risk_profile = await get_user_risk_profile(user.id, db)
    portfolio = await get_user_portfolio(user.id, db)

    # ── VÉRIFICATION ARRÊT D'URGENCE ─────────────────────────────────────────
    if risk_profile and risk_profile.emergency_stopped:
        now = datetime.now(timezone.utc)
        if risk_profile.emergency_resume_at and risk_profile.emergency_resume_at > now:
            raise HTTPException(
                status_code=403,
                detail=f"🛑 Arrêt d'urgence actif. Trading bloqué jusqu'à {risk_profile.emergency_resume_at.isoformat()}"
            )
        else:
            risk_profile.emergency_stopped = False
            await db.commit()

    # ── VALIDATION STOP-LOSS OBLIGATOIRE ─────────────────────────────────────
    if risk_profile and risk_profile.require_stop_loss and not data.stop_loss:
        raise HTTPException(
            status_code=400,
            detail="Stop-Loss obligatoire. Le Gardien du Risque exige un Stop-Loss sur chaque ordre."
        )

    # ── CALCUL DU RISQUE ──────────────────────────────────────────────────────
    capital = float(portfolio.demo_balance_fcfa if user.trading_mode == TradingMode.DEMO else portfolio.total_value_usdt)
    risk_calc = RiskManager.calculate_risk(
        capital=capital,
        entry_price=data.price or 0,
        stop_loss=data.stop_loss,
        quantity=data.quantity,
        max_risk_pct=risk_profile.max_risk_per_trade if risk_profile else 1.0,
    )

    if risk_calc["risk_percent"] > (risk_profile.max_risk_per_trade if risk_profile else 1.0):
        raise HTTPException(
            status_code=400,
            detail=f"🛑 Risque {risk_calc['risk_percent']:.2f}% dépasse le maximum autorisé de {risk_profile.max_risk_per_trade}%"
        )

    # ── CRÉER L'ORDRE ─────────────────────────────────────────────────────────
    order = TradeOrder(
        user_id    = user.id,
        exchange   = data.exchange,
        market_type= data.market_type,
        symbol     = data.symbol,
        side       = data.side,
        order_type = data.order_type,
        mode       = user.trading_mode,
        quantity   = data.quantity,
        price      = data.price,
        stop_loss  = data.stop_loss,
        take_profit= data.take_profit,
        risk_percent = risk_calc.get("risk_percent"),
        status     = OrderStatus.PENDING,
    )
    db.add(order)
    await db.flush()

    # ── EXÉCUTION ─────────────────────────────────────────────────────────────
    if user.trading_mode == TradingMode.DEMO:
        order.status = OrderStatus.FILLED
        order.filled_price = data.price or await _get_mock_price(data.symbol)
        order.filled_at = datetime.now(timezone.utc)
        await db.commit()
        background_tasks.add_task(send_order_notification, user, order)
        return OrderResponse(
            order_id=str(order.id),
            status="filled",
            message=f"[DEMO] Ordre simulé exécuté – {data.symbol}",
            risk_percent=risk_calc.get("risk_percent"),
            estimated_pnl_ratio=risk_calc.get("rr_ratio"),
        )
    else:
        # Mode réel – récupérer les clés API
        api_key_result = await db.execute(
            select(UserApiKey).where(
                and_(UserApiKey.user_id == user.id, UserApiKey.exchange == data.exchange)
            )
        )
        api_key = api_key_result.scalar_one_or_none()
        if not api_key:
            raise HTTPException(status_code=400, detail=f"Aucune clé API configurée pour {data.exchange}.")

        try:
            connector = ExchangeConnector(api_key)
            result = await connector.place_order(data)
            order.status = OrderStatus.OPEN
            order.exchange_order_id = result.get("id")
            order.raw_response = result
            await db.commit()
            background_tasks.add_task(send_order_notification, user, order)
            return OrderResponse(
                order_id=str(order.id),
                status="open",
                message=f"Ordre réel envoyé sur {data.exchange}",
                risk_percent=risk_calc.get("risk_percent"),
                estimated_pnl_ratio=risk_calc.get("rr_ratio"),
            )
        except Exception as e:
            order.status = OrderStatus.REJECTED
            order.notes = str(e)
            await db.commit()
            raise HTTPException(status_code=500, detail=f"Erreur exchange: {str(e)}")


@router.get("/orders")
async def list_orders(
    limit: int = 50,
    status_filter: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(TradeOrder).where(TradeOrder.user_id == user.id)
    if status_filter:
        query = query.where(TradeOrder.status == status_filter)
    query = query.order_by(TradeOrder.created_at.desc()).limit(limit)
    result = await db.execute(query)
    orders = result.scalars().all()
    return [_order_to_dict(o) for o in orders]


@router.delete("/order/{order_id}")
async def cancel_order(
    order_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TradeOrder).where(and_(TradeOrder.id == order_id, TradeOrder.user_id == user.id))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Ordre introuvable.")
    if order.status not in [OrderStatus.PENDING, OrderStatus.OPEN]:
        raise HTTPException(status_code=400, detail="Ordre non annulable.")

    if user.trading_mode == TradingMode.REAL and order.exchange_order_id:
        api_key_result = await db.execute(
            select(UserApiKey).where(and_(UserApiKey.user_id == user.id, UserApiKey.exchange == order.exchange))
        )
        api_key = api_key_result.scalar_one_or_none()
        if api_key:
            connector = ExchangeConnector(api_key)
            await connector.cancel_order(order.symbol, order.exchange_order_id)

    order.status = OrderStatus.CANCELLED
    await db.commit()
    return {"message": "Ordre annulé."}


@router.post("/autonomous/toggle")
async def toggle_autonomous(
    data: AutonomousToggle,
    user: User = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db),
):
    if data.enabled and not data.confirm:
        raise HTTPException(
            status_code=400,
            detail="Vous devez confirmer explicitement l'activation du mode autonome."
        )
    user.autonomous_enabled = data.enabled
    if data.enabled:
        user.autonomous_authorized_at = datetime.now(timezone.utc)
    await db.commit()
    action = "AUTONOMOUS_ENABLED" if data.enabled else "AUTONOMOUS_DISABLED"
    await log_action(db, user.id, action, "trading")
    return {
        "autonomous_enabled": data.enabled,
        "message": "Mode autonome activé. L'IA analysera et exécutera automatiquement." if data.enabled
                   else "Mode autonome désactivé."
    }


@router.get("/portfolio")
async def get_portfolio(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    portfolio = await get_user_portfolio(user.id, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portefeuille introuvable.")
    return {
        "mode": portfolio.mode,
        "balances": portfolio.balances,
        "demo_balance_fcfa": float(portfolio.demo_balance_fcfa or 0),
        "total_value_usdt": float(portfolio.total_value_usdt or 0),
        "pnl_today": float(portfolio.total_pnl_today or 0),
        "pnl_total": float(portfolio.total_pnl_total or 0),
    }


@router.get("/performance")
async def get_performance(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TradeOrder).where(
            and_(TradeOrder.user_id == user.id, TradeOrder.status == OrderStatus.FILLED)
        ).order_by(TradeOrder.filled_at.desc()).limit(100)
    )
    orders = result.scalars().all()
    total_pnl = sum(float(o.pnl or 0) for o in orders)
    winning = [o for o in orders if (o.pnl or 0) > 0]
    win_rate = (len(winning) / len(orders) * 100) if orders else 0
    return {
        "total_trades": len(orders),
        "winning_trades": len(winning),
        "win_rate": round(win_rate, 2),
        "total_pnl": round(total_pnl, 4),
    }


# ─── UTILS ────────────────────────────────────────────────────────────────────
def _order_to_dict(o: TradeOrder) -> dict:
    return {
        "id": str(o.id),
        "exchange": o.exchange,
        "symbol": o.symbol,
        "side": o.side,
        "order_type": o.order_type,
        "quantity": float(o.quantity),
        "price": float(o.price) if o.price else None,
        "stop_loss": float(o.stop_loss) if o.stop_loss else None,
        "take_profit": float(o.take_profit) if o.take_profit else None,
        "filled_price": float(o.filled_price) if o.filled_price else None,
        "status": o.status,
        "mode": o.mode,
        "risk_percent": o.risk_percent,
        "pnl": float(o.pnl) if o.pnl else None,
        "is_autonomous": o.is_autonomous,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


async def _get_mock_price(symbol: str) -> float:
    mock_prices = {
        "BTC/USDT": 67234.5, "ETH/USDT": 3421.0,
        "BNB/USDT": 584.0, "SOL/USDT": 178.0,
        "SONATEL": 14500.0, "CORIS BANK": 8750.0,
    }
    return mock_prices.get(symbol, 100.0)
