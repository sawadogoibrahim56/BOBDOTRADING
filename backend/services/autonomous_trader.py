"""
BTF – Trader Autonome IA (Module A)
Analyse technique + fondamentale + marché physique → exécution automatique.
"""

import asyncio
import logging
from datetime import datetime, timezone

import ccxt.async_support as ccxt
import numpy as np

from backend.utils.database import AsyncSessionLocal
from backend.models.models import (
    User, TradeOrder, AISignal, RiskProfile, Portfolio,
    UserApiKey, OrderSide, OrderType, OrderStatus, TradingMode,
    MarketType,
)
from backend.services.risk_manager import RiskManager, DrawdownMonitor
from backend.services.technical_analysis import TechnicalAnalysis
from backend.services.nlp_sentiment import NLPSentimentAnalyzer
from sqlalchemy import select, and_

logger = logging.getLogger("btf.autonomous_trader")

SUPPORTED_EXCHANGES = ["binance", "okx", "bybit", "kraken", "kucoin", "gateio", "coinbase"]
SCAN_INTERVAL_SECONDS = 60      # Scan toutes les 60 secondes
SIGNAL_CONFIDENCE_THRESHOLD = 0.65  # Seuil de confiance minimum pour agir

WATCHLIST = [
    {"symbol": "BTC/USDT", "exchange": "binance", "market_type": MarketType.CRYPTO},
    {"symbol": "ETH/USDT", "exchange": "binance", "market_type": MarketType.CRYPTO},
    {"symbol": "BNB/USDT", "exchange": "binance", "market_type": MarketType.CRYPTO},
    {"symbol": "SOL/USDT", "exchange": "okx",     "market_type": MarketType.CRYPTO},
    {"symbol": "SONATEL",  "exchange": "brvm",    "market_type": MarketType.BRVM},
    {"symbol": "CORIS BANK","exchange": "brvm",   "market_type": MarketType.BRVM},
    {"symbol": "ECOBANK CI","exchange": "brvm",   "market_type": MarketType.BRVM},
]


