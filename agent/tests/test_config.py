import os
import tempfile
import unittest

from dak_agent.config import AgentConfig, get_litellm_model_name, load_agent_config


class TestLoadAgentConfig(unittest.TestCase):
    def _write_config(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
        f.write(content)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_load_full_config(self):
        path = self._write_config(
            """
mcp_servers:
  - name: "local-mcp"
    url: "http://mcp-server:8000/mcp"
    type: "http"
  - name: "extra-mcp"
    url: "http://extra:8000/sse"
    type: "sse"

a2a_peers:
  - name: "agent_provider"
    url: "http://agent-provider:8000"
    capabilities: ["premium_service"]
"""
        )
        config = load_agent_config(path)
        self.assertEqual(set(config.mcp_servers), {"local-mcp", "extra-mcp"})
        self.assertEqual(config.mcp_servers["extra-mcp"]["type"], "sse")
        self.assertEqual(len(config.a2a_peers), 1)
        self.assertEqual(config.a2a_peers[0]["name"], "agent_provider")

    def test_missing_file_returns_empty_config(self):
        config = load_agent_config("/nonexistent/agent_config.yaml")
        self.assertEqual(config, AgentConfig())

    def test_malformed_entries_are_skipped(self):
        path = self._write_config(
            """
mcp_servers:
  - url: "http://no-name:8000"
  - name: "good"
    url: "http://good:8000/mcp"
"""
        )
        config = load_agent_config(path)
        self.assertEqual(set(config.mcp_servers), {"good"})

    def test_empty_file(self):
        path = self._write_config("")
        config = load_agent_config(path)
        self.assertEqual(config, AgentConfig())


class TestLitellmModelName(unittest.TestCase):
    def test_gemini_gets_prefixed(self):
        self.assertEqual(get_litellm_model_name("gemini-2.5-flash"), "gemini/gemini-2.5-flash")

    def test_prefixed_gemini_unchanged(self):
        self.assertEqual(get_litellm_model_name("gemini/gemini-2.5-flash"), "gemini/gemini-2.5-flash")

    def test_other_models_unchanged(self):
        self.assertEqual(get_litellm_model_name("openai/gpt-4o"), "openai/gpt-4o")
        self.assertEqual(get_litellm_model_name("claude-3-opus"), "claude-3-opus")


if __name__ == "__main__":
    unittest.main()
