import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from dak_agent.skill_tools import (
    WALLET_TOOL_NAMES,
    load_local_tools_from_skill,
    load_solana_wallet_tools,
    make_mcp_toolset,
)


class TestLoadLocalToolsFromSkill(unittest.TestCase):
    def setUp(self):
        self.skill_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.skill_dir)

    def _write_tools_py(self, content: str):
        with open(os.path.join(self.skill_dir, "tools.py"), "w") as f:
            f.write(content)

    def test_no_tools_py_falls_back_to_mcp(self):
        tools, mcp_fallback = load_local_tools_from_skill(
            "myskill", self.skill_dir, ["tool_a", "tool_b"], current_tool_names=[]
        )
        self.assertEqual(tools, [])
        self.assertEqual(mcp_fallback, ["tool_a", "tool_b"])

    def test_loads_callable_tools(self):
        self._write_tools_py(
            "def tool_a(x: str) -> str:\n"
            "    \"\"\"Tool A.\"\"\"\n"
            "    return x\n"
        )
        tools, mcp_fallback = load_local_tools_from_skill(
            "myskill_loads", self.skill_dir, ["tool_a", "tool_b"], current_tool_names=[]
        )
        self.assertEqual([t.name for t in tools], ["tool_a"])
        self.assertEqual(mcp_fallback, ["tool_b"])

    def test_skips_already_present_tools(self):
        self._write_tools_py(
            "def tool_a(x: str) -> str:\n"
            "    \"\"\"Tool A.\"\"\"\n"
            "    return x\n"
        )
        tools, mcp_fallback = load_local_tools_from_skill(
            "myskill_present", self.skill_dir, ["tool_a"], current_tool_names=["tool_a"]
        )
        self.assertEqual(tools, [])
        self.assertEqual(mcp_fallback, [])

    def test_non_callable_falls_back(self):
        self._write_tools_py("tool_a = 42\n")
        tools, mcp_fallback = load_local_tools_from_skill(
            "myskill_noncallable", self.skill_dir, ["tool_a"], current_tool_names=[]
        )
        self.assertEqual(tools, [])
        self.assertEqual(mcp_fallback, ["tool_a"])

    def test_broken_module_falls_back(self):
        self._write_tools_py("raise RuntimeError('boom')\n")
        tools, mcp_fallback = load_local_tools_from_skill(
            "myskill_broken", self.skill_dir, ["tool_a"], current_tool_names=[]
        )
        self.assertEqual(tools, [])
        self.assertEqual(mcp_fallback, ["tool_a"])


class TestMakeMcpToolset(unittest.TestCase):
    @patch("dak_agent.skill_tools.McpToolset")
    def test_http_toolset(self, MockToolset):
        make_mcp_toolset("http://srv:8000/mcp", "http", ["tool_a"])
        kwargs = MockToolset.call_args.kwargs
        self.assertEqual(kwargs["tool_filter"], ["tool_a"])
        self.assertEqual(kwargs["connection_params"].url, "http://srv:8000/mcp")

    @patch("dak_agent.skill_tools.McpToolset")
    def test_sse_toolset(self, MockToolset):
        make_mcp_toolset("http://srv:8000/sse", "sse", None)
        kwargs = MockToolset.call_args.kwargs
        self.assertEqual(kwargs["connection_params"].url, "http://srv:8000/sse")
        self.assertEqual(type(kwargs["connection_params"]).__name__, "SseConnectionParams")


class TestLoadSolanaWalletTools(unittest.TestCase):
    def test_loads_wallet_tools(self):
        tools = load_solana_wallet_tools()
        self.assertEqual([t.name for t in tools], WALLET_TOOL_NAMES)

    def test_skips_existing(self):
        tools = load_solana_wallet_tools(existing_tool_names=["check_solana_balance"])
        names = [t.name for t in tools]
        self.assertNotIn("check_solana_balance", names)
        self.assertIn("send_sol_payment", names)


if __name__ == "__main__":
    unittest.main()
