"""BTF – Router Marché Physique UEMOA"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.models import PhysicalMarketTrend
from backend.routers.auth import get_current_user
from backend.utils.database import get_db

router = APIRouter()

@router.get("/trends")
async def get_trends(
    country: str | None = None,
    category: str | None = None,
    limit: int = 50,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(PhysicalMarketTrend).order_by(desc(PhysicalMarketTrend.rarity_score)).limit(limit)
    if country: query = query.where(PhysicalMarketTrend.country == country)
    if category: query = query.where(PhysicalMarketTrend.category == category)
    result = await db.execute(query)
    trends = result.scalars().all()
    return [{"id":str(t.id),"country":t.country,"city":t.city,"product":t.product,
             "category":t.category,"rarity_score":t.rarity_score,"rarity_level":t.rarity_level,
             "supply_status":t.supply_status,"demand_level":t.demand_level,
             "logistics_axis":t.logistics_axis,"price_local":float(t.price_local) if t.price_local else None,
             "price_currency":t.price_currency,"created_at":t.created_at.isoformat() if t.created_at else None}
            for t in trends]

@router.get("/report")
async def get_physical_report(user=Depends(get_current_user)):
    from backend.services.physical_scanner import PhysicalMarketScanner
    return await PhysicalMarketScanner.get_summary_report()
