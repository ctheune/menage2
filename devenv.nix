{ pkgs, lib, config, inputs, ... }:

{
  packages = [ pkgs.opencode pkgs.prek ];
  languages.python.enable = true;
  languages.python.uv.enable = true;
  # basedpyright resolves imports through .venv (see pyproject.toml), so the
  # project environment must exist before the prek hooks run.
  languages.python.uv.sync.enable = true;

  tasks."menage:upgrade-db".exec = "uv run alembic -c development.ini upgrade head";

  # processes.menage = {
  #   after = [ "menage:upgrade-db@succeeded" ];
  #   exec = "uv run pserve --reload development.ini";
  # };

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
    uv run playwright install chromium
    uv run pytest
  '';

}
