Menage is a software suite for managing household day to day tasks:

- Planning meals (including ingredients and tags on them)
- Creating shopping lists (using tags to allow grouping things that are placed in similar locations in the supermarket)
- a dashboard run in a kitchen ipad

# Development

* use git

* you are running inside a devenv
  * `uv run pytest` to run tests. run `devenv up` in the background if it isn't running already and stop it when done with the tests.

* use `uv run alembic -c development.ini revision --autogenerate -m "<message>"` to generate database upgrades when changing the structure. however, verify the generated file whether it matches the changes you made or whether you need to adjust things for proper upgrades. downgrades are not important.

# Architectural decisions

* the app must be usable in multiple browser tabs, don't persist state in sessions when this would break this goal

# Tool use - file writing

To avoid encoding issues, always encode unicode characters outside ascii as hex characters as appropriate for the language (javascript, json, python, ...)

# Frameworks

## Hyperscript instead of Javascript

* implement client-side interactivity purely with hyperscript

* note that to refer to tags (instead of classes) in a hyperscript expression you need to use pointy brackets: `<a/>` instead of just plain `a`.

# Tests

* write tests for all changes
* use pytest tests, do not write unittest classes
* prefer fixtures instead of random setup methods
* keep things cleanly structured: provide good unit test coverage (no db interaction), integration test (no ui interaction), and ui level tests
* if you need to create extensive mocking, re-evaluate your implementation approach to allow reasonable testing, this is a trade off and not a hard and fast rule, though.

# Linting

* run `pre-commit run -a` for linting and static analysis
* be aware of sqlalchemy specifics and if necessary add exceptions to avoid breaking queries
