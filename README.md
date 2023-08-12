# Menage

An app to keep track of recipes and make meal plans with automatic
suggestions what to cook when.


## Hacking

Set up environment:

  $ poetry install 
  $ poetry run pytest
  $ poetry run pserve development.ini

Regenerate tailwind.css:

  $ cd tailwindcss; npx tailwindcss -i ./css/input.css -o ../recipedb/static/tailwind.css --watch

