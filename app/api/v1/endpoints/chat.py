"""
app/api/v1/endpoints/chat.py
REST + WebSocket chat endpoints

REST:
  POST /chat          → send message, get reply
  GET  /chat/history  → last N messages
  DELETE /chat        → clear history

WebSocket:
  WS /chat/ws         → real-time streaming chat
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, get_verified_user, oauth2_scheme
from app.core.security import decode_token
from app.models.chat import ChatMessage
from app.models.user import User
from app.schemas.chat import ChatHistoryResponse, ChatMessageIn, ChatMessageOut, ChatResponse
from app.services.ai_chat import chat as ai_chat

logger = logging.getLogger("autotaxhub.chat")
router = APIRouter(prefix="/chat", tags=["AI Chat"])


# ── REST ──────────────────────────────────────────────────────────────────────

@router.post("", response_model=ChatResponse)
async def send_message(
    payload: ChatMessageIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """Send a message and receive an AI reply."""
    if not payload.message.strip():
        raise HTTPException(status_code=422, detail="Message cannot be empty")

    reply, msg_id = await ai_chat(payload.message, current_user, db)
    return ChatResponse(reply=reply, message_id=msg_id)


@router.get("/history", response_model=ChatHistoryResponse)
def get_history(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """Return last N messages for this user."""
    msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return ChatHistoryResponse(messages=list(reversed(msgs)))


@router.delete("", status_code=204)
def clear_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """Delete all chat history for this user."""
    db.query(ChatMessage).filter(ChatMessage.user_id == current_user.id).delete()
    db.commit()


# ── WebSocket ─────────────────────────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_chat(
    websocket: WebSocket,
    token: str,                    # ?token=<paseto_token> in query string
    db: Session = Depends(get_db),
):
    """
    WebSocket real-time chat.

    Connect: `ws://host/api/v1/chat/ws?token=<access_token>`

    Protocol:
    - Client sends: plain text message
    - Server sends: JSON  {"type": "reply", "content": "..."}
                    JSON  {"type": "error", "content": "..."}
                    JSON  {"type": "typing"}  (before reply)
    """
    # Authenticate via token in query param
    try:
        user_id = decode_token(token, expected_type="access")
        user    = db.query(User).filter(User.id == user_id, User.is_active == True).first()
        if not user:
            await websocket.close(code=4001)
            return
    except ValueError:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    logger.info(f"WS chat connected: user_id={user_id}")

    try:
        while True:
            data = await websocket.receive_text()
            msg  = data.strip()
            if not msg:
                continue
            if len(msg) > 2000:
                await websocket.send_json({"type": "error", "content": "Message too long (max 2000 chars)"})
                continue

            # Send typing indicator
            await websocket.send_json({"type": "typing"})

            reply, _ = await ai_chat(msg, user, db)
            await websocket.send_json({"type": "reply", "content": reply})

    except WebSocketDisconnect:
        logger.info(f"WS chat disconnected: user_id={user_id}")
    except Exception as e:
        logger.error(f"WS chat error: {e}")
        try:
            await websocket.send_json({"type": "error", "content": "Server error"})
        except Exception:
            pass
