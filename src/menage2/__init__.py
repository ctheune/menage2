from pyramid.config import Configurator
import logging


def main(global_config, **settings):
    """This function returns a Pyramid WSGI application."""

    logging.basicConfig()  # you need to initialize logging, otherwise you will not see anything from requests
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True

    with Configurator(settings=settings) as config:
        config.include("pyramid_chameleon")
        config.include(".routes")
        config.include(".models")
        config.scan()

    return config.make_wsgi_app()
