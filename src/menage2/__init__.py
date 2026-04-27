import logging
import secrets

from pyramid.config import Configurator
from pyramid.events import ApplicationCreated

log = logging.getLogger(__name__)

SETUP_TOKEN_KEY = "setup_token"


def _on_app_created(event):
    """On startup, if no users exist, generate a one-time setup token and log it."""
    import transaction

    from .models import get_engine, get_session_factory, get_tm_session
    from .models.config import ConfigItem
    from .models.user import User

    settings = event.app.registry.settings
    engine = get_engine(settings)
    session_factory = get_session_factory(engine)

    try:
        with transaction.manager:
            db = get_tm_session(session_factory, transaction.manager)
            if db.query(User).count() == 0:
                token = secrets.token_urlsafe(32)
                existing = db.get(ConfigItem, SETUP_TOKEN_KEY)
                if existing:
                    existing.value = token
                else:
                    db.add(ConfigItem(key=SETUP_TOKEN_KEY, value=token))
                base_url = settings.get(
                    "menage.base_url", "http://localhost:6543"
                ).rstrip("/")
                setup_url = f"{base_url}/setup?token={token}"
                log.warning(
                    "\n" + "=" * 60 + "\n"
                    "  FIRST RUN — no users found\n"
                    "  Open this URL to create the admin account:\n\n"
                    f"  {setup_url}\n\n"
                    "  The token is destroyed after setup completes.\n" + "=" * 60
                )
    except Exception:
        log.exception("Failed to generate setup token")


def main(global_config, **settings):
    """This function returns a Pyramid WSGI application."""

    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True

    with Configurator(settings=settings) as config:
        config.include("pyramid_chameleon")
        config.include("pyramid_beaker")
        config.include(".routes")
        config.include(".models")

        from .security import SessionSecurityPolicy

        config.set_security_policy(SessionSecurityPolicy())
        config.set_default_permission("authenticated")

        config.add_tween(
            "menage2.tweens.first_run_tween_factory",
            under="pyramid_tm.tm_tween_factory",
        )
        config.add_subscriber(_on_app_created, ApplicationCreated)

        config.scan()

    return config.make_wsgi_app()
