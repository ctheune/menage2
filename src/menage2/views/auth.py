import base64
import hmac
import secrets
import smtplib
import json
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from pyramid.security import NO_PERMISSION_REQUIRED
from pyramid.httpexceptions import HTTPSeeOther, HTTPForbidden
from pyramid.view import view_config, forbidden_view_config

from ..models.user import User, Passkey
from ..models.config import ConfigItem
from .. import SETUP_TOKEN_KEY

_ph = PasswordHasher()

DASHBOARD_TOKEN_KEY = "dashboard_secret_token"


def _now():
    return datetime.now(timezone.utc)


def _get_next_url(request):
    came_from = request.params.get("came_from", "")
    if came_from and came_from.startswith("/"):
        return came_from
    return request.route_url("list_todos")


# ---------------------------------------------------------------------------
# Forbidden view
# ---------------------------------------------------------------------------

@forbidden_view_config()
def forbidden_view(request):
    if request.identity is not None:
        return HTTPForbidden("You do not have permission to access this page.")
    if request.headers.get("HX-Request"):
        response = request.response
        response.status_int = 403
        response.headers["HX-Redirect"] = request.route_url("login")
        return response
    return HTTPSeeOther(
        location=request.route_url("login") + "?came_from=" + request.path
    )


# ---------------------------------------------------------------------------
# Setup (first-run admin creation)
# ---------------------------------------------------------------------------

def _get_setup_token(request):
    item = request.dbsession.get(ConfigItem, SETUP_TOKEN_KEY)
    return item.value if item else None


def _valid_setup_token(stored, provided):
    if not stored or not provided:
        return False
    return hmac.compare_digest(stored, provided)


@view_config(route_name="setup", request_method="GET",
             renderer="menage2:templates/auth/setup.pt",
             permission=NO_PERMISSION_REQUIRED)
def setup_get(request):
    from sqlalchemy import func
    count = request.dbsession.query(func.count(User.id)).scalar()
    if count > 0:
        return HTTPSeeOther(location=request.route_url("list_todos"))

    token_param = request.params.get("token", "").strip()
    stored = _get_setup_token(request)

    if not token_param:
        return {"stage": "token", "token_error": None, "errors": {}, "token": ""}

    if not _valid_setup_token(stored, token_param):
        return {"stage": "token", "token_error": "Invalid token.", "errors": {}, "token": ""}

    return {"stage": "form", "token": token_param, "errors": {}, "token_error": None}


@view_config(route_name="setup", request_method="POST",
             renderer="menage2:templates/auth/setup.pt",
             permission=NO_PERMISSION_REQUIRED)
def setup_post(request):
    from sqlalchemy import func
    count = request.dbsession.query(func.count(User.id)).scalar()
    if count > 0:
        return HTTPSeeOther(location=request.route_url("list_todos"))

    token_post = request.POST.get("token", "").strip()
    stored = _get_setup_token(request)

    if not _valid_setup_token(stored, token_post):
        return {"stage": "token", "token_error": "Invalid or missing token.", "errors": {}, "token": ""}

    errors = {}
    username = request.POST.get("username", "").strip()
    real_name = request.POST.get("real_name", "").strip()
    email = request.POST.get("email", "").strip()
    password = request.POST.get("password", "")
    confirm = request.POST.get("confirm_password", "")

    if not username:
        errors["username"] = "Username is required."
    if not real_name:
        errors["real_name"] = "Real name is required."
    if not email:
        errors["email"] = "Email is required."
    if not password:
        errors["password"] = "Password is required."
    elif password != confirm:
        errors["confirm_password"] = "Passwords do not match."

    if errors:
        return {"stage": "form", "token": token_post, "errors": errors, "token_error": None}

    user = User(
        username=username,
        real_name=real_name,
        email=email,
        password_hash=_ph.hash(password),
        is_admin=True,
        is_active=True,
        created_at=_now(),
    )
    request.dbsession.add(user)

    # Destroy the one-time setup token
    setup_token_item = request.dbsession.get(ConfigItem, SETUP_TOKEN_KEY)
    if setup_token_item is not None:
        request.dbsession.delete(setup_token_item)

    # Seed the dashboard token
    dash_token = secrets.token_urlsafe(64)
    config_item = request.dbsession.get(ConfigItem, DASHBOARD_TOKEN_KEY)
    if config_item is None:
        request.dbsession.add(ConfigItem(key=DASHBOARD_TOKEN_KEY, value=dash_token))
    else:
        config_item.value = dash_token

    request.dbsession.flush()
    request.session["user_id"] = user.id
    return HTTPSeeOther(location=request.route_url("list_todos"))


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

