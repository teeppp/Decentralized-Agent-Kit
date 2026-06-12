import unittest
from unittest.mock import MagicMock

from dak_agent.builtin_tools import (
    ask_question,
    attempt_answer,
    make_builtin_tools,
    planner,
    switch_mode,
)


class TestBuiltinTools(unittest.TestCase):
    def test_make_builtin_tools_default(self):
        tools = make_builtin_tools(enforcer_mode=False)
        names = [t.name for t in tools]
        self.assertEqual(names, ["planner", "switch_mode"])

    def test_make_builtin_tools_enforcer(self):
        tools = make_builtin_tools(enforcer_mode=True)
        names = [t.name for t in tools]
        self.assertEqual(names, ["planner", "switch_mode", "attempt_answer", "ask_question"])

    def test_planner_formats_plan(self):
        result = planner("My task", ["step one", "step two"], allowed_tools=["read_file"])
        self.assertIn("My task", result)
        self.assertIn("1. step one", result)
        self.assertIn("2. step two", result)
        self.assertIn("Ulysses Pact Active", result)
        self.assertIn("read_file", result)

    def test_planner_without_restriction(self):
        result = planner("My task", ["step one"])
        self.assertNotIn("Ulysses Pact", result)

    def test_switch_mode_message(self):
        result = switch_mode(reason="too much context", new_focus="coding")
        self.assertIn("too much context", result)
        self.assertIn("coding", result)

    def test_attempt_answer_ends_invocation(self):
        tool_context = MagicMock()
        result = attempt_answer("42", "high", ["deep_think"], tool_context)
        self.assertTrue(tool_context._invocation_context.end_invocation)
        self.assertIn("42", result)
        self.assertIn("high", result)
        self.assertIn("deep_think", result)

    def test_ask_question_ends_invocation(self):
        tool_context = MagicMock()
        result = ask_question(["What OS?"], "Need environment info", tool_context)
        self.assertTrue(tool_context._invocation_context.end_invocation)
        self.assertIn("What OS?", result)
        self.assertIn("Need environment info", result)


if __name__ == "__main__":
    unittest.main()
