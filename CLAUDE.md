# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Menage is a household-management web app: meal planning, shopping lists, recurring task management, protocol checklists, and a kitchen-kiosk dashboard.

# Development

* use git

* you are running inside a devenv — `devenv up` is already running in the background, DO NOT start any other devenv processes. Services: PostgreSQL (databases `menage` / `menage-testing`), Redis, Mailpit.

* `uv run pytest -v` to run all tests
* `uv run pytest -v src/menage2/tests/test_todos.py` to run a single file
* `uv run pytest -v -k "test_postpone"` to run tests matching a name pattern
* `pre-commit run -a` for linting and static analysis
* `uv run alembic -c development.ini revision --autogenerate -m "<message>"` to generate DB migrations — always verify the generated file before committing; downgrades are not important

# Tool use - file writing

To avoid encoding issues, always encode unicode characters outside ascii as hex characters as appropriate for the language (javascript, json, python, ...)

# Architectural decisions

* The app must be usable in multiple browser tabs — do not persist mutable UI state in sessions

# Architecture

## Request Flow

Routes are declared in `routes.py` and views use `@view_config` decorators (scanned by `config.scan()`). All routes require `authenticated` permission by default (`SessionSecurityPolicy` checks `user_id` in session).

Two tweens run on every request:
- `first_run_tween_factory`: if no users exist, redirects to `/setup`
- `hx_trigger_tween_factory`: attaches `request.response.hx_trigger` so any view can call `request.response.hx_trigger("event-name", {...})` to set the `HX-Trigger` response header

Views return a dict for Chameleon rendering or a `Response` directly for HTMX swaps. Templates use `layout.pt` as the outer shell via `metal:use-macro`. Partial templates (prefixed `_`) are used as HTMX swap targets and do not extend the layout.

## HTMX/Hyperscript Frontend

Client-side interactivity is implemented with Hyperscript (`_="..."`) not plain JS. Use `<tagname/>` syntax (angle brackets) to refer to HTML tags in Hyperscript — `<a/>` not `a`.

HTMX is used for all server communication. Use `hx-trigger` / `hx-target` / `hx-swap` to declaratively update page regions. Custom events coordinate components — for example, any mutation fires `response.hx_trigger("todo-updated")` via the `HX-Trigger` header, which causes the todo list and subnav (which listen for `todo-updated from:window`) to refetch without a full reload.

The `menage.js` file handles gestures (swipe right → done, swipe left → hold), picker UIs (due-date, postpone), and the composite pill input bridge. `composite-input.js` drives the `#tag @assignee ^date *recurrence ~note` parsing in the task input.

## form-json Pattern

This is the primary mutation mechanism. Forms carry `hx-ext="form-json"`, activating the custom extension in `static/form-json.js`, which serializes form inputs as a nested JSON body (`Content-Type: application/json`).

Structured sub-objects that cannot be a single `<input>` are encoded as **hidden inputs with dotted names** (`name="recurrence.kind"` becomes `{"recurrence": {"kind": "..."}}` in the JSON). This is the "hidden value" approach.

The server reads `request.json_body`, validates it through a Pydantic model, and applies the patch:

```python
data = BatchAction.model_validate(request.json_body)
```

The `clear_fields` list in `TodoUpdate` handles explicit field removal: since omitted fields are absent (not null) in JSON, the client sends `clear_fields.0=due_date` to signal intentional clearing.

`hx-vals="js:expr"` (with the `js:` prefix) is evaluated lazily at request time — use a JS state variable populated just before the click rather than `setAttribute` at click time. `hx-vals` is read from the form element (the one with `hx-post`), not from submit buttons.

## Key Models

- **`Todo`**: core task. `tags`/`assignees` are PostgreSQL `TEXT[]` (Python `set` via `TagSet` custom type). `recurrence_id` → `RecurrenceRule` (shared across sibling recurrences). `recurred_from_id` → self (previous in chain). `protocol_run_id` → `ProtocolRun` (1-to-1, nullable).
- **`RecurrenceRule`**: `kind` (`after`/`every`), `interval_value`, `interval_unit`, optional `weekday`/`month_day`.
- **`Protocol`/`ProtocolRun`/`ProtocolItem`/`ProtocolRunItem`**: `ProtocolRun` is created from a `Protocol`; on first `GET` of the run, `ensure_snapshot_run_items()` freezes a copy of the current items. When all items resolve, `maybe_close_run()` auto-completes the linked `Todo` and spawns the next recurrence.
- **`Recipe`/`Week`/`Day`**: Meal planner. `Day.suggestions()` ranks recipes by weekday, season, and `schedule.due_ratio`.
- **`Team`/`TeamMember`**: Groups for `@team-name` principal resolution. `principals.py` expands team names to member lists.

## SQLAlchemy

* Avoid id comparisons — compare object equality when the column is a mapped relationship:

  ❌ `user.id == todo.owner_id` → ✅ `user == todo.owner`

* Be aware of SQLAlchemy expression specifics when writing queries; add `# noqa` exceptions for static analysis warnings that are false positives on ORM expressions.

## Python

* Use pathlib instead of os.path
* Annotate types when you change things, avoid `Any`
* Run scripts with `uv run ...` not plain `python`

## Tests

Tests are in `src/menage2/tests/`. All fixtures are in `conftest.py`.

**Three layers:**
1. **Unit** (`test_todos.py`, `test_recurrence.py`, `test_dateparse.py`, etc.): no DB, use `dummy_request` / `app_request` fixtures.
2. **Integration** (`test_functional.py`, `test_attachments.py`, `test_nav_integration.py`, etc.): use `testapp` (WebTest) against a real DB inside a doomed transaction — the transaction is always aborted after each test for isolation, so `tm.doom()` is set; never commit in integration tests.
3. **Browser** (`test_todos_browser.py`, `test_protocols_browser.py`, etc.): Playwright against a real Waitress server (`live_server` fixture). Uses `clean_db` (full table truncation) instead of doomed transactions because the browser talks to the server over HTTP.

Use `prefer fixtures instead of setup methods`. The `authenticated_testapp` fixture gives a logged-in WebTest client; `browser_admin_user` gives a logged-in Playwright browser.

Playwright tests: use DOM-change waits rather than `wait_for_load_state("networkidle")` — the networkidle state races with `htmx.ajax` calls.
