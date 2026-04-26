import datetime as _datetime
import secrets
from datetime import datetime, timezone

from argon2 import PasswordHasher
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther
from pyramid.view import view_config

from ..models.config import ConfigItem
from ..models.user import User
from ..recurrence import force_recurrence_sweep
from ..security import PERM_ADMIN
from ..views.auth import DASHBOARD_TOKEN_KEY

_ph = PasswordHasher()


def _now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# User listing
# ---------------------------------------------------------------------------

@view_config(route_name="admin_users", renderer="menage2:templates/admin/users.pt",
             permission=PERM_ADMIN)
def list_users(request):
    users = request.dbsession.query(User).order_by(User.username).all()
    sweep_spawned = request.params.get("sweep_spawned")
    return {
        "users": users,
        "sweep_spawned": int(sweep_spawned) if sweep_spawned and sweep_spawned.isdigit() else None,
    }


# ---------------------------------------------------------------------------
# Create user
# ---------------------------------------------------------------------------

@view_config(route_name="admin_user_new", request_method="GET",
             renderer="menage2:templates/admin/user_form.pt",
             permission=PERM_ADMIN)
def new_user_get(request):
    return {"user": None, "errors": {}, "action": request.route_url("admin_user_new")}


@view_config(route_name="admin_user_new", request_method="POST",
             renderer="menage2:templates/admin/user_form.pt",
             permission=PERM_ADMIN)
def new_user_post(request):
    errors = {}
    username = request.POST.get("username", "").strip()
    real_name = request.POST.get("real_name", "").strip()
    email = request.POST.get("email", "").strip()
    password = request.POST.get("password", "")
    is_admin = bool(request.POST.get("is_admin"))

    if not username:
        errors["username"] = "Username is required."
    else:
        existing = request.dbsession.query(User).filter(User.username == username).first()
        if existing:
            errors["username"] = "Username already taken."

    if not real_name:
        errors["real_name"] = "Real name is required."

    if not email:
        errors["email"] = "Email is required."
    else:
        existing_email = request.dbsession.query(User).filter(User.email == email).first()
        if existing_email:
            errors["email"] = "Email already in use."

    if errors:
        return {"user": None, "errors": errors, "action": request.route_url("admin_user_new")}

    user = User(
        username=username,
        real_name=real_name,
        email=email,
        password_hash=_ph.hash(password) if password else None,
        is_admin=is_admin,
        is_active=True,
        created_at=_now(),
    )
    request.dbsession.add(user)
    return HTTPSeeOther(location=request.route_url("admin_users"))


# ---------------------------------------------------------------------------
# Edit user
# ---------------------------------------------------------------------------

@view_config(route_name="admin_user_edit", request_method="GET",
             renderer="menage2:templates/admin/user_form.pt",
             permission=PERM_ADMIN)
def edit_user_get(request):
    user_id = int(request.matchdict["id"])
    user = request.dbsession.get(User, user_id)
    if user is None:
        raise HTTPNotFound()
    return {"user": user, "errors": {}, "action": request.route_url("admin_user_edit", id=user_id)}


@view_config(route_name="admin_user_edit", request_method="POST",
             renderer="menage2:templates/admin/user_form.pt",
             permission=PERM_ADMIN)
def edit_user_post(request):
    user_id = int(request.matchdict["id"])
    user = request.dbsession.get(User, user_id)
    if user is None:
        raise HTTPNotFound()

    errors = {}
    real_name = request.POST.get("real_name", "").strip()
    email = request.POST.get("email", "").strip()
    new_password = request.POST.get("password", "")
    is_admin = bool(request.POST.get("is_admin"))
    is_active = bool(request.POST.get("is_active"))

    if not real_name:
        errors["real_name"] = "Real name is required."

    if not email:
        errors["email"] = "Email is required."
    else:
        conflict = (
            request.dbsession.query(User)
            .filter(User.email == email, User.id != user_id)
            .first()
        )
        if conflict:
            errors["email"] = "Email already in use by another user."

    if errors:
        return {"user": user, "errors": errors, "action": request.route_url("admin_user_edit", id=user_id)}

    # Guard: prevent removing admin from last admin
    if user.is_admin and not is_admin:
        admin_count = request.dbsession.query(User).filter(User.is_admin == True, User.is_active == True).count()
        if admin_count <= 1:
            errors["is_admin"] = "Cannot remove admin from the last active administrator."
            return {"user": user, "errors": errors, "action": request.route_url("admin_user_edit", id=user_id)}

    user.real_name = real_name
    user.email = email
    user.is_admin = is_admin
    user.is_active = is_active

    if new_password:
        user.password_hash = _ph.hash(new_password)

    return HTTPSeeOther(location=request.route_url("admin_users"))


# ---------------------------------------------------------------------------
# Deactivate / delete
# ---------------------------------------------------------------------------

@view_config(route_name="admin_user_deactivate", request_method="POST",
             permission=PERM_ADMIN)
def deactivate_user(request):
    user_id = int(request.matchdict["id"])
    if user_id == request.identity.id:
        raise HTTPBadRequest("You cannot deactivate your own account.")
    user = request.dbsession.get(User, user_id)
    if user is None:
        raise HTTPNotFound()
    user.is_active = False
    return HTTPSeeOther(location=request.route_url("admin_users"))


@view_config(route_name="admin_user_delete", request_method="POST",
             permission=PERM_ADMIN)
def delete_user(request):
    user_id = int(request.matchdict["id"])
    if user_id == request.identity.id:
        raise HTTPBadRequest("You cannot delete your own account.")
    user = request.dbsession.get(User, user_id)
    if user is None:
        raise HTTPNotFound()

    if user.is_admin:
        admin_count = (
            request.dbsession.query(User)
            .filter(User.is_admin == True, User.is_active == True)
            .count()
        )
        if admin_count <= 1:
            raise HTTPBadRequest("Cannot delete the last active administrator.")

    request.dbsession.delete(user)
    return HTTPSeeOther(location=request.route_url("admin_users"))


# ---------------------------------------------------------------------------
# Dashboard token management
# ---------------------------------------------------------------------------

@view_config(route_name="admin_dashboard_token",
             renderer="menage2:templates/admin/dashboard_token.pt",
             permission=PERM_ADMIN)
def dashboard_token_view(request):
    config_item = request.dbsession.get(ConfigItem, DASHBOARD_TOKEN_KEY)

    if request.method == "POST":
        token = secrets.token_urlsafe(64)
        if config_item is None:
            request.dbsession.add(ConfigItem(key=DASHBOARD_TOKEN_KEY, value=token))
        else:
            config_item.value = token
        request.dbsession.flush()
        config_item = request.dbsession.get(ConfigItem, DASHBOARD_TOKEN_KEY)

    token_value = config_item.value if config_item else None
    dashboard_url = (
        request.route_url("dashboard", token=token_value)
        if token_value else None
    )

    return {"token": token_value, "dashboard_url": dashboard_url}


# ---------------------------------------------------------------------------
# Manual recurrence sweep
# ---------------------------------------------------------------------------

@view_config(route_name="admin_recurrence_sweep",
             request_method="POST",
             permission=PERM_ADMIN)
def recurrence_sweep(request):
    """Force the daily recurrence sweep regardless of the marker.

    Useful after editing rules in bulk or recovering from a worker that was
    down across midnight. Spawned count is surfaced via a flash message.
    """
    today = _datetime.date.today()
    spawned = force_recurrence_sweep(request.dbsession, today, _now())
    return HTTPSeeOther(location=request.route_url(
        "admin_users", _query={"sweep_spawned": str(spawned)},
    ))
