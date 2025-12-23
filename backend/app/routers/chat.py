"""
聊天路由 - 处理对话请求
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import json
from app.services.agent_service import process_chat_stream
from app.services.history_service import history_service

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    messages: Optional[List[Dict[str, Any]]] = []
    session_id: Optional[str] = None


class CanvasData(BaseModel):
    id: str
    name: str
    createdAt: float
    images: List[Dict[str, Any]]
    messages: List[Dict[str, Any]]


@router.get("/canvases")
async def get_canvases():
    """获取所有画布历史"""
    return history_service.get_canvases()


@router.post("/canvases")
async def save_canvas(request: Request):
    """保存或更新画布（项目）

    注意：前端会携带 Excalidraw 的 data(elements/appState/files)，
    用 Pydantic 模型解析容易因 extra 字段处理/热重载不同步而丢字段。
    这里直接存原始 JSON，避免 data 被过滤导致刷新后画布空白。
    """
    payload = await request.json()
    return history_service.save_canvas(payload)


@router.delete("/canvases/{canvas_id}")
async def delete_canvas(canvas_id: str):
    """删除画布"""
    history_service.delete_canvas(canvas_id)
    return {"success": True}


@router.post("/chat")
async def chat(request: ChatRequest):
    """
    处理聊天请求，返回流式响应
    支持OpenAI格式的流式输出
    """
    try:
        # 构建消息历史
        messages = request.messages.copy() if request.messages else []
        messages.append({
            "role": "user",
            "content": request.message
        })

        # 返回流式响应 - 确保立即发送，不缓冲
        return StreamingResponse(
            process_chat_stream(messages, request.session_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "Content-Type": "text/event-stream; charset=utf-8"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

