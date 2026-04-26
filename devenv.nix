{ pkgs, lib, config, inputs, ... }:

{
  # https://devenv.sh/languages/
  languages.python.enable = true;

  tasks."menage:upgrade-db".exec = "uv run alembic -c development.ini upgrade head";

  processes.menage = {
    after = [ "menage:upgrade-db@succeeded" ];
    exec = "uv run pserve --reload development.ini";
  };

  services.postgres = {
    enable = true;
    initialDatabases = [
      { name = "menage"; }
      { name = "menage-testing"; }
    ];
  };

  services.redis = {
    enable = true;
  };

  services.mailpit = {
    enable = true;
  };

  # https://devenv.sh/tests/
  enterTest = ''
    uv run pytest
  '';

}
