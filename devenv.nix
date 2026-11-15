{ pkgs, lib, config, inputs, ... }:

{
  packages = [ pkgs.opencode ];
  languages.python.enable = true;
  languages.python.uv.enable = true;

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
    uv run playwright install chromium
    wait_for_port 6543
    wait_for_port 5432
    uv run pytest -v --tb=short -ra --junitxml=unit.xml &> pytest.log
  '';

}
