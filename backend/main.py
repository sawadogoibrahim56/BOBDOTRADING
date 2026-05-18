import os
"""
Bobdo Trading and Finance (BTF)
================================
Backend Principal – FastAPI
Version 1.3 – Production Ready
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.middleware.security import SecurityHeadersMiddleware, RateLimitMiddleware
from backend.middleware.logging import AuditLogMiddleware
from backend.routers import (
    auth,
    users,
    trading,
    markets,
    physical_market,
    payments,
    admin,
    risk,
    websocket_feed,
)
from backend.services.market_scanner import MarketScannerService
from backend.services.physical_scanner import PhysicalMarketScanner
from backend.services.autonomous_trader import AutonomousTrader
from backend.utils.database import init_db
from backend.utils.scheduler import start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("btf.main")


# ─── LIFESPAN (startup / shutdown) ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 BTF démarrage...")
    await init_db()
    await start_scheduler()
    asyncio.create_task(MarketScannerService.run_forever())
    asyncio.create_task(PhysicalMarketScanner.run_forever())
    asyncio.create_task(AutonomousTrader.run_forever())
    logger.info("✅ BTF opérationnel – Tous les services actifs")
    yield
    logger.info("🔴 BTF arrêt en cours...")


# ─── APPLICATION ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Bobdo Trading and Finance (BTF)",
    description="Hedge & Trade Operating System – Afrique de l'Ouest",
    version="1.3.0",
    docs_url=None,          # désactiver docs en production
    redoc_url=None,
    lifespan=lifespan,
)

# ─── MIDDLEWARES ───────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "https://btf.bf,http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, max_requests=200, window_seconds=60)
app.add_middleware(AuditLogMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["btf.bf", "*.btf.bf", "localhost"])

# ─── ROUTERS ──────────────────────────────────────────────────────────────────
app.include_router(auth.router,            prefix="/api/v1/auth",           tags=["Auth"])
app.include_router(users.router,           prefix="/api/v1/users",          tags=["Users"])
app.include_router(trading.router,         prefix="/api/v1/trading",        tags=["Trading"])
app.include_router(markets.router,         prefix="/api/v1/markets",        tags=["Markets"])
app.include_router(physical_market.router, prefix="/api/v1/physical",       tags=["Marché Physique"])
app.include_router(payments.router,        prefix="/api/v1/payments",       tags=["Paiements"])
app.include_router(risk.router,            prefix="/api/v1/risk",           tags=["Risk Manager"])
app.include_router(websocket_feed.router,  prefix="/ws",                    tags=["WebSocket"])
# Admin sur URL secrète
app.include_router(admin.router,           prefix="/admin-secret-gate",     tags=["Admin"])


# ─── HEALTH CHECK ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "BTF", "version": "1.3.0"}


# ─── GLOBAL ERROR HANDLER ─────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_error_handler(request: Request, exc: Exception):
    logger.error(f"Erreur non gérée: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erreur interne. L'incident a été enregistré."},
    )
