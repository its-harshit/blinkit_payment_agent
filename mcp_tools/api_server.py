"""FastAPI server exposing the UnifiedAgent as an HTTP API (with streaming)."""
import json
import logging
import os
import uuid
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .unified_agent import UnifiedAgent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Unified NPCI + Shopping Agent API", version="0.1.0")

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Vite default ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store agents per chat session
_chat_agents: dict[str, UnifiedAgent] = {}


class ChatRequest(BaseModel):
    """Incoming chat/message from frontend."""
    message: str
    chat_id: Optional[str] = None


class LoginRequest(BaseModel):
    """Login request with mobile number."""
    mobile_number: str


class VerifyOTPRequest(BaseModel):
    """OTP verification request."""
    mobile_number: str
    otp: str


class ChatCreateResponse(BaseModel):
    """Response for chat creation."""
    chat_id: str


class ChatResponse(BaseModel):
    """Non-streaming response from the agent."""
    reply: str


def _get_or_create_agent(chat_id: Optional[str] = None) -> tuple[UnifiedAgent, str]:
    """Get or create an agent for a chat session."""
    if chat_id and chat_id in _chat_agents:
        return _chat_agents[chat_id], chat_id
    
    # Create new chat session
    new_chat_id = chat_id or str(uuid.uuid4())
    agent = UnifiedAgent(log_level=logging.INFO)
    _chat_agents[new_chat_id] = agent
    logger.info(f"Created new agent for chat_id: {new_chat_id}")
    return agent, new_chat_id


# Auth endpoints (placeholder - implement proper auth later)
@app.post("/auth/login")
async def login(request: LoginRequest):
    """Placeholder login endpoint - accepts mobile number and returns success."""
    # In production, this would send OTP via SMS
    logger.info(f"Login request for mobile: {request.mobile_number}")
    return {"success": True, "message": "OTP sent to mobile number"}


@app.post("/auth/verify-otp")
async def verify_otp(request: VerifyOTPRequest):
    """Placeholder OTP verification - accepts any 6-digit OTP."""
    # Simple validation - accept any 6-digit OTP for now
    if request.otp and len(request.otp) == 6:
        # Generate a dummy access token
        import hashlib
        token = hashlib.sha256(f"{request.mobile_number}_{request.otp}".encode()).hexdigest()
        logger.info(f"OTP verified for mobile: {request.mobile_number}")
        return {
            "success": True,
            "access_token": token,
            "message": "Login successful"
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid OTP")


@app.post("/api/chat/create", response_model=ChatCreateResponse)
async def create_chat() -> ChatCreateResponse:
    """Create a new chat session."""
    agent, chat_id = _get_or_create_agent()
    return ChatCreateResponse(chat_id=chat_id)


@app.get("/api/chat/{chat_id}/messages")
async def get_messages(chat_id: str):
    """Get message history for a chat (placeholder - agent maintains history internally)."""
    if chat_id not in _chat_agents:
        raise HTTPException(status_code=404, detail="Chat not found")
    # The agent maintains conversation history internally
    # Return empty list as placeholder - frontend manages its own message state
    return {"messages": []}


@app.post("/api/chat/stream")
async def chat_stream(body: ChatRequest) -> StreamingResponse:
    """Stream chat response with Server-Sent Events format.
    
    Frontend expects:
    - POST /api/chat/stream
    - Body: { "message": "...", "chat_id": "..." }
    - Response: SSE format with chunks like:
      data: {"type": "content", "text": "..."}
      data: {"type": "tool_result", "data": {...}}
      data: {"type": "error", "message": "..."}
    """
    
    async def sse_generator() -> AsyncGenerator[bytes, None]:
        try:
            agent, chat_id = _get_or_create_agent(body.chat_id)
            
            # Send chat_id back to frontend
            yield f"data: {json.dumps({'type': 'chat_id', 'chat_id': chat_id})}\n\n".encode("utf-8")
            
            # Run agent and stream response
            response = await agent.run(body.message)
            
            # Format response as string if it's a dict (from plan_and_shop)
            if isinstance(response, dict):
                response_text = response.get("message", str(response))
            else:
                response_text = str(response)
            
            # Stream response in chunks (simulate streaming by sending character by character)
            # In a real implementation, you'd use pydantic-ai's streaming API
            chunk_size = 10  # Send 10 characters at a time for smoother streaming
            for i in range(0, len(response_text), chunk_size):
                chunk = response_text[i:i + chunk_size]
                yield f"data: {json.dumps({'type': 'content', 'text': chunk})}\n\n".encode("utf-8")
            
            # If response contains structured data (like cart info), send it as tool_result
            if isinstance(response, dict) and "cart" in response:
                yield f"data: {json.dumps({'type': 'tool_result', 'data': response})}\n\n".encode("utf-8")
            
        except Exception as e:
            logger.error(f"Error in chat stream: {e}", exc_info=True)
            error_msg = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(error_msg)}\n\n".encode("utf-8")
    
    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    """Chat with the agent (non-streaming)."""
    agent, _ = _get_or_create_agent(body.chat_id)
    reply = await agent.run(body.message)
    
    # Format response
    if isinstance(reply, dict):
        reply_text = reply.get("message", str(reply))
    else:
        reply_text = str(reply)
    
    return ChatResponse(reply=reply_text)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cleanly shut down all agents and MCP processes."""
    logger.info("Shutting down all agents...")
    for chat_id, agent in _chat_agents.items():
        try:
            await agent.close()
            logger.info(f"Closed agent for chat_id: {chat_id}")
        except Exception as e:
            logger.error(f"Error closing agent for chat_id {chat_id}: {e}")
    _chat_agents.clear()


if __name__ == "__main__":
    import uvicorn

    # Run with: python -m mcp_tools.api_server  (from project root)
    # Or: uvicorn mcp_tools.api_server:app --host 0.0.0.0 --port 8000 --reload
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("mcp_tools.api_server:app", host="0.0.0.0", port=port, reload=True)


