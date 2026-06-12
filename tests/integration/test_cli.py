"""CLI E2E: dak-cli run against the test agent."""
import json
import os
import subprocess

import pytest

from conftest import AGENT_URL

MODEL = "fake-default"

CLI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "cli"))


@pytest.mark.skipif(not os.path.isdir(CLI_DIR), reason="cli directory not found")
def test_cli_run_round_trip(fake_llm, tmp_path):
    fake_llm.clear(MODEL)
    fake_llm.script(MODEL, [fake_llm.text("CLI round trip answer.")])

    # Isolate the CLI config (~/.dak-cli) so we don't touch the real one
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    env["DAK_AGENT_URL"] = AGENT_URL

    config_dir = tmp_path / ".dak-cli"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(json.dumps({"username": "it_cli_user"}))

    result = subprocess.run(
        ["uv", "run", "dak-cli", "run", "Hello via CLI"],
        cwd=CLI_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    assert "CLI round trip answer." in result.stdout