@view_config(route_name="login", request_method="GET",
             renderer="menage2:templates/auth/login.pt",
             permission=NO_PERMISSION_REQUIRED)
def login_get(request):
    if request.identity is not None:
        return HTTPSeeOther(location=request.route_url("list_todos"))
    return {"error": None, "came_from": request.params.get("came_from", "")}


@view_config(route_name="login", request_method="POST",
             renderer="menage2:templates/auth/login.pt",
             permission=NO_PERMISSION_REQUIRED)
def login_post(request):
    username = request.POST.get("username", "").strip()
    password = request.POST.get("password", "")
    came_from = request.POST.get("came_from", "")

    user = (
        request.dbsession.query(User)
        .filter(User.username == username)
        .first()
    )

    error = None
    if user is None or not user.is_active or user.password_hash is None:
        error = "Invalid username or password."
    else:
        try:
            _ph.verify(user.password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            error = "Invalid username or password."

    if error:
        return {"error": error, "came_from": came_from}

    if _ph.check_needs_rehash(user.password_hash):
        user.password_hash = _ph.hash(password)

    user.last_login_at = _now()
    request.session["user_id"] = user.id
    next_url = came_from if (came_from and came_from.startswith("/")) else request.route_url("list_todos")
    return HTTPSeeOther(location=next_url)


@view_config(route_name="logout", request_method="POST",
             permission=NO_PERMISSION_REQUIRED)
def logout(request):
    request.session.invalidate()
    return HTTPSeeOther(location=request.route_url("login"))


# ---------------------------------------------------------------------------
# Password recovery
# ---------------------------------------------------------------------------

@view_config(route_name="forgot_password", request_method="GET",
             renderer="menage2:templates/auth/forgot_password.pt",
             permission=NO_PERMISSION_REQUIRED)
def forgot_password_get(request):
    return {"submitted": False}


@view_config(route_name="forgot_password", request_method="POST",
             renderer="menage2:templates/auth/forgot_password.pt",
             permission=NO_PERMISSION_REQUIRED)
def forgot_password_post(request):
    email = request.POST.get("email", "").strip()
    user = request.dbsession.query(User).filter(User.email == email).first()
    if user and user.is_active:
        token = secrets.token_urlsafe(32)
        user.password_reset_token = token
        user.password_reset_token_expires_at = _now() + timedelta(hours=1)
        _send_password_reset_email(request, user, token)
    return {"submitted": True}


@view_config(route_name="reset_password", request_method="GET",
             renderer="menage2:templates/auth/reset_password.pt",
             permission=NO_PERMISSION_REQUIRED)
def reset_password_get(request):
    token = request.matchdict["token"]
    user = _get_user_by_reset_token(request, token)
    if user is None:
        return {"valid": False, "error": None, "token": token}
    return {"valid": True, "error": None, "token": token}


@view_config(route_name="reset_password", request_method="POST",
             renderer="menage2:templates/auth/reset_password.pt",
             permission=NO_PERMISSION_REQUIRED)
def reset_password_post(request):
    token = request.matchdict["token"]
    user = _get_user_by_reset_token(request, token)
    if user is None:
        return {"valid": False, "error": None, "token": token}

    password = request.POST.get("password", "")
    confirm = request.POST.get("confirm_password", "")

    if not password:
        return {"valid": True, "error": "Password is required.", "token": token}
    if password != confirm:
        return {"valid": True, "error": "Passwords do not match.", "token": token}

    user.password_hash = _ph.hash(password)
    user.password_reset_token = None
    user.password_reset_token_expires_at = None
    return HTTPSeeOther(location=request.route_url("login"))


def _get_user_by_reset_token(request, token):
    user = (
        request.dbsession.query(User)
        .filter(User.password_reset_token == token)
        .first()
    )
    if user is None:
        return None
    if user.password_reset_token_expires_at < _now():
        return None
    return user


def _send_password_reset_email(request, user, token):
    settings = request.registry.settings
    host = settings.get("mail.host", "localhost")
    port = int(settings.get("mail.port", 25))
    mail_username = settings.get("mail.username", "")
    mail_password = settings.get("mail.password", "")
    from_address = settings.get("mail.from_address", "menage@localhost")
    use_tls = settings.get("mail.use_tls", "false").lower() == "true"

    reset_url = request.route_url("reset_password", token=token)

    msg = EmailMessage()
    msg["Subject"] = "Password reset for Menage"
    msg["From"] = from_address
    msg["To"] = user.email
    msg.set_content(
        f"Hello {user.real_name},\n\n"
        f"Click the link below to reset your Menage password:\n\n"
        f"{reset_url}\n\n"
        f"This link expires in 1 hour. If you did not request this, ignore this email.\n"
    )

    smtp_class = smtplib.SMTP_SSL if use_tls else smtplib.SMTP
    with smtp_class(host, port) as smtp:
        if not use_tls and mail_username:
            smtp.starttls()
        if mail_username:
            smtp.login(mail_username, mail_password)
        smtp.send_message(msg)


# ---------------------------------------------------------------------------
# WebAuthn / Passkey login
# ---------------------------------------------------------------------------

@view_config(route_name="login_passkey_begin", request_method="POST",
             renderer="json", permission=NO_PERMISSION_REQUIRED)
def login_passkey_begin(request):
    import webauthn
    from webauthn.helpers.structs import UserVerificationRequirement

    all_passkeys = request.dbsession.query(Passkey).all()
    allow_credentials = [
        webauthn.helpers.structs.PublicKeyCredentialDescriptor(
            id=pk.credential_id,
        )
        for pk in all_passkeys
    ]

    options = webauthn.generate_authentication_options(
        rp_id=request.domain,
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    request.session["webauthn_auth_challenge"] = base64.b64encode(options.challenge).decode()

    return json.loads(webauthn.options_to_json(options))


@view_config(route_name="login_passkey_complete", request_method="POST",
             renderer="json", permission=NO_PERMISSION_REQUIRED)
def login_passkey_complete(request):
    import webauthn
    from webauthn.helpers.exceptions import InvalidCBORData, InvalidAuthenticatorDataStructure

    challenge_b64 = request.session.get("webauthn_auth_challenge")
    if not challenge_b64:
        request.response.status_int = 400
        return {"error": "No challenge found. Please try again."}

    challenge = base64.b64decode(challenge_b64)

    try:
        credential_data = request.json_body
    except Exception:
        request.response.status_int = 400
        return {"error": "Invalid request body."}

    credential_id_b64 = credential_data.get("rawId") or credential_data.get("id", "")
    try:
        credential_id = base64.urlsafe_b64decode(credential_id_b64 + "==")
    except Exception:
        request.response.status_int = 400
        return {"error": "Invalid credential ID."}

    passkey = (
        request.dbsession.query(Passkey)
        .filter(Passkey.credential_id == credential_id)
        .first()
    )
    if passkey is None:
        request.response.status_int = 401
        return {"error": "Passkey not found."}

    try:
        auth_verification = webauthn.verify_authentication_response(
            credential=credential_data,
            expected_challenge=challenge,
            expected_rp_id=request.domain,
            expected_origin=f"{request.scheme}://{request.host}",
            credential_public_key=passkey.credential_public_key,
            credential_current_sign_count=passkey.sign_count,
        )
    except Exception as e:
        request.response.status_int = 401
        return {"error": f"Authentication failed: {e}"}

    passkey.sign_count = auth_verification.new_sign_count
    passkey.last_used_at = _now()

    user = passkey.user
    if not user.is_active:
        request.response.status_int = 403
        return {"error": "Account is inactive."}

    user.last_login_at = _now()
    request.session["user_id"] = user.id
    del request.session["webauthn_auth_challenge"]

    return {"ok": True, "redirect": request.route_url("list_todos")}
