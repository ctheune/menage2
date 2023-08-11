

Regenerate tailwind.css:

  npx tailwindcss -i ./css/input.css -o ../recipedb/static/tailwind.css --watch


Run in development mode:


  DJANGO_SETTINGS_MODULE=menage.dev_settings bin/python manage.py runserver
