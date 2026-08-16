import os
import re
import secrets
from functools import wraps

import jwt
import requests
from flask import Blueprint, jsonify, redirect, request, url_for, render_template, make_response
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from auth.service import (
    add_identity,
    create_access_token,
    create_otp,
    create_session,
    create_user,
    get_identity,
    get_user_by_email,
    get_user_by_id,
    get_user_by_phone,
    revoke_all_sessions,
    revoke_session,
    rotate_refresh_token,
    validate_session,
    verify_otp,
)

auth_bp = Blueprint("auth", __name__)

OTP_COOLDOWN = int(os.getenv("OTP_RESEND_SECONDS", "60"))
E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone(phone):
    value = (phone or "").strip().replace(" ", "").replace("-", "")
    return value


def set_auth_cookies(response, access_token, refresh_token):
    secure = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    samesite = os.getenv("COOKIE_SAMESITE", "Lax")
    response.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        secure=secure,
        samesite=samesite,
        max_age=int(os.getenv("JWT_ACCESS_MINUTES", "15")) * 60,
        path="/",
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        secure=secure,
        samesite=samesite,
        max_age=int(os.getenv("REFRESH_TOKEN_DAYS", "30")) * 86400,
        path="/auth",
    )


def clear_auth_cookies(response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/auth")


def issue_session_response(user, session_id, refresh_token, status=200):
    access_token = create_access_token(user["id"], session_id)
    response = make_response(
        jsonify(
            {
                "message": "Authentication successful",
                "user": public_user(user),
                "session_id": session_id,
            }
        ),
        status,
    )
    set_auth_cookies(response, access_token, refresh_token)
    return response


def public_user(user):
    return {
        "id": str(user["id"]),
        "name": user.get("name"),
        "email": user.get("email"),
        "phone_number": user.get("phone_number"),
        "profile_image": user.get("profile_image"),
        "phone_verified": user.get("phone_verified", False),
        "email_verified": user.get("email_verified", False),
    }


def get_bearer_token():
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get("access_token")


def current_identity():
    token = get_bearer_token()
    if not token:
        return None

    try:
        payload = jwt.decode(
            token,
            os.environ["SECRET_KEY"],
            algorithms=["HS256"],
            options={"require": ["sub", "sid", "exp", "iat"]},
        )
        if payload.get("type") != "access":
            return None
        user_id = payload["sub"]
        session_id = payload["sid"]
        if not validate_session(session_id, user_id):
            return None
        user = get_user_by_id(user_id)
        if not user or not user["is_active"]:
            return None
        return user, session_id
    except (jwt.InvalidTokenError, ValueError, TypeError):
        return None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        identity = current_identity()
        if not identity:
            if request.path.startswith("/api/") or request.path in ("/status",):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("auth.login_page"))
        return view(*args, **kwargs)
    return wrapped


def send_sms(phone_number, otp):
    # Development mode lets you test the complete UI without an SMS vendor.
    if os.getenv("DEV_OTP_MODE", "true").lower() == "true":
        print(f"[DEV OTP] {phone_number}: {otp}", flush=True)
        return {"dev_otp": otp}

    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    service = os.getenv("TWILIO_VERIFY_SERVICE_SID")
    if not all([sid, token, service]):
        raise RuntimeError(
            "Twilio Verify is not configured. Set TWILIO_ACCOUNT_SID, "
            "TWILIO_AUTH_TOKEN and TWILIO_VERIFY_SERVICE_SID."
        )

    response = requests.post(
        f"https://verify.twilio.com/v2/Services/{service}/Verifications",
        auth=(sid, token),
        data={"To": phone_number, "Channel": "sms"},
        timeout=20,
    )
    response.raise_for_status()
    return {"status": response.json().get("status")}


@auth_bp.get("/login")
def login_page():
    return render_template("login.html")


@auth_bp.post("/auth/send-otp")
def send_otp():
    data = request.get_json(silent=True) or request.form
    phone = normalize_phone(data.get("phone"))
    if not E164_RE.match(phone):
        return jsonify({"error": "Enter a valid phone number in E.164 format, e.g. +919876543210"}), 400

    otp = create_otp(phone)
    result = send_sms(phone, otp)
    payload = {"message": "OTP sent"}
    if os.getenv("DEV_OTP_MODE", "true").lower() == "true":
        payload["dev_otp"] = result["dev_otp"]
    return jsonify(payload)


@auth_bp.post("/auth/verify-otp")
def verify_otp_route():
    data = request.get_json(silent=True) or request.form
    phone = normalize_phone(data.get("phone"))
    otp = (data.get("otp") or "").strip()

    if not E164_RE.match(phone) or not otp.isdigit():
        return jsonify({"error": "Invalid phone number or OTP"}), 400

    ok, message = verify_otp(phone, otp)
    if not ok:
        return jsonify({"error": message}), 401

    user = get_user_by_phone(phone)
    if not user:
        user = create_user(phone_number=phone)

    if not user["phone_verified"]:
        # create_user sets it true; existing unverified accounts are upgraded here.
        from auth.service import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET phone_verified = TRUE, updated_at = NOW() WHERE id = %s",
                    (user["id"],),
                )
        user = get_user_by_id(user["id"])

    session_id, refresh_token = create_session(
        user["id"],
        request.headers.get("User-Agent"),
        request.remote_addr,
    )
    return issue_session_response(user, session_id, refresh_token)


