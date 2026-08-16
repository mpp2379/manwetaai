-- PostgreSQL schema for Addition App authentication.
-- Start from an empty database and run this file once.

CREATE SCHEMA IF NOT EXISTS auth;

CREATE TABLE IF NOT EXISTS auth.users (
    id UUID PRIMARY KEY,
    name VARCHAR(150),
    email VARCHAR(320),
    phone_number VARCHAR(32),
    profile_image TEXT,
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    phone_verified BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_ci
    ON auth.users (LOWER(email))
    WHERE email IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_phone
    ON auth.users (phone_number)
    WHERE phone_number IS NOT NULL;

CREATE TABLE IF NOT EXISTS auth.auth_identities (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    provider VARCHAR(30) NOT NULL,
    provider_user_id VARCHAR(512) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(provider, provider_user_id)
);

CREATE INDEX IF NOT EXISTS idx_auth_identities_user_id
    ON auth.auth_identities(user_id);

CREATE TABLE IF NOT EXISTS auth.sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    refresh_token_hash VARCHAR(128) NOT NULL,
    user_agent TEXT,
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id
    ON auth.sessions(user_id);

CREATE INDEX IF NOT EXISTS idx_sessions_active
    ON auth.sessions(user_id, revoked_at, expires_at);

CREATE TABLE IF NOT EXISTS auth.otp_verifications (
    id UUID PRIMARY KEY,
    phone_number VARCHAR(32) NOT NULL,
    otp_hash VARCHAR(128) NOT NULL,
    purpose VARCHAR(30) NOT NULL DEFAULT 'login',
    expires_at TIMESTAMPTZ NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_otp_phone_created
    ON auth.otp_verifications(phone_number, created_at DESC);

-- Optional cleanup query:
-- DELETE FROM auth.otp_verifications
-- WHERE expires_at < NOW() - INTERVAL '1 day';
