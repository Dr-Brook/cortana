"""
JARVIS — Conversational Task Planner
Asks clarifying questions before building, breaks down complex requests.

Built from CLAUDE.md by RJ - https://itsbrook.com
"""

import json
import logging
from typing import Optional

logger = logging.getLogger("jarvis.planner")

# Planning templates
CLARIFYING_QUESTIONS = {
    "build": [
        "What specific features are required for this build?",
        "What's the target platform or environment?",
        "Are there existing designs, specs, or references?",
        "What's the priority — speed, quality, or completeness?",
    ],
    "debug": [
        "What's the exact error message or unexpected behavior?",
        "When did this start happening?",
        "What changed recently?",
        "Can you reproduce it consistently?",
    ],
    "research": [
        "What specific information are you looking for?",
        "How deep should the research go?",
        "Are there specific sources to prioritize or avoid?",
        "What format would you like the results in?",
    ],
    "general": [
        "Could you give me more details about what you'd like?",
        "Is there a specific outcome you're expecting?",
        "How should I deliver this — summary, detailed report, or step-by-step?",
    ],
}


def needs_clarification(request: str) -> bool:
    """Determine if a request needs clarification before proceeding."""
    # Short requests likely need clarification
    if len(request.split()) < 5:
        return True
    # Vague keywords
    vague = ["something", "some kind", "whatever", "stuff", "things", "a thing"]
    lower = request.lower()
    return any(v in lower for v in vague)


def get_request_type(request: str) -> str:
    """Classify the request type."""
    lower = request.lower()
    build_words = ["build", "create", "make", "develop", "implement", "code", "write", "design"]
    debug_words = ["fix", "debug", "error", "bug", "broken", "crash", "issue", "problem"]
    research_words = ["research", "find", "search", "look up", "investigate", "analyze", "compare"]
    
    for word in build_words:
        if word in lower:
            return "build"
    for word in debug_words:
        if word in lower:
            return "debug"
    for word in research_words:
        if word in lower:
            return "research"
    return "general"


def generate_clarifying_questions(request: str) -> list[str]:
    """Generate clarifying questions based on request type."""
    req_type = get_request_type(request)
    return CLARIFYING_QUESTIONS.get(req_type, CLARIFYING_QUESTIONS["general"])


def break_down_task(request: str) -> list[dict]:
    """Break down a complex task into steps."""
    req_type = get_request_type(request)
    
    if req_type == "build":
        return [
            {"step": 1, "action": "Define requirements and scope", "status": "pending"},
            {"step": 2, "action": "Research existing solutions and patterns", "status": "pending"},
            {"step": 3, "action": "Design architecture and data flow", "status": "pending"},
            {"step": 4, "action": "Implement core functionality", "status": "pending"},
            {"step": 5, "action": "Add error handling and edge cases", "status": "pending"},
            {"step": 6, "action": "Test and validate", "status": "pending"},
            {"step": 7, "action": "Document and deliver", "status": "pending"},
        ]
    elif req_type == "debug":
        return [
            {"step": 1, "action": "Reproduce the issue", "status": "pending"},
            {"step": 2, "action": "Identify root cause", "status": "pending"},
            {"step": 3, "action": "Implement fix", "status": "pending"},
            {"step": 4, "action": "Verify fix resolves the issue", "status": "pending"},
            {"step": 5, "action": "Add regression test", "status": "pending"},
        ]
    elif req_type == "research":
        return [
            {"step": 1, "action": "Define research scope and key questions", "status": "pending"},
            {"step": 2, "action": "Gather information from primary sources", "status": "pending"},
            {"step": 3, "action": "Analyze and cross-reference findings", "status": "pending"},
            {"step": 4, "action": "Synthesize conclusions", "status": "pending"},
            {"step": 5, "action": "Present findings", "status": "pending"},
        ]
    else:
        return [
            {"step": 1, "action": "Understand the request fully", "status": "pending"},
            {"step": 2, "action": "Plan approach", "status": "pending"},
            {"step": 3, "action": "Execute", "status": "pending"},
            {"step": 4, "action": "Review and deliver", "status": "pending"},
        ]


def format_plan(steps: list[dict]) -> str:
    """Format a task plan as a readable string."""
    lines = ["Here's my plan, sir:", ""]
    for step in steps:
        status_icon = "⬜" if step["status"] == "pending" else "✅" if step["status"] == "done" else "🔄"
        lines.append(f"  {status_icon} Step {step['step']}: {step['action']}")
    lines.append("")
    lines.append("Shall I proceed, or would you like to adjust anything?")
    return "\n".join(lines)