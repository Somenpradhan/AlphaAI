"""
agent.py
--------
Defines every agent and wires them together.

Architecture
------------

    User
     │
     ▼
  root_agent  (Router — LlmAgent)
     │
     ├──► general_agent      (LlmAgent, no tools)
     │
     └──► sequential_agent   (SequentialAgent)
               │
               ├──► planner_agent    (LlmAgent, all tools)
               │
               └──► formatter_agent  (LlmAgent, no tools)

• root_agent is what ADK Web / adk run exposes as the entry point.
  It MUST be named `root_agent` at module level.
• The Router delegates — it never replies itself.
• Only planner_agent calls tools.
• formatter_agent reads state["last_result"] written by the tools and
  produces the final user-visible reply.
• general_agent handles casual chat / knowledge questions with no tools.

Compatible with: `adk web`, `adk run`, FastAPI via Runner.
"""

import os
import logging

from dotenv import load_dotenv

from google.adk.agents import LlmAgent, SequentialAgent

from .instructions import (
    ROUTER_AGENT_ORCHESTRATOR,
    GENERAL_AGENT,
    PLANNER_AGENT,
    FORMATTER_AGENT,
)
from .tools import ALL_TOOLS

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
load_dotenv()

# ADK reads GOOGLE_GENAI_MODEL if set; fall back to MODEL, then a safe default.
MODEL = (
    os.environ.get("GOOGLE_GENAI_MODEL")
    or os.environ.get("MODEL")
    or "gemini-2.0-flash"
)

# ---------------------------------------------------------------------------
# General Agent
# ---------------------------------------------------------------------------
# Handles greetings, knowledge questions, small talk.
# No tools — pure conversational LLM.
# ---------------------------------------------------------------------------

general_agent = LlmAgent(
    name="general_agent",
    model=MODEL,
    instruction=GENERAL_AGENT,
    tools=[],
)

# ---------------------------------------------------------------------------
# Planner Agent
# ---------------------------------------------------------------------------
# Understands intent, calls tools, emits structured JSON to state.
# ---------------------------------------------------------------------------

planner_agent = LlmAgent(
    name="planner_agent",
    model=MODEL,
    instruction=PLANNER_AGENT,
    tools=ALL_TOOLS,
)

# ---------------------------------------------------------------------------
# Formatter Agent
# ---------------------------------------------------------------------------
# Reads state["last_result"], produces the final natural-language reply.
# No tools.
# ---------------------------------------------------------------------------

formatter_agent = LlmAgent(
    name="formatter_agent",
    model=MODEL,
    instruction=FORMATTER_AGENT,
    tools=[],
)

# ---------------------------------------------------------------------------
# Sequential Agent  (Planner → Formatter)
# ---------------------------------------------------------------------------
# ADK SequentialAgent runs sub_agents in order and passes session state
# between them, so the Formatter can read whatever the Planner wrote.
# ---------------------------------------------------------------------------

sequential_agent = SequentialAgent(
    name="sequential_agent",
    description=(
        "Handles task management, event scheduling, notes, and daily planning. "
        "Runs Planner then Formatter in sequence."
    ),
    sub_agents=[planner_agent, formatter_agent],
)

# ---------------------------------------------------------------------------
# Root Agent  (Router)
# ---------------------------------------------------------------------------
# This is the agent ADK exposes.  It classifies every incoming message and
# delegates to either general_agent or sequential_agent.
# IMPORTANT: must be named `root_agent` for `adk web` and `adk run`.
# ---------------------------------------------------------------------------

root_agent = LlmAgent(
    name="smart_assistant",
    model=MODEL,
    instruction=ROUTER_AGENT_ORCHESTRATOR,
    tools=[],
    sub_agents=[general_agent, sequential_agent],
)