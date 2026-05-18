"""BTF – Router Marchés (OHLCV, Tickers, Signaux IA)"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.models import AISignal, MarketData
from backend.routers.auth import get_current_user
from backend.utils.database import get_db

router = APIRouter()

@router.get("/tickers")
async def get_tickers(user=Depends(get_current_user)):
    """Retourne les tickers simulés (en prod : CCXT live)."""
    return [
        {"symbol":"BTC/USDT","exchange":"binance","last":67234.5,"change_24h":2.14,"volume_24h":"2.4B"},
        {"symbol":"ETH/USDT","exchange":"bybit",  "last":3421.0,  "change_24h":1.87,"volume_24h":"890M"},
        {"symbol":"BNB/USDT","exchange":"binance","last":584.0,   "change_24h":-0.43,"volume_24h":"120M"},
        {"symbol":"SOL/USDT","exchange":"okx",    "last":178.0,   "change_24h":3.21,"volume_24h":"450M"},
        {"symbol":"SONATEL", "exchange":"brvm",   "last":14500,   "change_24h":0.69,"volume_24h":"N/A"},
        {"symbol":"CORIS BANK","exchange":"brvm", "last":8750,    "change_24h":-0.23,"volume_24h":"N/A"},
    ]

@router.get("/signals")
async def get_signals(limit: int = 20, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    result = await db.execute(select(AISignal).order_by(desc(AISignal.created_at)).limit(limit))
    signals = result.scalars().all()
    return [{"id":str(s.id),"symbol":s.symbol,"exchange":s.exchange,"signal":s.signal,
             "confidence":s.confidence,"indicators":s.indicators,"reasoning":s.reasoning,
             "suggested_sl":float(s.suggested_sl) if s.suggested_sl else None,
             "suggested_tp":float(s.suggested_tp) if s.suggested_tp else None,
             "created_at":s.created_at.isoformat() if s.created_at else None} for s in signals]

@router.get("/ohlcv")
async def get_ohlcv(exchange: str, symbol: str, timeframe: str = "15m", limit: int = 100, user=Depends(get_current_user)):
    """Retourne les données OHLCV (simulées en demo, live en prod)."""
    import random, time
    base = 67000 if "BTC" in symbol else 3400 if "ETH" in symbol else 580
    data = []
    ts = int(time.time()*1000) - limit*900000
    for i in range(limit):
        o = base + random.uniform(-200,200)
        h = o + random.uniform(0,300)
        l = o - random.uniform(0,300)
        c = l + random.uniform(0, h-l)
        data.append({"timestamp":ts+i*900000,"open":round(o,2),"high":round(h,2),
                     "low":round(l,2),"close":round(c,2),"volume":round(random.uniform(100,5000),2)})
    return data
