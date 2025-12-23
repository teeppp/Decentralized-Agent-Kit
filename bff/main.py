import json
import os
import uuid
import httpx
import logging
from fastapi import FastAPI, Request, Form
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# ADK Agent URL
AGENT_URL = os.getenv("AGENT_URL", "http://agent:8000")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # Generate a session ID for this page load
    session_id = f"session_bff_{uuid.uuid4()}"
    return templates.TemplateResponse("index.html", {"request": request, "session_id": session_id})

@app.post("/chat")
async def chat(request: Request, prompt: str = Form(...), session_id: str = Form(...)):
    
    async def event_generator():
        # 1. Send user message to UI immediately
        yield f'<div class="chat-message user"><div class="message-content">{prompt}</div></div>\n'
        
        # 2. Send loading indicator
        yield '<div id="loading-indicator" class="chat-message system">Thinking...</div>\n'

        # 2.5. Ensure Session Exists
        # Use a local variable for the session ID to use in calls, initialized from the argument
        current_session_id = session_id
        # Use a unique user ID per session to ensure fresh state (wallet, memory)
        current_user_id = f"user_{current_session_id}"
        
        session_url = f"{AGENT_URL}/apps/dak_agent/users/{current_user_id}/sessions/{current_session_id}"
        headers = {
            "Content-Type": "application/json",
            "X-User-ID": current_user_id,
            "X-Session-ID": current_session_id
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                # Check if session exists
                resp = await client.get(session_url, headers=headers)
                if resp.status_code != 200:
                    # Create session
                    create_url = f"{AGENT_URL}/apps/dak_agent/users/{current_user_id}/sessions"
                    create_resp = await client.post(create_url, json={"id": current_session_id}, headers=headers)
                    if create_resp.status_code == 200:
                         data = create_resp.json()
                         if "id" in data:
                             current_session_id = data["id"]
                             # Update headers with new session ID
                             headers["X-Session-ID"] = current_session_id
            except Exception as e:
                yield f'<div class="chat-message error">Session Error: {str(e)}</div>\n'
                return

        # 3. Call ADK Agent
        url = f"{AGENT_URL}/run"
        payload = {
            "app_name": "dak_agent",
            "user_id": current_user_id,
            "session_id": current_session_id,
            "new_message": {
                "parts": [{"text": prompt}]
            }
        }

        try:
            # Non-streaming fallback for now to ensure correctness
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                logger.info(f"Agent response type: {type(data)}")
                logger.info(f"Agent response content: {json.dumps(data)[:500]}...")
                
                # Remove loading indicator
                yield '<div id="loading-indicator" hx-swap-oob="true"></div>\n'
                
                # Parse response into Thoughts and Final Answer
                thoughts = []
                response_text = ""
                
                # Normalize data to list
                events = data if isinstance(data, list) else [data]
                
                for event in events:
                    # Handle standard ADK event format
                    if "content" in event and "parts" in event["content"]:
                        for part in event["content"]["parts"]:
                            # 1. Direct Text (Model thought or answer)
                            if "text" in part:
                                response_text += part["text"]
                            
                            # 2. Tool Calls (Thoughts/Actions)
                            elif "functionCall" in part:
                                fc = part["functionCall"]
                                name = fc.get("name", "unknown")
                                args = json.dumps(fc.get("args", {}))
                                thoughts.append(f'<div class="thought-item"><span class="thought-label">Action:</span> Called <strong>{name}</strong></div>')
                                thoughts.append(f'<div class="thought-args">{args}</div>')
                            
                            # 3. Tool Responses (Observations)
                            elif "functionResponse" in part:
                                func_resp = part["functionResponse"]
                                name = func_resp.get("name", "unknown")
                                
                                # Special handling for user-facing tools
                                if name in ["ask_question", "attempt_answer"]:
                                    if "response" in func_resp and "result" in func_resp["response"]:
                                        response_text += str(func_resp["response"]["result"]) + "\n"
                                else:
                                    # Internal tool results go to thoughts
                                    result = "No result"
                                    if "response" in func_resp:
                                        result = json.dumps(func_resp["response"])
                                    
                                    # Highlight Payment Errors
                                    if "Payment Required" in result:
                                        thoughts.append(f'<div class="thought-item error"><span class="thought-label">System:</span> <strong>Payment Required</strong></div>')
                                    
                                    thoughts.append(f'<div class="thought-item"><span class="thought-label">Observation:</span> {name} returned: {result[:200]}...</div>')

                # Construct HTML
                html_output = '<div class="chat-message assistant">'
                
                # Add Thoughts block if exists
                if thoughts:
                    html_output += f'''
                    <details class="thoughts">
                        <summary>Thinking Process ({len(thoughts)} steps)</summary>
                        <div class="thought-content">
                            {"".join(thoughts)}
                        </div>
                    </details>
                    '''
                
                # Add Final Answer
                html_output += f'<div class="message-content">{response_text}</div>'
                html_output += '</div>\n'
                
                yield html_output

        except Exception as e:
            logger.error(f"Error in chat: {e}")
            yield f'<div class="chat-message error">Error: {str(e)}</div>\n'
            yield '<div id="loading-indicator" hx-swap-oob="true"></div>\n'

    return StreamingResponse(event_generator(), media_type="text/html")
