import os
from langfuse import Langfuse
import json
from datetime import datetime

# Set credentials from environment (retrieved from container)
os.environ["LANGFUSE_PUBLIC_KEY"] = "pk-lf-aa7f4d39-cf42-473d-a1fe-b82556ab1f2f"
os.environ["LANGFUSE_SECRET_KEY"] = "sk-lf-3d2d94e7-2f70-41a2-b6a1-0fcc1dd1f261"
os.environ["LANGFUSE_HOST"] = "https://cloud.langfuse.com"

import requests
import base64

def analyze_traces():
    print("Initializing Langfuse API request...")
    
    # LangFuse API uses Basic Auth with public/secret keys
    auth = (os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"])
    host = os.environ["LANGFUSE_HOST"]
    
    # API Endpoint for traces
    url = f"{host}/api/public/traces"
    
    print(f"Fetching recent traces from {url}...")
    try:
        res = requests.get(url, auth=auth, params={"limit": 10, "orderBy": "timestamp.desc"})
        res.raise_for_status()
        data = res.json()
        traces = data.get('data', [])
        
        print(f"Found {len(traces)} traces.")
        
        for trace in traces:
            t_id = trace.get('id')
            t_time = trace.get('timestamp')
            
            input_data = trace.get('input', {})
            session_id = "N/A"
            if isinstance(input_data, dict):
                session_id = input_data.get('session_id', 'N/A')
                
            print(f"Trace: {t_id} | Time: {t_time} | Session: {session_id}")
            
            # Check for tool calls
            obs_url = f"{host}/api/public/observations"
            obs_res = requests.get(obs_url, auth=auth, params={"traceId": t_id})
            if obs_res.ok:
                observations = obs_res.json().get('data', [])
                for obs in observations:
                    if obs.get('type') == "TOOL":
                        print(f"  -> Tool: {obs.get('name')}")

    except Exception as e:
        print(f"Error fetching traces: {e}")
        if hasattr(e, 'response') and e.response:
             print(f"Response: {e.response.text}")

if __name__ == "__main__":
    analyze_traces()
