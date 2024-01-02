def includeme(config):
    config.add_static_view("static", "static", cache_max_age=3600)

    config.add_route("suggest_ingredient", "/ingredient/suggest")

    config.add_route("list_recipes", "/")
    config.add_route("add_recipe", "/recipe")
    config.add_route("edit_recipe", "/recipe/{id}/edit")

    config.add_route("list_weeks", "/weeks")
    config.add_route("add_week", "/week/new")
    config.add_route("show_week", "/week/{id}")
    config.add_route("edit_week", "/week/{id}/edit")
    config.add_route("add_day", "/week/{id}/new-day/{position}")
    config.add_route("send_to_rtm", "/week/{id}/shoppinglist")

    config.add_route("set_dinner", "/day/{day}/dinner/{recipe}")
    config.add_route("delete_day", "/day/{day}")

    config.add_route("rtm_login", "/services/rtm/login")
    config.add_route("rtm_callback", "/services/rtm/callback")

    config.add_route("dashboard", "/dashboard")
