{ pkgs, lib, config, inputs, ... }:

{
  # https://devenv.sh/basics/
  env.GREET = "Menage II asdfs fdsafdsa";

  packages = [ pkgs.tailwindcss_3 ];

  # https://devenv.sh/languages/
  languages.python.enable = true;


  tasks."menage:upgrade-db".exec = "uv run alembic -c development.ini upgrade head";
  tasks."menage:upgrade-test-db".exec = "uv run alembic -c development.ini upgrade head";


  processes.tailwind.exec = "cd tailwind; tailwindcss -i ./css/input.css -o ..src/menage2/static/tailwind.css --watch";
  processes.menage = {
    after = [ "menage:upgrade-db@succeeded" ];
    exec = "uv run pserve --reload development.ini ";
  };

  services.postgres = {
    enable = true;
    initialDatabases = [ {name = "menage";} ];
  };

  # https://devenv.sh/tasks/
  # tasks = {
  #   "myproj:setup".exec = "mytool build";
  #   "devenv:enterShell".after = [ "myproj:setup" ];
  # };

  # https://devenv.sh/tests/
  enterTest = ''
    echo "Running tests"
    if psql -l | grep menage-testing; then
      dropdb menage-testing
    fi
    createdb menage-testing
    uv run alembic -c testing.ini upgrade head
    uv run pytest
  '';

}
