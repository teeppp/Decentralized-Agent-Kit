import unittest
from unittest.mock import patch, MagicMock
import uuid

from src.client import AgentClient


class TestAgentClient(unittest.TestCase):
    def setUp(self):
        """Set up test environment."""
        self.mock_config = MagicMock()
        self.mock_config.get_agent_url.return_value = "http://test.example.com:8000"
        self.mock_config.get_user.return_value = "test_user"

    @patch('src.client.ConfigManager')
    def test_init_with_session_id(self, mock_config_class):
        """Test initialization with provided session ID."""
        mock_config_class.return_value = self.mock_config
        
        client = AgentClient(session_id="custom_session")
        
        self.assertEqual(client.session_id, "custom_session")
        self.assertEqual(client.username, "test_user")
        self.assertEqual(client.base_url, "http://test.example.com:8000")

    @patch('src.client.ConfigManager')
    def test_init_generates_session_id(self, mock_config_class):
        """Test that session ID is generated when not provided."""
        mock_config_class.return_value = self.mock_config
        
        client = AgentClient()
        
        self.assertTrue(client.session_id.startswith("session_test_user_"))
        self.assertIsNotNone(client.session_id)

    @patch('src.client.ConfigManager')
    def test_reset_session(self, mock_config_class):
        """Test session reset generates new ID."""
        mock_config_class.return_value = self.mock_config
        
        client = AgentClient()
        old_session = client.session_id
        client.reset_session()
        
        self.assertNotEqual(client.session_id, old_session)
        self.assertTrue(client.session_id.startswith("session_test_user_"))

    @patch('src.client.ConfigManager')
    def test_get_headers(self, mock_config_class):
        """Test header generation."""
        mock_config_class.return_value = self.mock_config
        
        client = AgentClient(session_id="test_session")
        headers = client._get_headers()
        
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["X-User-ID"], "test_user")
        self.assertEqual(headers["X-Session-ID"], "test_session")

    @patch('src.client.requests.post')
    @patch('src.client.requests.get')
    @patch('src.client.ConfigManager')
    def test_run_task_success(self, mock_config_class, mock_get, mock_post):
        """Test successful task execution."""
        mock_config_class.return_value = self.mock_config
        
        # Mock session check (exists)
        mock_get.return_value.status_code = 200
        
        # Mock task response
        mock_response = MagicMock()
        mock_response.json.return_value = [{"content": {"parts": [{"text": "Response"}]}}]
        mock_post.return_value = mock_response
        
        client = AgentClient()
        result = client.run_task("Test prompt")
        
        self.assertEqual(result, [{"content": {"parts": [{"text": "Response"}]}}])
        mock_post.assert_called_once()

    @patch('src.client.requests.post')
    @patch('src.client.requests.get')
    @patch('src.client.ConfigManager')
    def test_run_task_needs_approval(self, mock_config_class, mock_get, mock_post):
        """Test task requiring tool approval."""
        mock_config_class.return_value = self.mock_config
        
        # Mock session check (exists)
        mock_get.return_value.status_code = 200
        
        # Mock approval request response
        mock_response = MagicMock()
        mock_response.json.return_value = [{
            "invocationId": "inv_123",
            "content": {
                "parts": [{
                    "functionCall": {
                        "id": "fc_123",
                        "name": "adk_request_confirmation",
                        "args": {
                            "originalFunctionCall": {
                                "name": "test_tool",
                                "args": {"param": "value"}
                            }
                        }
                    }
                }]
            }
        }]
        mock_post.return_value = mock_response
        
        client = AgentClient()
        result = client.run_task("Test prompt")
        
        self.assertEqual(result["status"], "needs_approval")
        self.assertEqual(result["tool_call"]["tool_name"], "test_tool")

    @patch('src.client.ConfigManager')
    def test_run_task_not_logged_in(self, mock_config_class):
        """Test run_task raises error when not logged in."""
        mock_config = MagicMock()
        mock_config.get_user.return_value = None
        mock_config_class.return_value = mock_config
        
        client = AgentClient()
        
        with self.assertRaises(ValueError) as context:
            client.run_task("Test prompt")
        
        self.assertIn("Not logged in", str(context.exception))

    @patch('src.client.requests.get')
    @patch('src.client.ConfigManager')
    def test_list_sessions_success(self, mock_config_class, mock_get):
        """Test listing sessions."""
        mock_config_class.return_value = self.mock_config
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"sessions": ["session1", "session2"]}
        mock_get.return_value = mock_response
        
        client = AgentClient()
        result = client.list_sessions()
        
        self.assertEqual(result, {"sessions": ["session1", "session2"]})

    @patch('src.client.requests.delete')
    @patch('src.client.ConfigManager')
    def test_delete_session_success(self, mock_config_class, mock_delete):
        """Test deleting a session."""
        mock_config_class.return_value = self.mock_config
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "deleted"}
        mock_delete.return_value = mock_response
        
        client = AgentClient()
        result = client.delete_session("session_123")
        
        self.assertEqual(result, {"status": "deleted"})
        mock_delete.assert_called_once()


if __name__ == '__main__':
    unittest.main()
