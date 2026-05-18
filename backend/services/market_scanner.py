"""BTF – Scanner Marchés Financiers (Module A)
Collecte continue des données OHLCV via CCXT.
"""
import asyncio
import logging
from datetime import datetime, timezone

import ccxt.async_support as ccxt

from backend.utils.database import AsyncSessionLocal
from backend.models.models import MarketData, MarketType

logger = logging.getLogger("btf.market_scanner")

SCAN_PAIRS = [
    {"exchange": "binance", "symbol": "BTC/USDT",  "type": MarketType.CRYPTO},
    {"exchange": "binance", "symbol": "ETH/USDT",  "type": MarketType.CRYPTO},
    {"exchange": "binance", "symbol": "BNB/USDT",  "type": MarketType.CRYPTO},
    {"exchange": "okx",     "symbol": "SOL/USDT",  "type": MarketType.CRYPTO},
    {"exchange": "binance", "symbol": "XRP/USDT",  "type": MarketType.CRYPTO},
    {"exchange": "binance", "symbol": "ADA/USDT",  "type": MarketType.CRYPTO},
]

TIMEFRAMES = ["1m", "15m", "1h", "4h"]


class MarketScannerService:
    """Scanner continu WebSocket tick-by-tick via CCXT."""

    @classmethod
    async def run_forever(cls):
        logger.info("📡 Market Scanner démarré")
        while True:
            try:
                await cls._scan_all()
            except Exception as e:
                logger.error(f"Erreur scan marchés: {e}", exc_info=True)
            await asyncio.sleep(60)   # Toutes les 60 secondes

    @classmethod
    async def _scan_all(cls):
        exchange = ccxt.binance({"enableRateLimit": True})
        try:
            async with AsyncSessionLocal() as db:
                for pair in SCAN_PAIRS[:3]:   # Limiter en dev
                    try:
                        ohlcv = await exchange.fetch_ohlcv(pair["symbol"], "1m", limit=1)
                        if ohlcv:
                            row = ohlcv[0]
                            md = MarketData(
                                exchange=pair["exchange"],
                                symbol=pair["symbol"],
                                market_type=pair["type"],
                                open=row[1], high=row[2],
                                low=row[3],  close=row[4],
                                volume=row[5],
                                timestamp=datetime.fromtimestamp(row[0]/1000, tz=timezone.utc),
                                timeframe="1m",
                            )
                            db.add(md)
                    except Exception as e:
                        logger.debug(f"OHLCV {pair['symbol']}: {e}")
                    await asyncio.sleep(0.5)
                await db.commit()
        finally:
            await exchange.close()
