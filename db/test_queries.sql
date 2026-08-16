-- Authentication verification queries.
-- Run these after using the UI.

SELECT id, name, email, phone_number, phone_verified, email_verified,
       is_active, created_at
FROM users
ORDER BY created_at DESC;

SELECT ai.id, ai.user_id, ai.provider, ai.provider_user_id, ai.created_at
FROM auth_identities ai
ORDER BY ai.created_at DESC;

SELECT id, user_id, created_at, last_used_at, expires_at, revoked_at,
       user_agent, ip_address
FROM sessions
ORDER BY created_at DESC;

SELECT id, phone_number, purpose, expires_at, attempts, verified_at, created_at
FROM otp_verifications
ORDER BY created_at DESC;

-- Active sessions for a user:
-- SELECT * FROM sessions
-- WHERE user_id = '<USER_UUID>'
--   AND revoked_at IS NULL
--   AND expires_at > NOW();

-- Revoke every session for one user:
-- UPDATE sessions
-- SET revoked_at = NOW()
-- WHERE user_id = '<USER_UUID>' AND revoked_at IS NULL;
