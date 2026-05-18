-- ═══════════════════════════════════════════════════════════════════════════
-- BTF – Bobdo Trading and Finance
-- Schéma PostgreSQL Complet v1.3
-- Compatible Supabase
-- ═══════════════════════════════════════════════════════════════════════════

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── ENUMS ───────────────────────────────────────────────────────────────────
CREATE TYPE user_status     AS ENUM ('trial', 'active', 'expired', 'suspended');
CREATE TYPE order_side      AS ENUM ('buy', 'sell');
CREATE TYPE order_type      AS ENUM ('market', 'limit', 'stop_limit');
CREATE TYPE order_status    AS ENUM ('pending', 'open', 'filled', 'cancelled', 'rejected', 'emergency_stopped');
CREATE TYPE trading_mode    AS ENUM ('demo', 'real');
CREATE TYPE payment_status  AS ENUM ('pending', 'approved', 'rejected');
CREATE TYPE market_type     AS ENUM ('crypto', 'brvm', 'physical');
CREATE TYPE rarity_level    AS ENUM ('low', 'medium', 'high', 'critical');
CREATE TYPE alert_type      AS ENUM ('order_executed','subscription_activated','emergency_stop','drawdown_warning','ai_signal','physical_alert');

-- ─── USERS ───────────────────────────────────────────────────────────────────
CREATE TABLE users (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email                   VARCHAR(255) UNIQUE NOT NULL,
    phone                   VARCHAR(20),
    full_name               VARCHAR(200) NOT NULL,
    hashed_password         VARCHAR(255) NOT NULL,
    country                 VARCHAR(5) DEFAULT 'BF',

    -- Statut & abonnement
    status                  user_status DEFAULT 'trial',
    trial_ends_at           TIMESTAMPTZ,
    subscription_ends_at    TIMESTAMPTZ,
    trading_mode            trading_mode DEFAULT 'demo',

    -- Sécurité
    totp_secret             VARCHAR(100),
    totp_enabled            BOOLEAN DEFAULT FALSE,
    failed_login_attempts   INT DEFAULT 0,
    locked_until            TIMESTAMPTZ,
    last_login_at           TIMESTAMPTZ,
    last_login_ip           VARCHAR(45),

    -- Mode autonome
    autonomous_enabled          BOOLEAN DEFAULT FALSE,
    autonomous_authorized_at    TIMESTAMPTZ,

    -- Flags
    is_admin    BOOLEAN DEFAULT FALSE,
    is_active   BOOLEAN DEFAULT TRUE,

    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_email  ON users(email);
CREATE INDEX idx_users_status ON users(status);

-- ─── USER API KEYS (Chiffrées AES-256) ───────────────────────────────────────
CREATE TABLE user_api_keys (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exchange            VARCHAR(50) NOT NULL,
    label               VARCHAR(100),
    encrypted_api_key   TEXT NOT NULL,     -- Chiffré Fernet
    encrypted_api_secret TEXT NOT NULL,   -- Chiffré Fernet
    encrypted_passphrase TEXT,            -- OKX, etc.
    permissions         JSONB DEFAULT '{"read": true, "trade": true, "withdraw": false}',
    is_valid            BOOLEAN DEFAULT TRUE,
    last_verified_at    TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, exchange)
);

