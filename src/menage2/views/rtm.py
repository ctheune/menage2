from pyramid.view import view_config
import os
from rtmapi import Rtm

from menage2.models import ConfigItem

from pyramid.httpexceptions import HTTPSeeOther


@view_config(route_name="rtm_login", renderer="menage2:templates/rtm_login.pt")
def rtm_login(request):
    api_key = os.environ["RTM_API_KEY"]
    shared_secret = os.environ["RTM_SHARED_SECRET"]
    session = request.dbsession

    try:
        config_token = (
            session.query(ConfigItem).filter(ConfigItem.key == "RTM_TOKEN").one()
        )
    except Exception:
        config_token = ConfigItem(key="RTM_TOKEN", value="")
        session.add(config_token)
    print(config_token.value)
    api = Rtm(api_key, shared_secret, "write", config_token.value)

    if api.token_valid():
        return {"status": "OK"}

    login_method = os.environ.get("RTM_LOGIN_METHOD", "desktop")
    if login_method == "desktop":
        if request.params.get("frob"):
            # we're already in a login process
            frob = request.params["frob"]
            if not api.retrieve_token(frob):
                raise RuntimeError()
            config_token.value = api.token
            print(config_token.value)
            return HTTPSeeOther(request.route_url("rtm_login"))
        else:
            url, frob = api.authenticate_desktop()

            return {
                "login_method": login_method,
                "login_url": url,
                "frob": frob,
                "status": "LOGIN-NEEDED",
            }

    elif login_method == "web":
        pass

    raise ValueError(f"Invalid RTM login method: {login_method}")


@view_config(route_name="rtm_callback")
def rtm_callback(request):
    pass
