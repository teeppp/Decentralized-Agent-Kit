import aiohttp
import logging
import json
import uuid

logger = logging.getLogger(__name__)

class BffClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    async def start_session(self) -> str:
        # BFF typically generates session ID on client side or via API
        # For this test, we'll generate a UUID
        return f"session_test_{str(uuid.uuid4())}"

    async def send_message(self, session_id: str, message: str) -> str:
        url = f"{self.base_url}/chat"
        
        # Use FormData to match curl -F behavior
        data = aiohttp.FormData()
        data.add_field('prompt', message)
        data.add_field('session_id', session_id)
        
        async with aiohttp.ClientSession() as session:
            # aiohttp automatically sets Content-Type to multipart/form-data when data is FormData
            async with session.post(url, data=data) as response:
                if response.status != 200:
                    text = await response.text()
                    logger.error(f"BFF Error {response.status}: {text}")
                    raise Exception(f"BFF returned status {response.status}")
                
                # Handle streaming response if necessary
                # The previous curl examples showed text/event-stream or similar
                # For simplicity, we'll accumulate text
                full_response = ""
                async for line in response.content:
                    decoded_line = line.decode('utf-8').strip()
                    if decoded_line:
                        # Simple parsing logic for now
                        full_response += decoded_line + "\n"
                
                return full_response
