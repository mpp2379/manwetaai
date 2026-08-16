import hashlib
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import psycopg
from psycopg.rows import dict_row


def db_url():
    value = os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is not configured")
    return value


def get_conn():
    return psycopg.connect(db_url(), row_factory=dict_row)


def utcnow():
    return datetime.now(timezone.utc)


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_otp(value: str) -> str:
    # OTPs are low-entropy, so keep them short-lived and attempt-limited.
    return hash_token(value)


def create_user(name=None, email=None, phone_number=None, profile_image=None):
    user_id = uuid.uuid4()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth.users
                    (id, name, email, phone_number, profile_image,
                     email_verified, phone_verified)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    user_id,
                    name,
                    email.lower() if email else None,
                    phone_number,
                    profile_image,
                    bool(email),
                    bool(phone_number),
                ),
            )
            return cur.fetchone()


def get_user_by_id(user_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM auth.users WHERE id = %s", (user_id,))
            return cur.fetchone()


def get_user_by_phone(phone):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM auth.users WHERE phone_number = %s",
                (phone,),
            )
            return cur.fetchone()


def get_user_by_email(email):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM auth.users WHERE LOWER(email) = LOWER(%s)",
                (email,),
            )
            return cur.fetchone()


def get_identity(provider, provider_user_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.*
                FROM auth.auth_identities ai
                JOIN auth.users u ON u.id = ai.user_id
                WHERE ai.provider = %s AND ai.provider_user_id = %s
                """,
                (provider, provider_user_id),
            )
            return cur.fetchone()


def add_identity(user_id, provider, provider_user_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth.auth_identities
                    (id, user_id, provider, provider_user_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (provider, provider_user_id) DO NOTHING
                """,
                (uuid.uuid4(), user_id, provider, provider_user_id),
            )


def update_user_from_google(user_id, name, email, picture):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE auth.users
                SET name = COALESCE(%s, name),
                    email = COALESCE(email, %s),
                    profile_image = COALESCE(%s, profile_image),
                    email_verified = TRUE,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (name, email.lower() if email else None, picture, user_id),
            )


def create_session(user_id, user_agent, ip_address):
    session_id = uuid.uuid4()
    refresh_token = secrets.token_urlsafe(64)
    refresh_hash = hash_token(refresh_token)
    days = int(os.getenv("REFRESH_TOKEN_DAYS", "30"))
    expires_at = utcnow() + timedelta(days=days)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth.sessions
                    (id, user_id, refresh_token_hash, user_agent,
                     ip_address, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    session_id,
                    user_id,
                    refresh_hash,
                    user_agent,
                    ip_address,
                    expires_at,
                ),
            )

    return str(session_id), refresh_token


def create_access_token(user_id, session_id):
    minutes = int(os.getenv("JWT_ACCESS_MINUTES", "15"))
    now = utcnow()
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
        "type": "access",
    }
    return jwt.encode(
        payload,
        os.environ["SECRET_KEY"],
        algorithm="HS256",
    )


def validate_session(session_id, user_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM auth.sessions
                WHERE id = %s AND user_id = %s
                  AND revoked_at IS NULL
                  AND expires_at > NOW()
                """,
                (session_id, user_id),
            )
            row = cur.fetchone()
            if row:
                cur.execute(
                    "UPDATE auth.sessions SET last_used_at = NOW() WHERE id = %s",
                    (session_id,),
                )
            return row


def rotate_refresh_token(session_id, old_refresh_token):
    old_hash = hash_token(old_refresh_token)
    new_refresh_token = secrets.token_urlsafe(64)
    new_hash = hash_token(new_refresh_token)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM auth.sessions
                WHERE id = %s
                  AND refresh_token_hash = %s
                  AND revoked_at IS NULL
                  AND expires_at > NOW()
                FOR UPDATE
                """,
                (session_id, old_hash),
            )
            session = cur.fetchone()
            if not session:
                return None

            cur.execute(
                """
                UPDATE auth.sessions
                SET refresh_token_hash = %s, last_used_at = NOW()
                WHERE id = %s
                """,
                (new_hash, session_id),
            )

    return new_refresh_token


def revoke_session(session_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE auth.sessions SET revoked_at = NOW() WHERE id = %s",
                (session_id,),
            )


def revoke_all_sessions(user_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE auth.sessions SET revoked_at = NOW()
                WHERE user_id = %s AND revoked_at IS NULL
                """,
                (user_id,),
            )


def create_otp(phone_number):
    length = int(os.getenv("OTP_LENGTH", "6"))
    otp = "".join(secrets.choice("0123456789") for _ in range(length))
    expiry_minutes = int(os.getenv("OTP_EXPIRY_MINUTES", "5"))

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Invalidate older unverified OTPs for the same number.
            cur.execute(
                """
                UPDATE auth.otp_verifications
                SET verified_at = NOW()
                WHERE phone_number = %s
                  AND verified_at IS NULL
                """,
                (phone_number,),
            )
            cur.execute(
                """
                INSERT INTO auth.otp_verifications
                    (id, phone_number, otp_hash, purpose, expires_at)
                VALUES (%s, %s, %s, 'login', %s)
                """,
                (
                    uuid.uuid4(),
                    phone_number,
                    hash_otp(otp),
                    utcnow() + timedelta(minutes=expiry_minutes),
                ),
            )
    return otp


def verify_otp(phone_number, otp):
    max_attempts = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM auth.otp_verifications
                WHERE phone_number = %s
                  AND verified_at IS NULL
                  AND expires_at > NOW()
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (phone_number,),
            )
            row = cur.fetchone()
            if not row:
                return False, "OTP expired or not found"

            if row["attempts"] >= max_attempts:
                return False, "Too many OTP attempts"

            cur.execute(
                """
                UPDATE auth.otp_verifications
                SET attempts = attempts + 1
                WHERE id = %s
                """,
                (row["id"],),
            )

            if secrets.compare_digest(row["otp_hash"], hash_otp(otp)):
                cur.execute(
                    """
                    UPDATE auth.otp_verifications
                    SET verified_at = NOW()
                    WHERE id = %s
                    """,
                    (row["id"],),
                )
                return True, "verified"

    return False, "Invalid OTP"