class AutonomousTrader:
    """
    Cerveau principal de BTF.
    Analyse multi-source et exécution automatique après autorisation utilisateur.
    """

    @classmethod
    async def run_forever(cls):
        logger.info("🤖 Trader Autonome démarré")
        while True:
            try:
                await cls._scan_cycle()
            except Exception as e:
                logger.error(f"Erreur cycle autonome: {e}", exc_info=True)
            await asyncio.sleep(SCAN_INTERVAL_SECONDS)

    @classmethod
    async def _scan_cycle(cls):
        async with AsyncSessionLocal() as db:
            # Récupérer tous les utilisateurs avec mode autonome activé
            result = await db.execute(
                select(User).where(and_(User.autonomous_enabled == True, User.is_active == True))
            )
            users = result.scalars().all()

            if not users:
                return

            # Analyser chaque actif de la watchlist
            for asset in WATCHLIST:
                signal = await cls._generate_signal(asset, db)
                if signal and signal["confidence"] >= SIGNAL_CONFIDENCE_THRESHOLD:
                    # Enregistrer le signal en DB
                    ai_signal = AISignal(
                        symbol=asset["symbol"],
                        exchange=asset["exchange"],
                        market_type=asset["market_type"],
                        signal=signal["action"],
                        confidence=signal["confidence"],
                        technical_score=signal.get("technical_score", 0),
                        fundamental_score=signal.get("fundamental_score", 0),
                        sentiment_score=signal.get("sentiment_score", 0),
                        indicators=signal.get("indicators", {}),
                        reasoning=signal.get("reasoning", ""),
                        suggested_sl=signal.get("stop_loss"),
                        suggested_tp=signal.get("take_profit"),
                    )
                    db.add(ai_signal)
                    await db.flush()

                    # Exécuter pour chaque utilisateur autorisé
                    for user in users:
                        await cls._execute_for_user(user, asset, signal, ai_signal.id, db)

            await db.commit()

    @classmethod
    async def _generate_signal(cls, asset: dict, db) -> dict | None:
        """
        Génère un signal de trading hybride :
        Analyse Technique (40%) + Sentiment NLP (30%) + Fondamental (30%)
        """
        try:
            symbol = asset["symbol"]
            exchange_name = asset["exchange"]

            # ── DONNÉES OHLCV ────────────────────────────────────────────────
            ohlcv = await cls._fetch_ohlcv(exchange_name, symbol)
            if not ohlcv or len(ohlcv) < 50:
                return None

            closes = np.array([c[4] for c in ohlcv])
            highs  = np.array([c[2] for c in ohlcv])
            lows   = np.array([c[3] for c in ohlcv])
            volumes= np.array([c[5] for c in ohlcv])

            # ── ANALYSE TECHNIQUE ────────────────────────────────────────────
            tech = TechnicalAnalysis.analyze(closes, highs, lows, volumes)

            # ── SENTIMENT NLP ────────────────────────────────────────────────
            sentiment = await NLPSentimentAnalyzer.analyze(symbol)

            # ── SCORE COMBINÉ ────────────────────────────────────────────────
            tech_score = tech["score"]            # -1.0 à +1.0
            sent_score = sentiment["score"]       # -1.0 à +1.0
            fund_score = 0.0                      # À étendre avec données fondamentales

            combined = (tech_score * 0.40) + (sent_score * 0.30) + (fund_score * 0.30)
            confidence = min(abs(combined) * 1.5, 1.0)

            if combined > 0.2:
                action = "buy"
            elif combined < -0.2:
                action = "sell"
            else:
                action = "hold"

            current_price = float(closes[-1])
            atr = tech.get("atr", current_price * 0.01)

            return {
                "action": action,
                "confidence": round(confidence, 4),
                "combined_score": round(combined, 4),
                "technical_score": round(tech_score, 4),
                "sentiment_score": round(sent_score, 4),
                "fundamental_score": round(fund_score, 4),
                "current_price": current_price,
                "stop_loss": round(current_price - 1.5 * atr, 8) if action == "buy" else round(current_price + 1.5 * atr, 8),
                "take_profit": round(current_price + 2.5 * atr, 8) if action == "buy" else round(current_price - 2.5 * atr, 8),
                "indicators": {
                    "rsi": tech.get("rsi"),
                    "macd": tech.get("macd"),
                    "ema20": tech.get("ema20"),
                    "ema50": tech.get("ema50"),
                    "bb_upper": tech.get("bb_upper"),
                    "bb_lower": tech.get("bb_lower"),
                    "atr": atr,
                },
                "reasoning": cls._build_reasoning(tech, sentiment, action),
            }
        except Exception as e:
            logger.warning(f"Signal error {asset['symbol']}: {e}")
            return None

    @classmethod
    async def _execute_for_user(cls, user: User, asset: dict, signal: dict, signal_id, db):
        """Exécute l'ordre pour un utilisateur si toutes les conditions sont remplies."""
        if signal["action"] == "hold":
            return

        # Vérifier statut utilisateur
        risk_result = await db.execute(select(RiskProfile).where(RiskProfile.user_id == user.id))
        risk = risk_result.scalar_one_or_none()
        if not risk or risk.emergency_stopped:
            return

        portfolio_result = await db.execute(select(Portfolio).where(Portfolio.user_id == user.id))
        portfolio = portfolio_result.scalar_one_or_none()
        if not portfolio:
            return

        capital = float(portfolio.demo_balance_fcfa)

        # Validation du risque (veto absolu)
        order_data = {
            "price": signal["current_price"],
            "stop_loss": signal["stop_loss"],
            "quantity": cls._calc_position_size(capital, signal["current_price"], signal["stop_loss"], risk),
        }
        validation = RiskManager.validate_order(order_data, risk, capital)
        if not validation["approved"]:
            logger.info(f"🛑 Veto IA ordre {asset['symbol']} user {user.id}: {validation['reason']}")
            return

        # Créer et enregistrer l'ordre
        order = TradeOrder(
            user_id=user.id,
            exchange=asset["exchange"],
            market_type=asset["market_type"],
            symbol=asset["symbol"],
            side=OrderSide.BUY if signal["action"] == "buy" else OrderSide.SELL,
            order_type=OrderType.MARKET,
            mode=user.trading_mode,
            quantity=order_data["quantity"],
            price=signal["current_price"],
            stop_loss=signal["stop_loss"],
            take_profit=signal["take_profit"],
            risk_percent=validation.get("risk_percent"),
            status=OrderStatus.FILLED if user.trading_mode == TradingMode.DEMO else OrderStatus.PENDING,
            is_autonomous=True,
            ai_signal_id=signal_id,
            filled_price=signal["current_price"] if user.trading_mode == TradingMode.DEMO else None,
            filled_at=datetime.now(timezone.utc) if user.trading_mode == TradingMode.DEMO else None,
        )
        db.add(order)
        logger.info(f"🤖 Ordre autonome: {signal['action'].upper()} {asset['symbol']} user {user.id}")

    @staticmethod
    def _calc_position_size(capital: float, entry: float, stop_loss: float, risk: RiskProfile) -> float:
        """Calcule la taille de position pour risquer exactement 1% du capital."""
        risk_pct = risk.max_risk_per_trade / 100
        risk_amount = capital * risk_pct
        risk_per_unit = abs(entry - stop_loss) if stop_loss else entry * 0.01
        if risk_per_unit <= 0:
            return 0
        return round(risk_amount / risk_per_unit, 6)

    @staticmethod
    def _build_reasoning(tech: dict, sentiment: dict, action: str) -> str:
        reasons = []
        if tech.get("rsi"):
            if tech["rsi"] < 30:
                reasons.append(f"RSI survendu ({tech['rsi']:.1f})")
            elif tech["rsi"] > 70:
                reasons.append(f"RSI suracheté ({tech['rsi']:.1f})")
            else:
                reasons.append(f"RSI neutre ({tech['rsi']:.1f})")
        if tech.get("macd_bullish"):
            reasons.append("MACD croisement haussier")
        if tech.get("ema_bullish"):
            reasons.append("EMA20 > EMA50 (tendance haussière)")
        if sentiment.get("label"):
            reasons.append(f"Sentiment {sentiment['label']} ({sentiment.get('score', 0):.2f})")
        return f"Signal {action.upper()}: " + " | ".join(reasons)

    @staticmethod
    async def _fetch_ohlcv(exchange_name: str, symbol: str) -> list:
        """Récupère les données OHLCV via CCXT."""
        if exchange_name == "brvm":
            return await AutonomousTrader._fetch_brvm_data(symbol)
        try:
            exchange_class = getattr(ccxt, exchange_name, None)
            if not exchange_class:
                return []
            exchange = exchange_class({"enableRateLimit": True})
            ohlcv = await exchange.fetch_ohlcv(symbol, "15m", limit=100)
            await exchange.close()
            return ohlcv
        except Exception as e:
            logger.warning(f"OHLCV fetch error {exchange_name}/{symbol}: {e}")
            return []

    @staticmethod
    async def _fetch_brvm_data(symbol: str) -> list:
        """Données simulées BRVM – à connecter à l'API BRVM réelle."""
        import random
        base = 14500.0
        return [
            [i * 900000, base + random.uniform(-100, 100),
             base + random.uniform(0, 200),
             base - random.uniform(0, 200),
             base + random.uniform(-150, 150),
             random.uniform(1000, 5000)]
            for i in range(100)
        ]
