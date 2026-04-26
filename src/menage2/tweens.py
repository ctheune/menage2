from pyramid.httpexceptions import HTTPSeeOther


_SKIP_PREFIXES = ("/setup", "/static", "/login", "/forgot-password", "/reset-password")


def first_run_tween_factory(handler, registry):
    def tween(request):
        if not any(request.path.startswith(p) for p in _SKIP_PREFIXES):
            from .models.user import User
            count = request.dbsession.query(User).count()
            if count == 0:
                return HTTPSeeOther(location=request.route_url("setup"))
        return handler(request)
    return tween
