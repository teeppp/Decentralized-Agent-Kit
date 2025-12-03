import unittest
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner

from src.main import app


class TestCLICommands(unittest.TestCase):
    def setUp(self):
        """Set up test environment."""
        self.runner = CliRunner()

    @patch('src.main.config_manager')
    def test_login_command(self, mock_config_manager):
        """Test login command."""
        result = self.runner.invoke(app, [
            "login",
            "--username", "test_user",
            "--agent-url", "http://test:8000"
        ])
        
        self.assertEqual(result.exit_code, 0)
        mock_config_manager.set_user.assert_called_once_with("test_user")
        mock_config_manager.set_agent_url.assert_called_once_with("http://test:8000")
        self.assertIn("Successfully logged in", result.stdout)

    @patch('src.main.config_manager')
    def test_config_command(self, mock_config_manager):
        """Test config command displays current settings."""
        mock_config_manager.get_user.return_value = "test_user"
        mock_config_manager.get_agent_url.return_value = "http://test:8000"
        
        result = self.runner.invoke(app, ["config"])
        
        self.assertEqual(result.exit_code, 0)
        self.assertIn("test_user", result.stdout)
        self.assertIn("http://test:8000", result.stdout)

    @patch('src.main.AgentClient')
    @patch('src.main.config_manager')
    def test_run_command_success(self, mock_config_manager, mock_client_class):
        """Test run command with successful response."""
        mock_config_manager.get_user.return_value = "test_user"
        
        # Mock client
        mock_client = MagicMock()
        mock_client.run_task.return_value = [{
            "content": {
                "role": "model",
                "parts": [{"text": "Test response"}]
            }
        }]
        mock_client_class.return_value = mock_client
        
        result = self.runner.invoke(app, ["run", "test prompt"])
        
        self.assertEqual(result.exit_code, 0)
        mock_client.run_task.assert_called_once()
        self.assertIn("Test response", result.stdout)

    @patch('src.main.AgentClient')
    @patch('src.main.config_manager')
    def test_run_command_error(self, mock_config_manager, mock_client_class):
        """Test run command handles errors gracefully."""
        mock_config_manager.get_user.return_value = "test_user"
        
        # Mock client to raise error
        mock_client = MagicMock()
        mock_client.run_task.side_effect = Exception("Connection error")
        mock_client_class.return_value = mock_client
        
        result = self.runner.invoke(app, ["run", "test prompt"])
        
        self.assertEqual(result.exit_code, 0)  # Typer commands succeed even with handled exceptions
        self.assertIn("Error", result.stdout)


if __name__ == '__main__':
    unittest.main()
