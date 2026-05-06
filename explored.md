# Codebase Exploration Notes

## Navigation / Layout

### `src/menage2/templates/layout.pt`
- Defines the `layout` METAL macro used by all page templates via `metal:use-macro="load: layout.pt"`.
- Top `<tal:block tal:define="...">` computes all section/sub-section flags from `request.matched_route.name`:
  - `in_food`, `in_tasks`, `in_operations` (section gates)
  - `sub_todo_active`, `sub_todo_hold`, `sub_todo_scheduled`, `sub_todo_done`, `sub_protocols` (task sub-nav active states)
- The tasks sub-nav `<ul id="task-subnav-tabs">` (lines ~106–165) carries HTMX attributes when `in_tasks`:
  `hx-get=/todos/subnav`, `hx-trigger="todo-updated from:body"`, `hx-swap="innerHTML"`.
  On `todo-updated` it fetches fresh `<li>` items and replaces the `<ul>`'s innerHTML.

### `src/menage2/format.py`
- `_TASKS_ROUTES` frozenset — all routes where task sub-nav counts should be computed.
- `globals_factory` — `IBeforeRender` subscriber that adds to every template namespace:
  - `nav_task_counts` dict (`active`, `hold`, `scheduled`) — DB queries filtered by current user + filter_mode.
  - Formatting helpers (`format_timedelta`, `date_ago`, `humanize_ago`, etc.).
  - `base_name` from the `config_items` table.
- `_VALID_FILTER_MODES` frozenset: `all`, `personal`, `delegated_out`, `delegated_in`.

## Todo List

### Routes (from `src/menage2/routes.py`)
| Route | Path |
|---|---|
| `list_todos` | `/todos` |
| `list_todos_hold` | `/todos/hold` |
| `list_todos_scheduled` | `/todos/scheduled` |
| `list_todos_done` | `/todos/done` |
| `list_todo_groups` | `/todos/groups` |
| `task_subnav` | `/todos/subnav` |
| `todos_done` | `/todos/done-items` (POST) |
| `todos_hold` | `/todos/hold-items` (POST) |
| `todos_postpone` | `/todos/postpone-items` (POST) |
| `list_protocols` | `/protocols` |

### `src/menage2/views/todo.py`
- `list_todo_groups` — GET `/todos/groups` — partial for the main todo list; fires after `todo-updated`.
- `task_subnav_partial` — GET `/todos/subnav` — partial for the sub-nav; uses `HX-Current-URL` header to determine active tab. Rendered context includes `sub_todo_active/hold/scheduled/done/protocols` flags.
- `todos_done` — POST `/todos/done-items` — marks todos done, fires `HX-Trigger: {"todo-updated": null, ...}`.
- `todos_hold`, `todos_postpone`, `todo_undo` — similar, all fire `todo-updated`.
- `todo_details_panel` — GET `/todos/details-panel` — side-panel; fires `HX-Trigger: "todo-updated"` when `?updated=true`.

### `src/menage2/templates/list_todos.pt`
- `#todo-list` div listens with `hx-trigger="todo-updated from:body, focus from:window"` → fetches `/todos/groups`.
- Initial group HTML injected via `<tal:block tal:replace="structure groups_html" />` (pre-rendered by the view).

### `src/menage2/templates/_task_subnav.pt`
- Fragment (wrapped in `<tal:block>`) containing the 5 task sub-nav `<li>` items.
- Used only by the `task_subnav_partial` view for HTMX refresh responses.
- Variables needed: `request`, `nav_task_counts`, `sub_todo_active/hold/scheduled/done/protocols`.

### `src/menage2/templates/_todo_groups.pt`
- Used both for the initial `groups_html` render (via `list_todos` view) and for HTMX refresh (via `list_todo_groups`).

## HTMX / Hyperscript Patterns

- `todo-updated` event is the primary cross-component signal: fired as `HX-Trigger` header by action views, listened to by `#todo-list` and `#task-subnav-tabs`.
- Partials use `request.response` (not `Response()`) to avoid `pyramid_tm` rollback — see memory `feedback_htmx_response_pattern.md`.
- Filter mode is passed as `?filter=personal|all|delegated_out|delegated_in` query param; propagated to HTMX `hx-get` URLs at render time.

## Tests

- `src/menage2/tests/test_nav_integration.py` — integration tests for navigation structure, on-hold list, protocols, and task sub-nav partial endpoint.
- Browser tests (Playwright) live in `test_todos_browser.py`, `test_protocols_browser.py`, etc. — require `devenv up`.
- Pre-existing failures (as of 2026-05-06): `test_planner.py::test_send_to_shopping_list_creates_todos` and several `test_recurrence.py` tests.