-- ─── PORTFOLIOS ───────────────────────────────────────────────────────────────
CREATE TABLE portfolios (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mode                trading_mode DEFAULT 'demo',
    balances            JSONB DEFAULT '{"USDT": 2450000}',
    demo_balance_fcfa   NUMERIC(18, 2) DEFAULT 2450000.00,
    total_value_usdt    NUMERIC(18, 4) DEFAULT 0,
    total_pnl_today     NUMERIC(18, 4) DEFAULT 0,
    total_pnl_total     NUMERIC(18, 4) DEFAULT 0,
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ─── RISK PROFILES ────────────────────────────────────────────────────────────
CREATE TABLE risk_profiles (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id                 UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    max_risk_per_trade      FLOAT DEFAULT 1.0,
    max_daily_drawdown      FLOAT DEFAULT 2.0,
    current_daily_drawdown  FLOAT DEFAULT 0.0,
    emergency_stopped       BOOLEAN DEFAULT FALSE,
    emergency_stop_at       TIMESTAMPTZ,
    emergency_resume_at     TIMESTAMPTZ,
    require_stop_loss       BOOLEAN DEFAULT TRUE,
    require_take_profit     BOOLEAN DEFAULT FALSE,
    max_open_trades         INT DEFAULT 10,
    daily_reset_at          TIMESTAMPTZ,
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

-- ─── TRADE ORDERS ─────────────────────────────────────────────────────────────
CREATE TABLE trade_orders (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exchange            VARCHAR(50) NOT NULL,
    market_type         market_type DEFAULT 'crypto',
    symbol              VARCHAR(30) NOT NULL,
    side                order_side NOT NULL,
    order_type          order_type DEFAULT 'market',
    mode                trading_mode DEFAULT 'demo',

    -- Prix & quantités
    quantity            NUMERIC(20, 8) NOT NULL,
    price               NUMERIC(20, 8),
    stop_loss           NUMERIC(20, 8),
    take_profit         NUMERIC(20, 8),
    filled_price        NUMERIC(20, 8),
    filled_at           TIMESTAMPTZ,

    -- Risque & P&L
    risk_percent        FLOAT,
    pnl                 NUMERIC(20, 8),
    pnl_percent         FLOAT,

    -- Statut & méta
    status              order_status DEFAULT 'pending',
    exchange_order_id   VARCHAR(100),
    is_autonomous       BOOLEAN DEFAULT FALSE,
    ai_signal_id        UUID,
    notes               TEXT,
    raw_response        JSONB,

    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_orders_user_status        ON trade_orders(user_id, status);
CREATE INDEX idx_orders_symbol_created     ON trade_orders(symbol, created_at DESC);
CREATE INDEX idx_orders_created            ON trade_orders(created_at DESC);

-- ─── MARKET DATA (OHLCV) ──────────────────────────────────────────────────────
CREATE TABLE market_data (
    id          BIGSERIAL PRIMARY KEY,
    exchange    VARCHAR(50) NOT NULL,
    symbol      VARCHAR(30) NOT NULL,
    market_type market_type DEFAULT 'crypto',
    open        NUMERIC(20, 8),
    high        NUMERIC(20, 8),
    low         NUMERIC(20, 8),
    close       NUMERIC(20, 8),
    volume      NUMERIC(30, 8),
    timestamp   TIMESTAMPTZ NOT NULL,
    timeframe   VARCHAR(10) DEFAULT '1m',
    UNIQUE(exchange, symbol, timestamp, timeframe)
);

CREATE INDEX idx_market_symbol_ts ON market_data(symbol, timestamp DESC);

-- ─── AI SIGNALS ───────────────────────────────────────────────────────────────
CREATE TABLE ai_signals (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol              VARCHAR(30) NOT NULL,
    exchange            VARCHAR(50),
    market_type         market_type,
    signal              VARCHAR(20),        -- buy / sell / hold
    confidence          FLOAT,             -- 0.0 à 1.0
    technical_score     FLOAT,
    fundamental_score   FLOAT,
    sentiment_score     FLOAT,
    physical_score      FLOAT,
    indicators          JSONB,
    sentiment_data      JSONB,
    reasoning           TEXT,
    suggested_sl        NUMERIC(20, 8),
    suggested_tp        NUMERIC(20, 8),
    executed            BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_signals_symbol ON ai_signals(symbol, created_at DESC);

-- ─── PHYSICAL MARKET TRENDS ───────────────────────────────────────────────────
CREATE TABLE physical_market_trends (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    country         VARCHAR(5) NOT NULL,
    region          VARCHAR(100),
    city            VARCHAR(100),
    market_name     VARCHAR(200),
    product         VARCHAR(200) NOT NULL,
    category        VARCHAR(100),
    rarity_score    FLOAT NOT NULL,
    rarity_level    rarity_level,
    price_local     NUMERIC(12, 2),
    price_currency  VARCHAR(5) DEFAULT 'XOF',
    supply_status   VARCHAR(50),
    demand_level    VARCHAR(50),
    logistics_axis  VARCHAR(200),
    source_type     VARCHAR(50),
    source_url      TEXT,
    raw_data        JSONB,

    -- Workflow rapport admin
    report_generated    BOOLEAN DEFAULT FALSE,
    report_validated    BOOLEAN DEFAULT FALSE,
    validated_by        UUID,
    validated_at        TIMESTAMPTZ,
    published           BOOLEAN DEFAULT FALSE,
    notes               TEXT,

    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_phys_country_product  ON physical_market_trends(country, product);
CREATE INDEX idx_phys_rarity           ON physical_market_trends(rarity_score DESC);

-- ─── PAYMENT REQUESTS ────────────────────────────────────────────────────────
CREATE TABLE payment_requests (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount_fcfa     NUMERIC(10, 2) NOT NULL DEFAULT 5000.00,
    payment_method  VARCHAR(50) NOT NULL,
    -- Numéro de destination JAMAIS stocké ici (il est dans .env)
    sender_phone    VARCHAR(20) NOT NULL,
    transaction_ref VARCHAR(100),
    proof_image_url TEXT,                  -- URL Supabase Storage
    status          payment_status DEFAULT 'pending',
    admin_note      TEXT,
    reviewed_by     UUID,
    reviewed_at     TIMESTAMPTZ,
    period_months   INT DEFAULT 1,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_payments_user    ON payment_requests(user_id);
CREATE INDEX idx_payments_status  ON payment_requests(status);

-- ─── USER ALERTS ─────────────────────────────────────────────────────────────
CREATE TABLE user_alerts (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    alert_type  alert_type NOT NULL,
    title       VARCHAR(200) NOT NULL,
    message     TEXT NOT NULL,
    data        JSONB,
    is_read     BOOLEAN DEFAULT FALSE,
    sent_push   BOOLEAN DEFAULT FALSE,
    sent_email  BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_alerts_user_unread ON user_alerts(user_id, is_read, created_at DESC);

-- ─── SYSTEM LOGS (IMMUABLES) ──────────────────────────────────────────────────
CREATE TABLE system_logs (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID,
    action      VARCHAR(200) NOT NULL,
    module      VARCHAR(50) NOT NULL,
    ip_address  VARCHAR(45),
    user_agent  TEXT,
    data        JSONB,
    severity    VARCHAR(20) DEFAULT 'info',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Les logs ne sont jamais modifiés ni supprimés
REVOKE UPDATE, DELETE ON system_logs FROM PUBLIC;
CREATE INDEX idx_logs_user_created ON system_logs(user_id, created_at DESC);
CREATE INDEX idx_logs_severity     ON system_logs(severity, created_at DESC);

-- ─── ADMIN SESSIONS ───────────────────────────────────────────────────────────
CREATE TABLE admin_sessions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ip_address      VARCHAR(45),
    user_agent      TEXT,
    totp_verified   BOOLEAN DEFAULT FALSE,
    is_active       BOOLEAN DEFAULT TRUE,
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    revoked_at      TIMESTAMPTZ
);

-- ─── FONCTION DE MISE À JOUR AUTO updated_at ─────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated          BEFORE UPDATE ON users               FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_portfolios_updated     BEFORE UPDATE ON portfolios           FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_risk_updated           BEFORE UPDATE ON risk_profiles        FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_orders_updated         BEFORE UPDATE ON trade_orders         FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_physical_updated       BEFORE UPDATE ON physical_market_trends FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_payments_updated       BEFORE UPDATE ON payment_requests     FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─── ROW LEVEL SECURITY (Supabase) ───────────────────────────────────────────
ALTER TABLE users               ENABLE ROW LEVEL SECURITY;
ALTER TABLE trade_orders        ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolios          ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_requests    ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_alerts         ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_api_keys       ENABLE ROW LEVEL SECURITY;

-- Politique : chaque utilisateur ne voit que ses propres données
CREATE POLICY "own_data" ON users            USING (id = auth.uid()::UUID);
CREATE POLICY "own_data" ON trade_orders     USING (user_id = auth.uid()::UUID);
CREATE POLICY "own_data" ON portfolios       USING (user_id = auth.uid()::UUID);
CREATE POLICY "own_data" ON payment_requests USING (user_id = auth.uid()::UUID);
CREATE POLICY "own_data" ON user_alerts      USING (user_id = auth.uid()::UUID);
CREATE POLICY "own_data" ON user_api_keys    USING (user_id = auth.uid()::UUID);

-- ─── DONNÉES INITIALES ────────────────────────────────────────────────────────
-- Admin par défaut (mot de passe à changer immédiatement !)
INSERT INTO users (email, full_name, hashed_password, is_admin, status, totp_enabled)
VALUES (
    'admin@btf.bf',
    'Administrateur BTF',
    '$2b$12$placeholder_change_immediately',   -- bcrypt hash – CHANGER
    TRUE,
    'active',
    FALSE
) ON CONFLICT DO NOTHING;
