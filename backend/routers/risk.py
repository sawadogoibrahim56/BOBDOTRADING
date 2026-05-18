"""BTF – Router Risk Manager"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.models import RiskProfile
from backend.routers.auth import get_current_user
from backend.utils.database import get_db

router = APIRouter()

class RiskProfileUpdate(BaseModel):
    max_risk_per_trade: float | None = None
    max_daily_drawdown: float | None = None
    max_open_trades: int | None = None
    require_stop_loss: bool | None = None
    require_take_profit: bool | None = None

@router.get("/profile")
async def get_risk_profile(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RiskProfile).where(RiskProfile.user_id==user.id))
    r = result.scalar_one_or_none()
    if not r: raise HTTPException(status_code=404, detail="Profil de risque introuvable.")
    return {"max_risk_per_trade":r.max_risk_per_trade,"max_daily_drawdown":r.max_daily_drawdown,
            "current_daily_drawdown":r.current_daily_drawdown,"emergency_stopped":r.emergency_stopped,
            "emergency_resume_at":r.emergency_resume_at.isoformat() if r.emergency_resume_at else None,
            "require_stop_loss":r.require_stop_loss,"require_take_profit":r.require_take_profit,
            "max_open_trades":r.max_open_trades}

@router.put("/profile")
async def update_risk_profile(data: RiskProfileUpdate, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RiskProfile).where(RiskProfile.user_id==user.id))
    r = result.scalar_one_or_none()
    if not r: raise HTTPException(status_code=404, detail="Profil introuvable.")
    if data.max_risk_per_trade is not None:
        if data.max_risk_per_trade > 3.0: raise HTTPException(status_code=400, detail="Risque max : 3% absolu.")
        r.max_risk_per_trade = data.max_risk_per_trade
    if data.max_daily_drawdown is not None:
        if data.max_daily_drawdown > 5.0: raise HTTPException(status_code=400, detail="Drawdown max : 5% absolu.")
        r.max_daily_drawdown = data.max_daily_drawdown
    if data.max_open_trades is not None: r.max_open_trades = data.max_open_trades
    if data.require_stop_loss is not None: r.require_stop_loss = data.require_stop_loss
    if data.require_take_profit is not None: r.require_take_profit = data.require_take_profit
    await db.commit()
    return {"message": "Profil de risque mis à jour."}
