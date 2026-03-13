"""
app/schemas/chat.py
"""
from datetime import datetime
from pydantic import BaseModel


class ChatMessageIn(BaseModel):
    message: str


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime
    model_config = {"from_attributes": True}


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessageOut]


class ChatResponse(BaseModel):
    reply: str
    message_id: int
