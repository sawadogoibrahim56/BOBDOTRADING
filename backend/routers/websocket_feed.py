"""
BTF – WebSocket Tick-by-Tick via CCXT
Flux de prix en temps réel pour le frontend.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

import ccxt.async_support as ccxt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from jose import JWTError, jwt

from backend.routers.auth import SECRET_KEY, ALGORITHM

logger = logging.getLogger("btf.websocket")
router = APIRouter()

# Gestionnaire de connexions actives
class ConnectionManager:
    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.active.setdefault(user_id, []).append(ws)
        logger.info(f"WS connecté: user={user_id}")

    def disconnect(self, user_id: str, ws: WebSocket):
        if user_id in self.active:
            self.active[user_id].discard(ws) if hasattr(self.active[user_id], 'discard') else None
            try:
                self.active[user_id].remove(ws)
            except ValueError:
                pass

    async def send(self, user_id: str, data: dict):
        dead = []
        for ws in self.active.get(user_id, []):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for d in dead:
            self.disconnect(user_id, d)

    async def broadcast(self, data: dict):
        for user_id in list(self.active.keys()):
            await self.send(user_id, data)


manager = ConnectionManager()

SYMBOLS = {
    "binance": ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "ADA/USDT", "XRP/USDT"],
    "okx":     ["SOL/USDT"],
}


@router.websocket("/prices")
async def ws_prices(
    websocket: WebSocket,
    token: str = Query(...),
):
    """WebSocket public pour les prix en temps réel."""
    # Valider le token JWT
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=4001)
            return
    except JWTError:
        await websocket.close(code=4001)
        return

    await manager.connect(user_id, websocket)
    try:
        # Démarrer le stream de prix pour cet utilisateur
        price_task = asyncio.create_task(_stream_prices(user_id))
        while True:
            data = await websocket.receive_text()
            # Gérer les messages client (ex: changer de symbole)
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
        price_task.cancel()
        logger.info(f"WS déconnecté: user={user_id}")


async def _stream_prices(user_id: str):
    """Stream les prix depuis Binance via CCXT."""
    exchange = ccxt.binance({"enableRateLimit": True})
    try:
        while True:
            prices = {}
            for symbol in SYMBOLS["binance"]:
                try:
                    ticker = await exchange.fetch_ticker(symbol)
                    prices[symbol] = {
                        "symbol": symbol,
                        "exchange": "binance",
                        "last": ticker["last"],
                        "bid": ticker["bid"],
                        "ask": ticker["ask"],
                        "change_24h": ticker["percentage"],
                        "volume_24h": ticker["quoteVolume"],
                        "high_24h": ticker["high"],
                        "low_24h": ticker["low"],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                except Exception:
                    pass

            if prices:
                await manager.send(user_id, {
                    "type": "prices",
                    "data": prices,
                    "server_time": datetime.now(timezone.utc).isoformat(),
                })
            await asyncio.sleep(2)   # Mise à jour toutes les 2 secondes
    except asyncio.CancelledError:
        pass
    finally:
        await exchange.close()


@router.websocket("/alerts/{user_id}")
async def ws_alerts(websocket: WebSocket, user_id: str, token: str = Query(...)):
    """WebSocket pour les alertes temps réel (ordres, drawdown, signaux IA)."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("sub") != user_id:
            await websocket.close(code=4003)
            return
    except JWTError:
        await websocket.close(code=4001)
        return

    await manager.connect(f"alerts_{user_id}", websocket)
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        manager.disconnect(f"alerts_{user_id}", websocket)


async def broadcast_alert(user_id: str, alert_data: dict):
    """Envoie une alerte temps réel à un utilisateur."""
    await manager.send(f"alerts_{user_id}", {
        "type": "alert",
        "data": alert_data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def broadcast_order_executed(user_id: str, order: dict):
    """Notifie l'exécution d'un ordre en temps réel."""
    await broadcast_alert(user_id, {
        "alert_type": "order_executed",
        "title": "⚡ Ordre Exécuté",
        "order": order,
    })
