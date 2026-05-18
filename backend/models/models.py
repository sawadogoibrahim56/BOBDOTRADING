"""
BTF – Modèles de Base de Données (SQLAlchemy + Supabase/PostgreSQL)
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Integer, JSON, String, Text, UniqueConstraint, Index,
    Numeric, BigInteger,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.utils.database import Base


def gen_uuid():
    return str(uuid.uuid4())


# ─── ENUMS ────────────────────────────────────────────────────────────────────
class UserStatus(str, PyEnum):
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    SUSPENDED = "suspended"

class OrderSide(str, PyEnum):
    BUY = "buy"
    SELL = "sell"

class OrderType(str, PyEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_LIMIT = "stop_limit"

class OrderStatus(str, PyEnum):
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EMERGENCY_STOPPED = "emergency_stopped"

class TradingMode(str, PyEnum):
    DEMO = "demo"
    REAL = "real"

class PaymentStatus(str, PyEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class MarketType(str, PyEnum):
    CRYPTO = "crypto"
    BRVM = "brvm"
    PHYSICAL = "physical"

class RarityLevel(str, PyEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class AlertType(str, PyEnum):
    ORDER_EXECUTED = "order_executed"
    SUBSCRIPTION_ACTIVATED = "subscription_activated"
    EMERGENCY_STOP = "emergency_stop"
    DRAWDOWN_WARNING = "drawdown_warning"
    AI_SIGNAL = "ai_signal"
    PHYSICAL_ALERT = "physical_alert"


# ─── USERS ────────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email           = Column(String(255), unique=True, nullable=False, index=True)
    phone           = Column(String(20), nullable=True)
    full_name       = Column(String(200), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    country         = Column(String(50), default="BF")          # ISO code

    # Statut & abonnement
    status          = Column(Enum(UserStatus), default=UserStatus.TRIAL)
    trial_ends_at   = Column(DateTime, nullable=True)
    subscription_ends_at = Column(DateTime, nullable=True)
    trading_mode    = Column(Enum(TradingMode), default=TradingMode.DEMO)

    # Sécurité
    totp_secret     = Column(String(100), nullable=True)
    totp_enabled    = Column(Boolean, default=False)
    failed_login_attempts = Column(Integer, default=0)
    locked_until    = Column(DateTime, nullable=True)
    last_login_at   = Column(DateTime, nullable=True)
    last_login_ip   = Column(String(45), nullable=True)

    # Mode autonome
    autonomous_enabled = Column(Boolean, default=False)
    autonomous_authorized_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at      = Column(DateTime, server_default=func.now())
    updated_at      = Column(DateTime, server_default=func.now(), onupdate=func.now())
    is_admin        = Column(Boolean, default=False)
    is_active       = Column(Boolean, default=True)

    # Relations
    api_keys        = relationship("UserApiKey", back_populates="user", cascade="all, delete")
    orders          = relationship("TradeOrder", back_populates="user", cascade="all, delete")
    payments        = relationship("PaymentRequest", back_populates="user", cascade="all, delete")
    alerts          = relationship("UserAlert", back_populates="user", cascade="all, delete")
    portfolio       = relationship("Portfolio", back_populates="user", uselist=False, cascade="all, delete")
    risk_profile    = relationship("RiskProfile", back_populates="user", uselist=False, cascade="all, delete")


# ─── USER API KEYS (Chiffrées) ─────────────────────────────────────────────────
class UserApiKey(Base):
    __tablename__ = "user_api_keys"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id         = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    exchange        = Column(String(50), nullable=False)   # binance, okx, bybit, brvm...
    label           = Column(String(100), nullable=True)
    # Clés chiffrées (AES-256 via Fernet) – jamais en clair
    encrypted_api_key    = Column(Text, nullable=False)
    encrypted_api_secret = Column(Text, nullable=False)
    encrypted_passphrase = Column(Text, nullable=True)    # OKX etc.
    # Permissions (lecture + trading uniquement – JAMAIS retrait)
    permissions     = Column(JSONB, default={"read": True, "trade": True, "withdraw": False})
    is_valid        = Column(Boolean, default=True)
    last_verified_at = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="api_keys")
    __table_args__ = (UniqueConstraint("user_id", "exchange", name="uq_user_exchange"),)


# ─── PORTEFEUILLE ─────────────────────────────────────────────────────────────
class Portfolio(Base):
    __tablename__ = "portfolios"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id         = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    mode            = Column(Enum(TradingMode), default=TradingMode.DEMO)
    # Soldes par devise (JSONB)
    balances        = Column(JSONB, default={"USDT": 2450000, "BTC": 0, "ETH": 0})
    demo_balance_fcfa = Column(Numeric(18, 2), default=2450000.00)
    total_value_usdt  = Column(Numeric(18, 4), default=0)
    total_pnl_today   = Column(Numeric(18, 4), default=0)
    total_pnl_total   = Column(Numeric(18, 4), default=0)
    updated_at        = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="portfolio")


# ─── PROFIL DE RISQUE ─────────────────────────────────────────────────────────
class RiskProfile(Base):
    __tablename__ = "risk_profiles"

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id              = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    max_risk_per_trade   = Column(Float, default=1.0)      # % du capital
    max_daily_drawdown   = Column(Float, default=2.0)      # %
    current_daily_drawdown = Column(Float, default=0.0)    # %
    emergency_stopped    = Column(Boolean, default=False)
    emergency_stop_at    = Column(DateTime, nullable=True)
    emergency_resume_at  = Column(DateTime, nullable=True) # +24h après arrêt
    require_stop_loss    = Column(Boolean, default=True)
    require_take_profit  = Column(Boolean, default=False)
    max_open_trades      = Column(Integer, default=10)
    daily_reset_at       = Column(DateTime, nullable=True)
    updated_at           = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="risk_profile")


# ─── ORDRES DE TRADING ────────────────────────────────────────────────────────
class TradeOrder(Base):
    __tablename__ = "trade_orders"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id         = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    exchange        = Column(String(50), nullable=False)
    market_type     = Column(Enum(MarketType), default=MarketType.CRYPTO)
    symbol          = Column(String(30), nullable=False, index=True)
    side            = Column(Enum(OrderSide), nullable=False)
    order_type      = Column(Enum(OrderType), default=OrderType.MARKET)
    mode            = Column(Enum(TradingMode), default=TradingMode.DEMO)

    # Prix & quantités
    quantity        = Column(Numeric(20, 8), nullable=False)
    price           = Column(Numeric(20, 8), nullable=True)     # None = market
    stop_loss       = Column(Numeric(20, 8), nullable=True)
    take_profit     = Column(Numeric(20, 8), nullable=True)
    filled_price    = Column(Numeric(20, 8), nullable=True)
    filled_at       = Column(DateTime, nullable=True)

    # Gestion du risque
    risk_percent    = Column(Float, nullable=True)
    pnl             = Column(Numeric(20, 8), nullable=True)
    pnl_percent     = Column(Float, nullable=True)

    # Statut
    status          = Column(Enum(OrderStatus), default=OrderStatus.PENDING, index=True)
    exchange_order_id = Column(String(100), nullable=True)    # ID retourné par l'exchange
    is_autonomous   = Column(Boolean, default=False)          # Généré par l'IA
    ai_signal_id    = Column(UUID(as_uuid=True), nullable=True)

    # Méta
    notes           = Column(Text, nullable=True)
    raw_response    = Column(JSONB, nullable=True)
    created_at      = Column(DateTime, server_default=func.now(), index=True)
    updated_at      = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="orders")
    __table_args__ = (
        Index("idx_orders_user_status", "user_id", "status"),
        Index("idx_orders_symbol_created", "symbol", "created_at"),
    )


# ─── DONNÉES DE MARCHÉ ────────────────────────────────────────────────────────
class MarketData(Base):
    __tablename__ = "market_data"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    exchange    = Column(String(50), nullable=False)
    symbol      = Column(String(30), nullable=False, index=True)
    market_type = Column(Enum(MarketType), default=MarketType.CRYPTO)
    open        = Column(Numeric(20, 8))
    high        = Column(Numeric(20, 8))
    low         = Column(Numeric(20, 8))
    close       = Column(Numeric(20, 8))
    volume      = Column(Numeric(30, 8))
    timestamp   = Column(DateTime, nullable=False, index=True)
    timeframe   = Column(String(10), default="1m")

    __table_args__ = (
        Index("idx_market_symbol_ts", "symbol", "timestamp"),
        UniqueConstraint("exchange", "symbol", "timestamp", "timeframe", name="uq_ohlcv"),
    )


# ─── SIGNAUX IA ───────────────────────────────────────────────────────────────
class AISignal(Base):
    __tablename__ = "ai_signals"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol          = Column(String(30), nullable=False, index=True)
    exchange        = Column(String(50))
    market_type     = Column(Enum(MarketType))
    signal          = Column(String(20))             # buy / sell / hold
    confidence      = Column(Float)                  # 0.0 – 1.0
    # Composantes du signal
    technical_score  = Column(Float)
    fundamental_score = Column(Float)
    sentiment_score  = Column(Float)
    physical_score   = Column(Float, nullable=True)
    # Détail
    indicators      = Column(JSONB)                  # RSI, MACD, EMA, BB...
    sentiment_data  = Column(JSONB, nullable=True)
    reasoning       = Column(Text)
    suggested_sl    = Column(Numeric(20, 8), nullable=True)
    suggested_tp    = Column(Numeric(20, 8), nullable=True)
    executed        = Column(Boolean, default=False)
    created_at      = Column(DateTime, server_default=func.now(), index=True)


# ─── MARCHÉ PHYSIQUE ──────────────────────────────────────────────────────────
class PhysicalMarketTrend(Base):
    __tablename__ = "physical_market_trends"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    country         = Column(String(5), nullable=False, index=True)   # BF, CI, SN...
    region          = Column(String(100), nullable=True)
    city            = Column(String(100), nullable=True)
    market_name     = Column(String(200), nullable=True)
    product         = Column(String(200), nullable=False, index=True)
    category        = Column(String(100))                             # céréales, poisson, carburant...
    # Indicateurs
    rarity_score    = Column(Float, nullable=False)                   # 0–10
    rarity_level    = Column(Enum(RarityLevel))
    price_local     = Column(Numeric(12, 2), nullable=True)
    price_currency  = Column(String(5), default="XOF")
    supply_status   = Column(String(50))                              # surplus, normal, pénurie
    demand_level    = Column(String(50))
    logistics_axis  = Column(String(200), nullable=True)             # ex: Abidjan→Ouagadougou
    # Source
    source_type     = Column(String(50))                              # web, press, social, field
    source_url      = Column(Text, nullable=True)
    raw_data        = Column(JSONB, nullable=True)
    # Rapport admin
    report_generated = Column(Boolean, default=False)
    report_validated = Column(Boolean, default=False)
    validated_by    = Column(UUID(as_uuid=True), nullable=True)
    validated_at    = Column(DateTime, nullable=True)
    published       = Column(Boolean, default=False)
    notes           = Column(Text, nullable=True)

    created_at      = Column(DateTime, server_default=func.now(), index=True)
    updated_at      = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_phys_country_product", "country", "product"),
    )


# ─── PAIEMENTS ────────────────────────────────────────────────────────────────
class PaymentRequest(Base):
    __tablename__ = "payment_requests"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id         = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount_fcfa     = Column(Numeric(10, 2), nullable=False, default=5000.00)
    payment_method  = Column(String(50), nullable=False)    # orange_money, wave, moov_money
    # Numéro de destination en .env – jamais stocké ici
    sender_phone    = Column(String(20), nullable=False)
    transaction_ref = Column(String(100), nullable=True)    # référence du virement
    proof_image_url = Column(Text, nullable=True)           # URL Supabase Storage
    status          = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, index=True)
    admin_note      = Column(Text, nullable=True)
    reviewed_by     = Column(UUID(as_uuid=True), nullable=True)
    reviewed_at     = Column(DateTime, nullable=True)
    period_months   = Column(Integer, default=1)
    created_at      = Column(DateTime, server_default=func.now(), index=True)
    updated_at      = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="payments")


# ─── ALERTES / NOTIFICATIONS ──────────────────────────────────────────────────
class UserAlert(Base):
    __tablename__ = "user_alerts"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    alert_type  = Column(Enum(AlertType), nullable=False)
    title       = Column(String(200), nullable=False)
    message     = Column(Text, nullable=False)
    data        = Column(JSONB, nullable=True)
    is_read     = Column(Boolean, default=False)
    sent_push   = Column(Boolean, default=False)
    sent_email  = Column(Boolean, default=False)
    created_at  = Column(DateTime, server_default=func.now(), index=True)

    user = relationship("User", back_populates="alerts")


# ─── LOGS SYSTÈME (IMMUABLES) ─────────────────────────────────────────────────
class SystemLog(Base):
    __tablename__ = "system_logs"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id     = Column(UUID(as_uuid=True), nullable=True, index=True)
    action      = Column(String(200), nullable=False)
    module      = Column(String(50), nullable=False)          # auth, trading, admin, risk...
    ip_address  = Column(String(45), nullable=True)
    user_agent  = Column(Text, nullable=True)
    data        = Column(JSONB, nullable=True)
    severity    = Column(String(20), default="info")          # info, warning, critical
    created_at  = Column(DateTime, server_default=func.now(), index=True)
    # Les logs ne sont JAMAIS supprimés ni modifiés
    __table_args__ = (Index("idx_logs_user_created", "user_id", "created_at"),)


# ─── SESSIONS ADMIN ───────────────────────────────────────────────────────────
class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    ip_address  = Column(String(45))
    user_agent  = Column(Text)
    totp_verified = Column(Boolean, default=False)
    is_active   = Column(Boolean, default=True)
    expires_at  = Column(DateTime, nullable=False)
    created_at  = Column(DateTime, server_default=func.now())
    revoked_at  = Column(DateTime, nullable=True)
