Menage is a software suite for managing household day to day tasks:

- Planning meals (including ingredients and tags on them) 
- Creating shopping lists (using tags to allow grouping things that are placed in similar locations in the supermarket)
- a dashboard run in a kitchen ipad

# Development

* use git
* use devenv to provide a development environment
  * `devenv test` to run tests if no `devenv up` is already running. if `devenv up` is running, then use `uv run pytest`.
* use `uv run alembic -c development.ini revision --autogenerate -m "<message>"` to generate database upgrades when changing the structure. however, verify the generated file whether it matches the changes you made or whether you need to adjust things for proper upgrades. downgrades are not important.

# Architectural decisions

* the app must be usable in multiple browser tabs, don't persist state in sessions when this would break this goal

# Frameworks

* impement client-side interactivity with hyperscript, only switch to native js if the feature is much simpler to implement in native js

# Tests

* write tests for all changes
* use pytest tests, do not write unittest classes
* prefer fixtures instead of random setup methods
* keep things cleanly structured: try to provide reasonable unit test (no db interaction), integration test (no ui interaction), and ui level tests
* if you need to create extensive mocking, re-evaluate your implementation approach to allow reasonable testing, this is a trade off and not a hard and fast rule, though.
