"""
app.py
------
FastAPI entry point.

Endpoints
---------
POST /chat   -> { "response": str }
GET  /health -> { "status": "ok" }

Run locally
-----------
    uvicorn smart_assistant.app:app --reload

Or via ADK CLI (dev mode, with built-in web UI):
    adk web

Or a single-turn CLI test:
    adk run smart_assistant
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from .agent import root_agent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session service (in-memory; swap for DatabaseSessionService in prod)
# ---------------------------------------------------------------------------

session_service = InMemorySessionService()
USER_ID = "default_user"
_session = None  # populated at startup


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _session
    _session = await session_service.create_session(
        app_name=root_agent.name,
        user_id=USER_ID,
    )
    logger.info("Session created: %s", _session.id)
    yield


app = FastAPI(title="Smart Assistant API", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    global _session
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    if _session is None:
        _session = await session_service.create_session(
            app_name=root_agent.name,
            user_id=USER_ID,
        )

    runner = Runner(
        agent=root_agent,
        session_service=session_service,
        app_name=root_agent.name,
    )

    final_response = ""

    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=_session.id,
        new_message=Content(
            role="user",
            parts=[Part(text=req.message)],
        ),
    ):
        if event.is_final_response():
            try:
                final_response = event.content.parts[0].text
            except (AttributeError, IndexError):
                final_response = "Sorry, I could not generate a response."

    return ChatResponse(response=final_response)