import requests
from typing import Dict, Any, Optional
import time
import uuid
from .config import ConfigManager

class AgentClient:
    def __init__(self, session_id: Optional[str] = None):
        self.config = ConfigManager()
        self.base_url = self.config.get_agent_url()
        self.username = self.config.get_user()
        
        if session_id:
            self.session_id = session_id
        elif self.username:
            # Generate a unique session ID if not provided
            # Format: session_{username}_{uuid}
            self.session_id = f"session_{self.username}_{uuid.uuid4()}"
        else:
            self.session_id = str(uuid.uuid4())

    def reset_session(self):
        """Regenerate a new session ID."""
        if self.username:
            self.session_id = f"session_{self.username}_{uuid.uuid4()}"
        else:
            self.session_id = str(uuid.uuid4())

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.username:
            headers["X-User-ID"] = self.username
            if self.session_id:
                headers["X-Session-ID"] = self.session_id
        return headers

    def _ensure_session(self):
        """Ensure session exists, create if needed."""
        if not self.username:
            raise ValueError("Not logged in. Please run 'dak-cli login' first.")
        
        # Try to get session info to check if it exists
        try:
            response = requests.get(
                f"{self.base_url}/apps/dak_agent/users/{self.username}/sessions/{self.session_id}",
                headers=self._get_headers(),
                timeout=5
            )
            if response.status_code == 200:
                return  # Session exists
        except:
            pass
        
        # Session doesn't exist, create it
        try:
            response = requests.post(
                f"{self.base_url}/apps/dak_agent/users/{self.username}/sessions",
                json={},
                headers=self._get_headers(),
                timeout=10
            )
            response.raise_for_status()
            session_data = response.json()
            self.session_id = session_data.get("id", self.session_id)
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to create session: {e}")


    def run_task(self, prompt: str, permissions: Dict[str, str] = None, tool_approval: Dict = None) -> Dict[str, Any]:
        if not self.username:
            raise ValueError("Not logged in. Please run 'dak-cli login' first.")

        # Ensure session exists
        self._ensure_session()

        # ADK standard API schema
        payload = {
            "app_name": "dak_agent",
            "user_id": self.username,
            "session_id": self.session_id,
        }

        # If this is a tool approval response, construct the FunctionResponse payload
        if tool_approval:
            # We need the invocationId from the original request
            if "invocation_id" in tool_approval:
                payload["invocationId"] = tool_approval["invocation_id"]
            
            # Construct the function response for adk_request_confirmation
            payload["new_message"] = {
                "parts": [
                    {
                        "functionResponse": {
                            "id": tool_approval.get("tool_call_id"),
                            "name": "adk_request_confirmation",
                            "response": {
                                "confirmed": tool_approval.get("approved", False)
                            }
                        }
                    }
                ]
            }
        else:
            # Standard text prompt
            payload["new_message"] = {
                "parts": [{"text": prompt}]
            }

        try:
            response = requests.post(
                f"{self.base_url}/run",
                json=payload,
                headers=self._get_headers(),
                timeout=300
            )
            response.raise_for_status()
            response_data = response.json()
            
            # Check for tool confirmation requests in the response
            if isinstance(response_data, list):
                for event in response_data:
                    # Look for adk_request_confirmation tool call
                    for part in event.get("content", {}).get("parts", []):
                        if "functionCall" in part:
                            fc = part["functionCall"]
                            if fc.get("name") == "adk_request_confirmation":
                                # Found a confirmation request
                                original_fc = fc.get("args", {}).get("originalFunctionCall", {})
                                return {
                                    "status": "needs_approval",
                                    "tool_call": {
                                        "tool_name": original_fc.get("name"),
                                        "tool_args": original_fc.get("args"),
                                        "tool_call_id": fc.get("id"), # ID of the confirmation request
                                        "invocation_id": event.get("invocationId")
                                    },
                                    "response": response_data # Return full response for context if needed
                                }
            
            return response_data
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to communicate with agent: {e}")

    def list_sessions(self) -> Dict[str, Any]:
        if not self.username:
            raise ValueError("Not logged in. Please run 'dak-cli login' first.")
        
        try:
            # ADK standard: GET /apps/{app}/users/{user}/sessions
            response = requests.get(
                f"{self.base_url}/apps/dak_agent/users/{self.username}/sessions",
                headers=self._get_headers(),
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to list sessions: {e}")

    def get_session_history(self, session_id: str) -> Dict[str, Any]:
        if not self.username:
            raise ValueError("Not logged in. Please run 'dak-cli login' first.")
        
        try:
            # ADK standard: GET /apps/{app}/users/{user}/sessions/{session}
            response = requests.get(
                f"{self.base_url}/apps/dak_agent/users/{self.username}/sessions/{session_id}",
                headers=self._get_headers(),
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to get session history: {e}")

    def delete_session(self, session_id: str) -> Dict[str, Any]:
        if not self.username:
            raise ValueError("Not logged in. Please run 'dak-cli login' first.")
        
        try:
            # ADK standard: DELETE /apps/{app}/users/{user}/sessions/{session}
            response = requests.delete(
                f"{self.base_url}/apps/dak_agent/users/{self.username}/sessions/{session_id}",
                headers=self._get_headers(),
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to delete session: {e}")
