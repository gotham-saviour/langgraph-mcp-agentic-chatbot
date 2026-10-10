"""Unit tests for LangGraph topology and configuration using standard library unittest."""

import unittest
from src.backend import graph, chatbot, tools, ChatState


class TestGraphTopology(unittest.TestCase):
    def test_graph_nodes(self):
        node_names = set(graph.nodes.keys())
        self.assertIn("chat_node", node_names)
        self.assertIn("tools", node_names)

    def test_compiled_chatbot(self):
        self.assertIsNotNone(chatbot)
        self.assertIn("messages", ChatState.__annotations__)

    def test_tools_registered(self):
        tool_names = [t.name for t in tools]
        self.assertTrue(
            any("search" in t.name.lower() or "duckduckgo" in t.name.lower() for t in tools),
            "Search tool should be registered",
        )
        self.assertIn("calculator", tool_names)


if __name__ == "__main__":
    unittest.main()
