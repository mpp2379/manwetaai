# Authentication setup — start from zero

## 1. Create an empty PostgreSQL database

Using `psql`:

```sql
CREATE DATABASE addition_app;
```

Then connect to `addition_app` and run:

```bash
psql -U postgres -d addition_app -f db/schema.sql
```

Or paste the complete contents of `db/schema.sql` into pgAdmin Query Tool and execute.

## 2. Create environment file

Copy `.env.example` to `.env`.

For the first local test, use:

```text
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/addition_app
SECRET_KEY=replace-with-a-long-random-secret
DEV_OTP_MODE=true
COOKIE_SECURE=false
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://127.0.0.1:5555/auth/google/callback
```

Keep your existing RunPod values in `.env`.

## 3. Install dependencies

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 4. Start Flask

```bash
python app.py
```

Open:

```text
http://127.0.0.1:5555/login
```

## 5. Test mobile OTP

Because `DEV_OTP_MODE=true`, enter a test number such as:

```text
+919876543210
```

Click **Send OTP**.

The UI displays the development OTP.

Enter it and click **Verify & Continue**.

A user and session will be created.

Check PostgreSQL:

```sql
SELECT id, name, email, phone_number, phone_verified, created_at
FROM users;

SELECT id, user_id, provider, provider_user_id
FROM auth_identities;

SELECT id, user_id, expires_at, revoked_at, last_used_at
FROM sessions;
```

## 6. Test logout

Click Logout.

Then:

```sql
SELECT id, revoked_at
FROM sessions
ORDER BY created_at DESC;
```

The current session should have a non-null `revoked_at`.

Trying to open `/` after logout should send you back to `/login`.

## 7. Configure Google OAuth

In Google Cloud Console, create an OAuth 2.0 Client ID for a Web application.

For local development add this authorized redirect URI:

```text
http://127.0.0.1:5555/auth/google/callback
```

Set:

```text
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://127.0.0.1:5555/auth/google/callback
```

Restart Flask.

Click **Continue with Google**.

After Google authentication, the app creates/links the user, creates a session, sets the JWT/refresh cookies, and redirects to `/`.

## 8. Production OTP

Do not expose OTPs in the UI in production.

Set:

```text
DEV_OTP_MODE=false
```

Configure Twilio Verify:

```text
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_VERIFY_SERVICE_SID=...
```

The current implementation sends the SMS through Twilio Verify when development mode is disabled.

## 9. Authentication endpoints

```text
GET  /login
POST /auth/send-otp
POST /auth/verify-otp
GET  /auth/google
GET  /auth/google/callback
POST /auth/refresh
POST /auth/logout
POST /auth/logout-all
GET  /auth/me
```

The existing video generation endpoints `/` and `/status` now require authentication.

## 10. Important production settings

Use a strong random `SECRET_KEY`.

For HTTPS:

```text
COOKIE_SECURE=true
COOKIE_SAMESITE=Lax
```

Put the application behind HTTPS and do not commit `.env`.

The refresh token is stored only as a hash in PostgreSQL. The access JWT contains only the user ID, session ID, issue time, expiry and token type.