@auth_bp.get("/auth/google")
def google_login():
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        return jsonify({
            "error": "Google OAuth is not configured",
            "configure": ".env GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET"
        }), 503

    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI") or url_for(
        "auth.google_callback", _external=True
    )
    scope = "openid email profile"
    state = secrets.token_urlsafe(32)
    # State is kept in a short-lived cookie for CSRF protection.
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={client_id}"
        "&response_type=code"
        f"&redirect_uri={requests.utils.quote(redirect_uri, safe='')}"
        f"&scope={requests.utils.quote(scope, safe='')}"
        "&access_type=offline"
        "&prompt=select_account"
        f"&state={state}"
    )
    response = make_response(redirect(auth_url))
    response.set_cookie(
        "oauth_state", state, httponly=True, secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        samesite=os.getenv("COOKIE_SAMESITE", "Lax"), max_age=600, path="/"
    )
    return response


@auth_bp.get("/auth/google/callback")
def google_callback():
    error = request.args.get("error")
    if error:
        return redirect(url_for("auth.login_page", error=error))

    state = request.args.get("state")
    if not state or state != request.cookies.get("oauth_state"):
        return jsonify({"error": "Invalid OAuth state"}), 400

    code = request.args.get("code")
    if not code:
        return jsonify({"error": "Missing Google authorization code"}), 400

    client_id = os.environ["GOOGLE_CLIENT_ID"]
    client_secret = os.environ["GOOGLE_CLIENT_SECRET"]
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI") or url_for(
        "auth.google_callback", _external=True
    )

    token_response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    token_response.raise_for_status()
    tokens = token_response.json()

    info = id_token.verify_oauth2_token(
        tokens["id_token"],
        google_requests.Request(),
        client_id,
    )

    google_sub = info["sub"]
    email = info.get("email")
    name = info.get("name")
    picture = info.get("picture")

    user = get_identity("google", google_sub)
    if not user and email:
        user = get_user_by_email(email)

    if not user:
        user = create_user(name=name, email=email, profile_image=picture)

    add_identity(user["id"], "google", google_sub)

    if email:
        from auth.service import update_user_from_google
        update_user_from_google(user["id"], name, email, picture)
        user = get_user_by_id(user["id"])

    session_id, refresh_token = create_session(
        user["id"],
        request.headers.get("User-Agent"),
        request.remote_addr,
    )
    access_token = create_access_token(user["id"], session_id)
    response = make_response(redirect(url_for("index")))
    set_auth_cookies(response, access_token, refresh_token)
    response.delete_cookie("oauth_state", path="/")
    return response


@auth_bp.post("/auth/refresh")
def refresh():
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        return jsonify({"error": "Refresh token missing"}), 401

    # Session ID is not trusted from the client; it is bound to the signed access
    # token while it is valid. For an expired access token, we need the sid claim
    # without accepting any unsigned user identity data.
    try:
        payload = jwt.decode(
            request.cookies.get("access_token", ""),
            os.environ["SECRET_KEY"],
            algorithms=["HS256"],
            options={"verify_exp": False, "require": ["sub", "sid", "iat"]},
        )
        session_id = payload["sid"]
        user_id = payload["sub"]
    except jwt.InvalidTokenError:
        return jsonify({"error": "Refresh requires the previous access token cookie"}), 401

    new_refresh = rotate_refresh_token(session_id, refresh_token)
    if not new_refresh:
        response = make_response(jsonify({"error": "Invalid or revoked refresh token"}), 401)
        clear_auth_cookies(response)
        return response

    user = get_user_by_id(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 401

    new_access = create_access_token(user["id"], session_id)
    response = make_response(jsonify({"message": "Token refreshed", "user": public_user(user)}))
    set_auth_cookies(response, new_access, new_refresh)
    return response


@auth_bp.post("/auth/logout")
def logout():
    identity = current_identity()
    response = make_response(jsonify({"message": "Logged out"}))
    if identity:
        _, session_id = identity
        revoke_session(session_id)
    clear_auth_cookies(response)
    return response


@auth_bp.post("/auth/logout-all")
@login_required
def logout_all():
    user, _ = current_identity()
    revoke_all_sessions(user["id"])
    response = make_response(jsonify({"message": "All sessions revoked"}))
    clear_auth_cookies(response)
    return response


@auth_bp.get("/auth/me")
def me():
    identity = current_identity()
    if not identity:
        return jsonify({"authenticated": False}), 401
    user, session_id = identity
    return jsonify({"authenticated": True, "user": public_user(user), "session_id": session_id})
