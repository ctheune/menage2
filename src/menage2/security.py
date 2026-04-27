from pyramid.interfaces import ISecurityPolicy
from pyramid.security import NO_PERMISSION_REQUIRED, Allowed, Denied
from zope.interface import implementer

PERM_AUTHENTICATED = "authenticated"
PERM_ADMIN = "admin"


@implementer(ISecurityPolicy)
class SessionSecurityPolicy:
    def identity(self, request):
        user_id = request.session.get("user_id")
        if not user_id:
            return None
        from .models.user import User

        user = request.dbsession.get(User, user_id)
        return user if (user and user.is_active) else None

    def authenticated_userid(self, request):
        identity = request.identity
        return identity.id if identity else None

    def permits(self, request, context, permission):
        identity = request.identity
        if identity is None:
            return Denied("Not authenticated")
        if permission == PERM_AUTHENTICATED:
            return Allowed("Authenticated user")
        if permission == PERM_ADMIN:
            return Allowed("Admin") if identity.is_admin else Denied("Not admin")
        return Denied(f"Unknown permission: {permission}")
