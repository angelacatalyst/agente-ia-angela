"""
Chat endpoint — SSE streaming + full-response modes.
Main entry point for all agent interactions.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.agents.orchestrator import FinanceOrchestrator
from app.core.dependencies import SettingsDep
from app.core.logging import get_logger
from app.core.security import verify_api_key
from app.models.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["Chat"])
logger = get_logger(__name__)

# Module-level orchestrator (initialized at startup, injected via lifespan)
_orchestrator: FinanceOrchestrator | None = None


def get_orchestrator() -> FinanceOrchestrator:
    if _orchestrator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Orchestrator not initialized",
        )
    return _orchestrator


def set_orchestrator(orch: FinanceOrchestrator) -> None:
    global _orchestrator
    _orchestrator = orch


@router.post("", response_model=ChatResponse, summary="Chat with Finance AI (full response)")
async def chat(
    request: ChatRequest,
    _: str = Depends(verify_api_key),
) -> ChatResponse:
    """
    Send a message to the Finance Operations AI Manager.
    The orchestrator auto-routes to the appropriate specialist module.

    - **orchestrator** mode: auto-detects the right module
    - Specify **module** to force a specific agent
    """
    orch = get_orchestrator()
    import json
    from datetime import datetime, timezone

    try:
        result = await orch.invoke(
            user_message=request.message,
            conversation_id=str(request.conversation_id) if request.conversation_id else None,
            qbo_realm_id=request.qbo_realm_id,
            context=request.context,
        )
    except Exception as exc:
        logger.error("Chat agent error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc

    return ChatResponse(
        conversation_id=uuid.UUID(result["conversation_id"]),
        module=result["module"],
        content=result["content"],
        tool_calls_made=result.get("tool_calls_made", []),
        created_at=datetime.now(timezone.utc),
    )


@router.post("/stream", summary="Chat with Finance AI (SSE streaming)")
async def chat_stream(
    request: ChatRequest,
    _: str = Depends(verify_api_key),
) -> StreamingResponse:
    """
    Stream tokens from the Finance Operations AI Manager via Server-Sent Events.

    SSE event types:
    - `{"type": "routing", "module": "<module>"}` — which agent was selected
    - `{"type": "token", "content": "<text>"}` — individual text chunks
    - `{"type": "done"}` — stream complete
    - `{"type": "error", "detail": "<msg>"}` — error occurred
    """
    orch = get_orchestrator()

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for chunk in orch.stream(
                user_message=request.message,
                conversation_id=str(request.conversation_id) if request.conversation_id else None,
                qbo_realm_id=request.qbo_realm_id,
                context=request.context,
            ):
                yield chunk
        except Exception as exc:
            import json
            logger.error("Streaming error", error=str(exc))
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
