import base64
import json
from datetime import datetime, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from pyramid.httpexceptions import HTTPSeeOther, HTTPNotFound
from pyramid.view import view_config

from ..models.user import Passkey
from ..security import PERM_AUTHENTICATED

_ph = PasswordHasher()


def _now():
    return datetime.now(timezone.utc)


@view_config(route_name="account", renderer="menage2:templates/auth/account.pt",
             permission=PERM_AUTHENTICATED)
def account_view(request):
    return {"user": request.identity}


@view_config(route_name="account_change_password", request_method="GET",
             renderer="menage2:templates/auth/change_password.pt",
             permission=PERM_AUTHENTICATED)
def change_password_get(request):
    return {"errors": {}, "success": False}


@view_config(route_name="account_change_password", request_method="POST",
             renderer="menage2:templates/auth/change_password.pt",
             permission=PERM_AUTHENTICATED)
def change_password_post(request):
    user = request.identity
    current = request.POST.get("current_password", "")
    new_pw = request.POST.get("new_password", "")
    confirm = request.POST.get("confirm_password", "")

    errors = {}

    if user.password_hash is None:
        errors["current_password"] = "Your account uses passkey authentication; set a password from the reset flow."
    else:
        try:
            _ph.verify(user.password_hash, current)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            errors["current_password"] = "Current password is incorrect."

    if not new_pw:
        errors["new_password"] = "New password is required."
    elif new_pw != confirm:
        errors["confirm_password"] = "Passwords do not match."

    if errors:
        return {"errors": errors, "success": False}

    user.password_hash = _ph.hash(new_pw)
    return {"errors": {}, "success": True}


@view_config(route_name="account_passkeys", request_method="GET",
             renderer="menage2:templates/auth/passkeys.pt",
             permission=PERM_AUTHENTICATED)
def list_passkeys(request):
    return {"user": request.identity, "passkeys": request.identity.passkeys}


@view_config(route_name="account_passkey_delete", request_method="POST",
             permission=PERM_AUTHENTICATED)
def delete_passkey(request):
    passkey_id = int(request.matchdict["id"])
    passkey = request.dbsession.get(Passkey, passkey_id)
    if passkey is None or passkey.user_id != request.identity.id:
        raise HTTPNotFound()
    request.dbsession.delete(passkey)
    return HTTPSeeOther(location=request.route_url("account_passkeys"))


@view_config(route_name="account_passkey_register_begin", request_method="POST",
             renderer="json", permission=PERM_AUTHENTICATED)
def register_passkey_begin(request):
    import webauthn
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        UserVerificationRequirement,
    )

    user = request.identity
    existing = [
        webauthn.helpers.structs.PublicKeyCredentialDescriptor(id=pk.credential_id)
        for pk in user.passkeys
    ]

    options = webauthn.generate_registration_options(
        rp_id=request.domain,
        rp_name="Menage",
        user_id=str(user.id).encode(),
        user_name=user.username,
        user_display_name=user.real_name,
        exclude_credentials=existing,
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    request.session["webauthn_reg_challenge"] = base64.b64encode(options.challenge).decode()

    return json.loads(webauthn.options_to_json(options))


@view_config(route_name="account_passkey_register_complete", request_method="POST",
             renderer="json", permission=PERM_AUTHENTICATED)
def register_passkey_complete(request):
    import webauthn

    challenge_b64 = request.session.get("webauthn_reg_challenge")
    if not challenge_b64:
        request.response.status_int = 400
        return {"error": "No challenge found. Please try again."}

    challenge = base64.b64decode(challenge_b64)

    try:
        credential_data = request.json_body
    except Exception:
        request.response.status_int = 400
        return {"error": "Invalid request body."}

    device_name = credential_data.pop("device_name", "Passkey") or "Passkey"

    try:
        verification = webauthn.verify_registration_response(
            credential=credential_data,
            expected_challenge=challenge,
            expected_rp_id=request.domain,
            expected_origin=f"{request.scheme}://{request.host}",
        )
    except Exception as e:
        request.response.status_int = 400
        return {"error": f"Registration failed: {e}"}

    passkey = Passkey(
        user_id=request.identity.id,
        credential_id=verification.credential_id,
        credential_public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
        device_name=device_name,
        created_at=_now(),
    )
    request.dbsession.add(passkey)

    del request.session["webauthn_reg_challenge"]
    return {"ok": True}
