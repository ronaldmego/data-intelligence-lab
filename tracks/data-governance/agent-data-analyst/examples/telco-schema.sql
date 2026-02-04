-- Khipu Demo: Telco Prepago Schema
-- Simplified schema for testing analytics queries

-- Customers (base de clientes)
CREATE TABLE IF NOT EXISTS customers (
    customer_id VARCHAR(20) PRIMARY KEY,
    phone_number VARCHAR(15) NOT NULL,
    segment VARCHAR(20) DEFAULT 'prepago',  -- prepago, postpago
    customer_type VARCHAR(10) DEFAULT 'B2C', -- B2C, B2B
    registration_date DATE NOT NULL,
    status VARCHAR(20) DEFAULT 'active',     -- active, inactive, churned
    city VARCHAR(100),
    age_range VARCHAR(20),                   -- 18-25, 26-35, 36-45, 46+
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Recharges (recargas prepago)
CREATE TABLE IF NOT EXISTS recharges (
    recharge_id SERIAL PRIMARY KEY,
    customer_id VARCHAR(20) REFERENCES customers(customer_id),
    amount DECIMAL(10,2) NOT NULL,
    channel VARCHAR(50),                     -- app, web, agente, banco
    promotion_code VARCHAR(50),
    recharge_date TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Usage (consumo de datos/voz/sms)
CREATE TABLE IF NOT EXISTS usage_daily (
    id SERIAL PRIMARY KEY,
    customer_id VARCHAR(20) REFERENCES customers(customer_id),
    usage_date DATE NOT NULL,
    data_mb DECIMAL(10,2) DEFAULT 0,
    voice_minutes INT DEFAULT 0,
    sms_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(customer_id, usage_date)
);

-- Campaigns (promociones enviadas)
CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(50),                        -- retention, upsell, win-back
    start_date DATE,
    end_date DATE,
    target_segment VARCHAR(50),
    discount_percent INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Campaign Responses
CREATE TABLE IF NOT EXISTS campaign_responses (
    id SERIAL PRIMARY KEY,
    campaign_id INT REFERENCES campaigns(campaign_id),
    customer_id VARCHAR(20) REFERENCES customers(customer_id),
    sent_at TIMESTAMP,
    opened_at TIMESTAMP,
    converted_at TIMESTAMP,
    conversion_amount DECIMAL(10,2)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_customers_segment ON customers(segment);
CREATE INDEX IF NOT EXISTS idx_customers_status ON customers(status);
CREATE INDEX IF NOT EXISTS idx_recharges_customer ON recharges(customer_id);
CREATE INDEX IF NOT EXISTS idx_recharges_date ON recharges(recharge_date);
CREATE INDEX IF NOT EXISTS idx_usage_customer ON usage_daily(customer_id);
CREATE INDEX IF NOT EXISTS idx_usage_date ON usage_daily(usage_date);

-- Comments for OpenMetadata glossary integration
COMMENT ON TABLE customers IS 'Base de clientes de telefonía móvil';
COMMENT ON COLUMN customers.segment IS 'Tipo de plan: prepago (sin contrato) o postpago (con contrato mensual)';
COMMENT ON COLUMN customers.status IS 'Estado del cliente: active (activo), inactive (sin actividad 15+ días), churned (sin actividad 30+ días)';

COMMENT ON TABLE recharges IS 'Transacciones de recarga para clientes prepago';
COMMENT ON COLUMN recharges.amount IS 'Monto de la recarga en USD';
COMMENT ON COLUMN recharges.channel IS 'Canal de recarga: app móvil, web, agente autorizado, banco';

COMMENT ON TABLE usage_daily IS 'Consumo diario agregado por cliente';
COMMENT ON COLUMN usage_daily.data_mb IS 'Consumo de datos en megabytes';
COMMENT ON COLUMN usage_daily.voice_minutes IS 'Minutos de llamadas de voz';

COMMENT ON TABLE campaigns IS 'Campañas de marketing y promociones';
COMMENT ON COLUMN campaigns.type IS 'Tipo de campaña: retention (evitar churn), upsell (aumentar consumo), win-back (recuperar churned)';
