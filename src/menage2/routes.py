import time

from pyramid.security import NO_PERMISSION_REQUIRED
from pyramid.static import QueryStringConstantCacheBuster


def includeme(config):
    config.add_static_view(
        "static", "static", cache_max_age=3600, permission=NO_PERMISSION_REQUIRED
    )
    config.add_cache_buster(
        "static", QueryStringConstantCacheBuster(str(int(time.time())))
    )

    config.add_route("suggest_ingredient", "/ingredient/suggest")
    config.add_route("list_ingredients", "/ingredient")
    config.add_route("ingredient_recipes", "/ingredient/{id}/recipes")
    config.add_route("ingredient_toggle_tag", "/ingredient/{id}/tag/{tag}")

    # Auth
    config.add_route("login", "/login")
    config.add_route("logout", "/logout")
    config.add_route("setup", "/setup")
    config.add_route("forgot_password", "/forgot-password")
    config.add_route("reset_password", "/reset-password/{token}")

    # WebAuthn JSON endpoints
    config.add_route("login_passkey_begin", "/login/passkey/begin")
    config.add_route("login_passkey_complete", "/login/passkey/complete")

    # Account management (authenticated users)
    config.add_route("account", "/account")
    config.add_route("account_change_password", "/account/password")
    config.add_route("account_passkeys", "/account/passkeys")
    config.add_route("account_passkey_delete", "/account/passkeys/{id}/delete")
    config.add_route(
        "account_passkey_register_begin", "/account/passkeys/register/begin"
    )
    config.add_route(
        "account_passkey_register_complete", "/account/passkeys/register/complete"
    )

    # Admin
    config.add_route("admin_operations", "/admin/operations")
    config.add_route("admin_users", "/admin/users")
    config.add_route("admin_user_new", "/admin/users/new")
    config.add_route("admin_user_edit", "/admin/users/{id}/edit")
    config.add_route("admin_user_deactivate", "/admin/users/{id}/deactivate")
    config.add_route("admin_user_delete", "/admin/users/{id}/delete")
    config.add_route("admin_dashboard_token", "/admin/dashboard-token")
    config.add_route("admin_base_name", "/admin/base-name")
    config.add_route("admin_recurrence_sweep", "/admin/recurrence-sweep")
    config.add_route("admin_teams", "/admin/teams")
    config.add_route("admin_team_new", "/admin/teams/new")
    config.add_route("admin_team_edit", "/admin/teams/{id}/edit")
    config.add_route("admin_team_delete", "/admin/teams/{id}/delete")
    config.add_route("admin_team_member_add", "/admin/teams/{id}/members")
    config.add_route(
        "admin_team_member_remove", "/admin/teams/{id}/members/{member_id}/remove"
    )

    config.add_route("home", "/")
    config.add_route("list_recipes", "/recipes")
    config.add_route("add_recipe", "/recipe")
    config.add_route("edit_recipe", "/recipe/{id}/edit")
    config.add_route("recipe_steps", "/recipe/{id}/steps")

    config.add_route("list_weeks", "/weeks")
    config.add_route("add_week", "/week/new")
    config.add_route("edit_week", "/week/{id}/edit")
    config.add_route("add_day", "/week/{id}/new-day/{position}")
    config.add_route("send_to_shopping_list", "/week/{id}/shoppinglist")

    config.add_route("set_dinner", "/day/{day}/dinner/{recipe}")
    config.add_route("toggle_day_shopping", "/day/{day}/toggle-shopping")
    config.add_route("delete_day", "/day/{day}")

    config.add_route("dashboard", "/dashboard/{token}")
    config.add_route("dashboard_recipes", "/dashboard/{token}/recipes")
    config.add_route("dashboard_pt_departures", "/dashboard/{token}/pt/departures")
    config.add_route("dashboard_pt_hbf", "/dashboard/{token}/pt/hbf")

    config.add_route("letscook", "/dashboard/{token}/lets-cook")

    config.add_route("timers", "/dashboard/{token}/timers")
    config.add_route("timer", "/dashboard/{token}/timer/{id}")
    config.add_route("timer_pause", "/dashboard/{token}/timer/{id}/pause")

    # TODOs / Tasks

    config.add_route("list_todos", "/todos")

    config.add_route("list_todo_groups", "/todos/groups")
    config.add_route("task_subnav", "/todos/subnav")

    config.add_route("todo_details_panel", "/todos/details-panel")
    config.add_route("todo_link_label", "/todos/link-label")
    config.add_route("recurrence_history", "/todos/{id}/history")
    config.add_route(
        "todo_attachment_thumbnail",
        "/todos/{todo_id}/attachment/{uuid}/thumb",
    )
    config.add_route("todo_attachment_full", "/todos/{todo_id}/attachment/{uuid}/full")

    config.add_route("add_todo", "/todos/add")

    config.add_route("todo_update", "/todos/{id:\\d+}")
    config.add_route("todo_batch_action", "/todos/batch-action")
    config.add_route("todo_attachment_upload", "/todos/{id}/attachments")
    config.add_route(
        "todo_attachment_delete", "/todos/{todo_id}/attachment/{uuid}/delete"
    )

    config.add_route("todos_done", "/todos/done-items")
    config.add_route("todos_hold", "/todos/hold-items")
    config.add_route("todos_postpone", "/todos/postpone-items")
    config.add_route("todos_activate_all_on_hold", "/todos/activate-on-hold")
    config.add_route("todo_undo", "/todos/undo")

    config.add_route("parse_date_preview", "/todos/parse-date")  # xxx
    config.add_route("parse_recurrence_preview", "/todos/parse-recurrence")  # xxx
    config.add_route("todo_picker_postpone", "/todos/pickers/postpone")  # xxx
    config.add_route("list_principals_json", "/todos/principals.json")  # xxx

    # Helpers
    config.add_route("todo_date_picker", "/todos/pickers/date")
    config.add_route("todo_recurrence_picker", "/todos/pickers/recurrence")
    config.add_route("todo_tag_picker", "/todos/pickers/tag")
    config.add_route("todo_assignee_picker", "/todos/pickers/assignee")

    # Protocols
    config.add_route("list_protocols", "/protocols")
    config.add_route("new_protocol", "/protocols/new")
    config.add_route("edit_protocol", "/protocols/{id}/edit")
    config.add_route("archive_protocol", "/protocols/{id}/archive")
    config.add_route("unarchive_protocol", "/protocols/{id}/unarchive")
    config.add_route("add_protocol_item", "/protocols/{id}/items")
    config.add_route("update_protocol_item", "/protocols/{id}/items/{item_id}")
    config.add_route(
        "update_protocol_item_partial", "/protocols/{id}/items/{item_id}/partial"
    )
    config.add_route("delete_protocol_item", "/protocols/{id}/items/{item_id}/delete")
    config.add_route("start_protocol_run", "/protocols/{id}/start")
    config.add_route("run_item_done", "/protocols/run/{id}/items/{item_id}/done")
    config.add_route("run_item_send", "/protocols/run/{id}/items/{item_id}/send")
    config.add_route("run_item_edit", "/protocols/run/{id}/items/{item_id}/edit")
