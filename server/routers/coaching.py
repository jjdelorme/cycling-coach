"""AI coaching chat endpoint."""

import uuid
from fastapi import APIRouter

from server.models.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/coaching", tags=["coaching"])


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    from server.coaching.agent import chat

    session_id = req.session_id or str(uuid.uuid4())

    response = await chat(
        message=req.message,
        session_id=session_id,
    )

    return ChatResponse(response=response, session_id=session_id)
