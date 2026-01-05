import logging
import os
import time
from langfuse import Langfuse

logger = logging.getLogger(__name__)

class LangfuseVerifier:
    def __init__(self):
        self.public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        self.secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        self.host = os.getenv("LANGFUSE_HOST")
        
        if not (self.public_key and self.secret_key and self.host):
            logger.warning("Langfuse credentials missing. Verification will be skipped (mock pass).")
            self.client = None
        else:
            self.client = Langfuse(
                public_key=self.public_key,
                secret_key=self.secret_key,
                host=self.host
            )

    def verify_trace(self, session_id: str, retries=3, delay=2) -> bool:
        if not self.client:
            return True # Skip verification if no creds

        logger.info(f"Querying Langfuse for session: {session_id}")
        
        for i in range(retries):
            try:
                # Note: Langfuse SDK might not have a direct 'get_traces_by_session' method exposed easily 
                # in the lightweight client, or it might be async. 
                # We often need to use the API directly or the fetch_traces method if available.
                # For this implementation, we'll assume a simple check or use the API via requests if SDK fails.
                
                # Using low-level API fetch if SDK doesn't support easy query
                # Actually, standard Langfuse client is for ingestion. 
                # For verification, we usually need to query the API.
                
                # Let's try a simple API request using the host/keys
                import requests
                from requests.auth import HTTPBasicAuth
                
                api_url = f"{self.host}/api/public/traces?sessionId={session_id}"
                response = requests.get(
                    api_url, 
                    auth=HTTPBasicAuth(self.public_key, self.secret_key)
                )
                
                if response.status_code == 200:
                    data = response.json()
                    traces = data.get("data", [])
                    if traces:
                        logger.info(f"Found {len(traces)} traces for session {session_id}")
                        return True
                
            except Exception as e:
                logger.warning(f"Error querying Langfuse: {e}")
            
            time.sleep(delay)
            
        logger.error(f"No traces found for session {session_id} after {retries} retries.")
        return False
