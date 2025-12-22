import os
import json
import httpx
import asyncio
from typing import List, Dict, Any, Optional

# Configuration
AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8000")
USER_ID = "eval_user"

class ApiClient:
    def __init__(self, base_url: str = AGENT_URL):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)

    async def create_session(self) -> str:
        """Creates a new session and returns the session_id."""
        url = f"{self.base_url}/apps/dak_agent/users/{USER_ID}/sessions"
        headers = {"X-User-ID": USER_ID}
        # The API might generate an ID if we don't provide one, or we can provide one.
        # Let's try to create one without providing an ID first to let server decide,
        # or provide a random one if needed.
        # Based on BFF code, it posts to /sessions.
        try:
            resp = await self.client.post(url, json={}, headers=headers)
            if resp.status_code == 200:
                return resp.json()["id"]
            # Fallback: generate one locally if server allows arbitrary IDs (BFF does this)
            import uuid
            session_id = f"eval_{uuid.uuid4()}"
            # Ensure it exists/create it
            await self.client.post(url, json={"id": session_id}, headers=headers)
            return session_id
        except Exception as e:
            print(f"Error creating session: {e}")
            # Fallback
            import uuid
            return f"eval_{uuid.uuid4()}"

    async def send_message(self, session_id: str, content: str) -> List[Dict[str, Any]]:
        """Sends a message to the agent and returns the list of response events."""
        url = f"{self.base_url}/run"
        headers = {
            "Content-Type": "application/json",
            "X-User-ID": USER_ID,
            "X-Session-ID": session_id
        }
        payload = {
            "app_name": "dak_agent",
            "user_id": USER_ID,
            "session_id": session_id,
            "new_message": {
                "parts": [{"text": content}]
            }
        }
        
        try:
            resp = await self.client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            events = resp.json()
            handled_ids = set()
            
            # Auto-confirmation loop
            while True:
                confirmation_id = None
                for event in events:
                    if "content" in event and "parts" in event["content"]:
                        for part in event["content"]["parts"]:
                            if "functionCall" in part:
                                fc = part["functionCall"]
                                if fc.get("name") == "adk_request_confirmation":
                                    cid = fc.get("id")
                                    if cid not in handled_ids:
                                        confirmation_id = cid
                                        break
                    if confirmation_id:
                        break
                
                if confirmation_id:
                    print(f"DEBUG: Auto-confirming tool call {confirmation_id}")
                    handled_ids.add(confirmation_id)
                    confirm_payload = {
                        "app_name": "dak_agent",
                        "user_id": USER_ID,
                        "session_id": session_id,
                        "new_message": {
                            "parts": [{
                                "functionResponse": {
                                    "name": "adk_request_confirmation",
                                    "id": confirmation_id,
                                    "response": {
                                        "confirmed": True
                                    }
                                }
                            }]
                        }
                    }
                    
                    resp = await self.client.post(url, json=confirm_payload, headers=headers)
                    resp.raise_for_status()
                    new_events = resp.json()
                    events.extend(new_events)
                else:
                    break
            
            return events
        except Exception as e:
            print(f"Error sending message: {e}")
            return []

    async def close(self):
        await self.client.aclose()

class Assertor:
    @staticmethod
    def get_text_from_response(events: List[Dict[str, Any]]) -> str:
        text = ""
        if not isinstance(events, list):
            return ""
        for event in events:
            if "content" in event and "parts" in event["content"]:
                for part in event["content"]["parts"]:
                    if "text" in part:
                        text += part["text"]
                    elif "functionCall" in part:
                        fc = part["functionCall"]
                        name = fc.get("name")
                        args = fc.get("args", {})
                        if name == "attempt_answer" and "answer" in args:
                            text += args["answer"]
                        elif name == "ask_question" and "question" in args:
                            text += args["question"]
                    elif "functionResponse" in part:
                        fr = part["functionResponse"]
                        name = fr.get("name")
                        # Optional: also check functionResponse if needed, but functionCall is the source
                        # BFF uses functionResponse, but functionCall is more direct from model.
                        # Let's stick to functionCall for the "text" content.
                        pass
        return text

    @staticmethod
    def get_tool_calls(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        calls = []
        if not isinstance(events, list):
            return []
        for event in events:
            if "content" in event and "parts" in event["content"]:
                for part in event["content"]["parts"]:
                    if "functionCall" in part:
                        calls.append(part["functionCall"])
        return calls

    @staticmethod
    def check_text_match(events: List[Dict[str, Any]], keyword: str) -> bool:
        text = Assertor.get_text_from_response(events)
        return keyword in text

    @staticmethod
    def check_tool_call(events: List[Dict[str, Any]], tool_name: str, args_contains: Optional[Dict[str, Any]] = None) -> bool:
        calls = Assertor.get_tool_calls(events)
        for call in calls:
            if call.get("name") == tool_name:
                if args_contains:
                    call_args = call.get("args", {})
                    # Check if all key-values in args_contains are present in call_args
                    match = True
                    for k, v in args_contains.items():
                        if k not in call_args or call_args[k] != v:
                            match = False
                            break
                    if match:
                        return True
                else:
                    return True
        return False

    @staticmethod
    async def check_semantic(events: List[Dict[str, Any]], instruction: str, context: Optional[str] = None) -> tuple[bool, str]:
        """
        Uses an LLM (Gemini) to verify the response against an instruction.
        Requires GOOGLE_API_KEY or GEMINI_API_KEY.
        Returns (is_pass, reasoning).
        """
        text = Assertor.get_text_from_response(events)
        if not text:
            return False, "No text response from agent."

        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("Warning: GOOGLE_API_KEY or GEMINI_API_KEY not found, skipping semantic check.")
            return False, "Skipped (No API Key)"

        # Gemini API usage via REST
        # Model: gemini-3-pro-preview (User requested)
        model = "gemini-3-pro-preview" 
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        
        prompt = f"""You are an expert evaluator for an AI agent.
Your task is to evaluate if the Agent's response meets the Requirement given the Context.

Context:
{context if context else "N/A"}

Requirement:
{instruction}

Agent Response:
{text}

Evaluate the response.
1. Is it correct/satisfactory? (YES/NO)
2. Provide a brief reasoning in JAPANESE.

Format:
REASONING: [Your explanation in Japanese]
RESULT: [YES or NO]
"""

        for attempt in range(3):
            try:
                async with httpx.AsyncClient() as client:
                    payload = {
                        "contents": [{
                            "parts": [{
                                "text": prompt
                            }]
                        }],
                        "generationConfig": {
                            "temperature": 0.0
                        }
                    }
                    
                    response = await client.post(url, json=payload, timeout=30.0)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if "candidates" in data and data["candidates"]:
                            content = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                            
                            # Parse result
                            is_pass = "RESULT: YES" in content
                            reasoning = content
                            
                            return is_pass, reasoning
                        else:
                            print(f"Attempt {attempt+1} failed: No candidates. {data}")
                    else:
                        print(f"Attempt {attempt+1} failed: API {response.status_code} - {response.text}")
                        
                    await asyncio.sleep(2) # Wait before retry
            except Exception as e:
                print(f"Attempt {attempt+1} error: {repr(e)}")
                await asyncio.sleep(2)
                
        return False, "Failed after 3 attempts."
