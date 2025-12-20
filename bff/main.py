import json
import os
import uuid
import httpx
from fastapi import FastAPI, Request, Form
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

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
        
        session_url = f"{AGENT_URL}/apps/dak_agent/users/bff_user/sessions/{current_session_id}"
        headers = {
            "Content-Type": "application/json",
            "X-User-ID": "bff_user",
            "X-Session-ID": current_session_id
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                # Check if session exists
                resp = await client.get(session_url, headers=headers)
                if resp.status_code != 200:
                    # Create session
                    create_url = f"{AGENT_URL}/apps/dak_agent/users/bff_user/sessions"
                    # We can try to pass the session_id we want, but the server might generate one.
                    # Let's try to pass it in the body if the API supports it, or just use what's returned.
                    # The CLI sends empty dict.
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
            "user_id": "bff_user", # Simplified user ID
            "session_id": current_session_id,
            "new_message": {
                "parts": [{"text": prompt}]
            }
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # We try to stream, but if ADK doesn't support it, we'll get the whole response
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    
                    full_text = ""
                    
                    # If the response is chunked/streaming
                    async for chunk in response.aiter_bytes():
                        # This is a bit naive for JSON parsing if it's not line-delimited
                        # But let's see what we get. 
                        # If ADK returns a single JSON object, we might get it in chunks.
                        # For now, let's accumulate and try to parse, OR if it's NDJSON.
                        # The standard ADK seems to return a JSON Array [ ... events ... ]
                        
                        # If we can't stream properly, we might just have to wait for the full response
                        # But let's try to handle it.
                        pass
                    
                    # Actually, since we know ADK might return a big JSON array, 
                    # streaming that is hard without a proper parser.
                    # Let's fallback to non-streaming request for safety first, 
                    # then we can optimize for streaming if we see it supports it.
                    pass
            
            # Non-streaming fallback for now to ensure correctness
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                print(f"DEBUG: Agent response: {json.dumps(data)}", flush=True)
                
                # Remove loading indicator
                yield '<div id="loading-indicator" hx-swap-oob="true"></div>\n'
                
                # Parse response into Thoughts and Final Answer
                thoughts = []
                response_text = ""
                
                if isinstance(data, list):
                    for event in data:
                        if "content" in event and "parts" in event["content"]:
                            for part in event["content"]["parts"]:
                                # 1. Direct Text (Model thought or answer)
                                if "text" in part:
                                    # Heuristic: If it's a short text before a tool call, it might be a thought.
                                    # But usually model text is the answer or explanation.
                                    # For now, treat all text as part of the answer unless we want to be very specific.
                                    # Actually, let's treat text as answer.
                                    response_text += part["text"]
                                
                                # 2. Tool Calls (Thoughts/Actions)
                                elif "functionCall" in part:
                                    fc = part["functionCall"]
                                    name = fc.get("name", "unknown")
                                    args = json.dumps(fc.get("args", {}))
                                    thoughts.append(f'<div class="thought-item"><span class="thought-label">Action:</span> Called <strong>{name}</strong> with {args}</div>')
                                
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
                                        thoughts.append(f'<div class="thought-item"><span class="thought-label">Observation:</span> {name} returned: {result}</div>')

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
            yield f'<div class="chat-message error">Error: {str(e)}</div>\n'
            yield '<div id="loading-indicator" hx-swap-oob="true"></div>\n'

    return StreamingResponse(event_generator(), media_type="text/html")
