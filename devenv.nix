{ pkgs, lib, config, inputs, ... }:

{
  packages = [ pkgs.opencode ];
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
    port = 6379;
  };

  services.mailpit = {
    enable = true;
  };

  # https://devenv.sh/tests/
  enterTest = ''
    uv run pytest
  '';

}
