import unittest
from unittest.mock import patch, mock_open, MagicMock, AsyncMock
import os
import sys
import subprocess

# Add parent directory to path to import main
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


class TestMCPTools(unittest.IsolatedAsyncioTestCase):
    """Test suite for MCP server tools."""

    async def test_deep_think(self):
        """Test deep_think tool returns the thought."""
        thought = "This is a deep thought"
        result = await main.deep_think(thought)
        self.assertEqual(result, thought)

    async def test_read_file_success(self):
        """Test read_file successfully reads file content."""
        test_content = "File content here"
        
        with patch('builtins.open', mock_open(read_data=test_content)):
            result = await main.read_file("/test/path.txt")
            self.assertEqual(result, test_content)

    async def test_read_file_error(self):
        """Test read_file handles errors gracefully."""
        with patch('builtins.open', side_effect=FileNotFoundError("File not found")):
            result = await main.read_file("/nonexistent/path.txt")
            self.assertIn("Error reading file", result)

    async def test_write_file_success(self):
        """Test write_file successfully writes content."""
        test_content = "Test content"
        test_path = "/test/path.txt"
        
        with patch('builtins.open', mock_open()) as mock_file:
            with patch('os.makedirs') as mock_makedirs:
                result = await main.write_file(test_path, test_content)
                
                mock_makedirs.assert_called_once()
                mock_file.assert_called_once_with(test_path, "w", encoding="utf-8")
                self.assertIn("Successfully wrote", result)

    async def test_write_file_error(self):
        """Test write_file handles errors gracefully."""
        with patch('builtins.open', side_effect=PermissionError("Permission denied")):
            result = await main.write_file("/test/path.txt", "content")
            self.assertIn("Error writing file", result)

    async def test_list_files_success(self):
        """Test list_files returns directory contents."""
        mock_items = ["file1.txt", "file2.py", "dir1"]
        
        with patch('os.listdir', return_value=mock_items):
            result = await main.list_files("/test/dir")
            
            for item in mock_items:
                self.assertIn(item, result)

    async def test_list_files_error(self):
        """Test list_files handles errors gracefully."""
        with patch('os.listdir', side_effect=FileNotFoundError("Directory not found")):
            result = await main.list_files("/nonexistent/dir")
            self.assertIn("Error listing files", result)

    async def test_run_command_success(self):
        """Test run_command executes commands successfully."""
        mock_result = MagicMock()
        mock_result.stdout = "Command output"
        mock_result.stderr = ""
        
        with patch('subprocess.run', return_value=mock_result):
            result = await main.run_command("echo test")
            
            self.assertIn("Command output", result)
            self.assertIn("Stdout:", result)

    async def test_run_command_with_stderr(self):
        """Test run_command includes stderr in output."""
        mock_result = MagicMock()
        mock_result.stdout = "Output"
        mock_result.stderr = "Error message"
        
        with patch('subprocess.run', return_value=mock_result):
            result = await main.run_command("test command")
            
            self.assertIn("Output", result)
            self.assertIn("Error message", result)
            self.assertIn("Stderr:", result)

    async def test_run_command_timeout(self):
        """Test run_command handles timeout."""
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired("cmd", 60)):
            result = await main.run_command("long_command")
            self.assertIn("timed out", result)

    async def test_run_command_error(self):
        """Test run_command handles general errors."""
        with patch('subprocess.run', side_effect=Exception("Command failed")):
            result = await main.run_command("bad_command")
            self.assertIn("Error executing command", result)

    async def test_search_files_success(self):
        """Test search_files finds matching files."""
        # Mock os.walk to simulate directory structure
        mock_walk_data = [
            ("/test", ["subdir"], ["file1.py", "file2.txt"]),
            ("/test/subdir", [], ["file3.py", "README.md"])
        ]
        
        with patch('os.walk', return_value=mock_walk_data):
            result = await main.search_files("*.py", "/test")
            
            self.assertIn("file1.py", result)
            self.assertIn("file3.py", result)
            self.assertNotIn("file2.txt", result)
            self.assertNotIn("README.md", result)

    async def test_search_files_error(self):
        """Test search_files handles errors gracefully."""
        with patch('os.walk', side_effect=PermissionError("Permission denied")):
            result = await main.search_files("*.py", "/test")
            self.assertIn("Error searching files", result)

    async def test_planner(self):
        """Test planner formats plan correctly."""
        task = "Implement new feature"
        steps = ["Step 1", "Step 2", "Step 3"]
        complexity = "moderate"
        
        result = await main.planner(task, steps, complexity)
        
        self.assertIn(task, result)
        self.assertIn(complexity, result)
        self.assertIn("1. Step 1", result)
        self.assertIn("2. Step 2", result)
        self.assertIn("3. Step 3", result)

    async def test_planner_complex(self):
        """Test planner with complex task."""
        task = "Build distributed system"
        steps = ["Design architecture", "Implement core", "Add monitoring", "Deploy"]
        complexity = "complex"
        
        result = await main.planner(task, steps, complexity)
        
        self.assertIn("complex", result)
        self.assertEqual(len([line for line in result.split('\n') if line.strip().startswith(tuple('1234'))]), 4)


if __name__ == '__main__':
    unittest.main()
