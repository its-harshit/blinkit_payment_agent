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
# from .unified_agent_langchain import UnifiedAgent
# NOTE: If your OSS model doesn't support function calling, uncomment the LangChain version above
# and comment out the pydantic-ai version. LangChain uses ReAct (text-based) tool calling which
# works better with models that don't support OpenAI-style function calling.

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Feature flag: enable/disable true model streaming.
# - When True  (default): use UnifiedAgent.run(..., writer=...) + model streaming
# - When False: fall back to non-streaming agent.run(...) and fake chunking on the server side
ENABLE_MODEL_STREAMING = os.getenv("ENABLE_MODEL_STREAMING", "1") in ("1", "true", "True")

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


async def _get_or_create_agent(chat_id: Optional[str] = None) -> tuple[UnifiedAgent, str]:
    """Get or create an agent for a chat session.
    
    Eagerly initializes MCP clients (Blinkit and Payment) when creating a new agent
    to avoid initialization delay on first request.
    """
    if chat_id and chat_id in _chat_agents:
        return _chat_agents[chat_id], chat_id
    
    # Create new chat session
    new_chat_id = chat_id or str(uuid.uuid4())
    agent = UnifiedAgent(log_level=logging.INFO)
    
    # Eagerly initialize MCP clients to avoid delay on first request
    try:
        logger.info(f"Initializing MCP clients for chat_id: {new_chat_id}")
        await agent._ensure_blinkit()
        await agent._ensure_payment()
        await agent._ensure_travel()
        logger.info(f"✅ MCP clients initialized successfully for chat_id: {new_chat_id}")
    except Exception as e:
        logger.error(f"❌ Failed to initialize MCP clients for chat_id {new_chat_id}: {e}")
        # Still store the agent, but it will fail on first tool call
        # This allows the server to start even if MCP servers are temporarily unavailable
    
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
    agent, chat_id = await _get_or_create_agent()
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
        """
        SSE generator with two modes controlled by ENABLE_MODEL_STREAMING:
        - True:  use UnifiedAgent.run(..., writer=...) and real model streaming
        - False: call agent.run(...) once and fake-stream the final text in chunks
        """
        import asyncio

        try:
            agent, chat_id = await _get_or_create_agent(body.chat_id)

            # Send chat_id back to frontend
            yield f"data: {json.dumps({'type': 'chat_id', 'chat_id': chat_id})}\n\n".encode("utf-8")

            if not ENABLE_MODEL_STREAMING:
                # Non-streaming agent call + server-side chunking (previous behavior)
                response = await agent.run(body.message)

                # Format response as string if it's a dict (e.g., from plan_and_shop)
                if isinstance(response, dict):
                    response_text = response.get("message", str(response))
                else:
                    response_text = str(response)

                # Fake streaming by slicing final text into chunks
                chunk_size = 10  # characters per SSE chunk
                for i in range(0, len(response_text), chunk_size):
                    chunk = response_text[i:i + chunk_size]
                    yield f"data: {json.dumps({'type': 'content', 'text': chunk})}\n\n".encode("utf-8")

                # If response contains structured data (like cart info), send it as tool_result
                if isinstance(response, dict) and "cart" in response:
                    yield f"data: {json.dumps({'type': 'tool_result', 'data': response})}\n\n".encode("utf-8")

            else:
                # True model streaming using UnifiedAgent.run(..., writer=...)
                queue: "asyncio.Queue[Optional[str]]" = asyncio.Queue()
                final_response_container: dict = {"response": None}

                async def writer(chunk: dict) -> None:
                    # Called by UnifiedAgent.run for each streamed text chunk
                    text = chunk.get("content", "")
                    if text:
                        await queue.put(text)

                async def run_agent() -> None:
                    try:
                        response = await agent.run(body.message, writer=writer)
                        final_response_container["response"] = response
                    except Exception as e:
                        # Push error marker into queue so outer loop can send SSE error
                        await queue.put(f"__ERROR__:{str(e)}")
                    finally:
                        # Signal completion
                        await queue.put(None)

                # Kick off agent in background
                asyncio.create_task(run_agent())

                # Drain queue and stream SSE events
                while True:
                    chunk = await queue.get()
                    if chunk is None:
                        break

                    if isinstance(chunk, str) and chunk.startswith("__ERROR__:"):
                        error_msg = {"type": "error", "message": chunk[len("__ERROR__:") :]}
                        yield f"data: {json.dumps(error_msg)}\n\n".encode("utf-8")
                        break

                    # Normal content chunk
                    yield f"data: {json.dumps({'type': 'content', 'text': chunk})}\n\n".encode("utf-8")

                # After streaming text, if we have a structured dict (e.g. cart info), send it as tool_result
                response = final_response_container["response"]
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
    agent, _ = await _get_or_create_agent(body.chat_id)
    reply = await agent.run(body.message)
    
    # Format response
    if isinstance(reply, dict):
        reply_text = reply.get("message", str(reply))
    else:
        reply_text = str(reply)
    
    return ChatResponse(reply=reply_text)


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize MCP clients at server startup to verify they're available."""
    logger.info("🚀 Server starting up - verifying MCP servers...")
    try:
        # Create a test agent to verify MCP servers are available
        test_agent = UnifiedAgent(log_level=logging.INFO)
        await test_agent._ensure_blinkit()
        await test_agent._ensure_payment()
        await test_agent._ensure_travel()
        await test_agent.close()
        logger.info("✅ MCP servers verified and ready")
    except Exception as e:
        logger.warning(f"⚠️  MCP servers not available at startup: {e}")
        logger.warning("   Server will continue, but MCP operations may fail until servers are available")


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
    uvicorn.run("backend.api_server:app", host="0.0.0.0", port=port, reload=True)


