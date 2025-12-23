"""
Agent服务 - 处理LangGraph Agent的流式输出
"""
import json
import os
import logging
from typing import List, Dict, Any, AsyncGenerator, Optional
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import AIMessageChunk, ToolMessage, convert_to_openai_messages
from app.services.stream_processor import StreamProcessor
from app.tools.image_generation import generate_image_tool, edit_image_tool

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 从环境变量获取配置
# 注意：不要在代码里写死任何真实 API Key。未配置时直接报错提示用户设置 .env。
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1").strip()
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-ai/DeepSeek-V3.1-Terminus").strip()


def create_agent():
    """创建LangGraph Agent"""
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "未配置 OPENAI_API_KEY。请在 backend/.env 中设置，"
            "可参考 env.example（cp env.example .env）。"
        )
    logger.info(f"🤖 创建Agent: model={MODEL_NAME}, base_url={OPENAI_BASE_URL}")
    
    # 创建OpenAI模型实例（使用SiliconFlow）
    # 关键：streaming=True 确保真正的流式输出
    model = ChatOpenAI(
        model=MODEL_NAME,
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL,
        temperature=0.7,
        streaming=True,  # 启用流式输出
        max_tokens=2048,
        # 关键：禁止并行工具调用，强制“一次调用一个工具 -> 等结果 -> 再下一次”
        # 否则模型可能在一次响应里吐出一堆 generate_image tool_calls，前端只能“挤在一起”展示。
        model_kwargs={"parallel_tool_calls": False},
    )

    # 创建工具列表
    tools = [generate_image_tool, edit_image_tool]
    logger.info(f"🛠️  注册工具: {[tool.name for tool in tools]}")

    # 创建Agent
    agent = create_react_agent(
        name="image_generation_agent",
        model=model,
        tools=tools,
        prompt="""你是一个专业的AI图像生成助手。

重要规则：
0. **必须一次只调用一个工具**：每生成/编辑一张图片，先调用一次工具，等待工具返回结果后再继续下一次调用。
1. 当用户请求生成新图片时，使用generate_image工具。
2. 当用户请求修改、编辑或变换之前生成的图片时，使用edit_image工具。
3. **关键**：当使用edit_image工具时，必须从对话历史中查找之前generate_image工具返回的结果。
   - 在之前的工具调用结果中查找JSON格式的返回结果
   - 提取其中的"image_url"字段作为原图URL
   - 如果找不到，可以查找"local_path"字段
   - 不要要求用户提供图片URL，应该自动从历史记录中提取
4. 如果用户说"修改成XX"、"改成XX"、"变成XX"等，这表示要编辑之前生成的图片，必须使用edit_image工具。
5. 始终从对话历史中查找最近生成的图片URL，不要要求用户提供。"""
    )
    
    logger.info("✅ Agent创建成功")
    return agent


async def process_chat_stream(
    messages: List[Dict[str, Any]],
    session_id: Optional[str] = None
) -> AsyncGenerator[str, None]:
    """
    处理聊天流式响应
    
    Args:
        messages: 消息历史
        session_id: 会话ID
    
    Yields:
        SSE格式的事件流
    """
    try:
        logger.info(f"💬 收到聊天请求: session_id={session_id}, messages_count={len(messages)}")
        
        # 创建Agent（在 langgraph 1.0.0 中，create_react_agent 返回的对象已经是编译后的）
        agent = create_agent()

        # 创建流处理器
        processor = StreamProcessor(session_id)

        # 处理流式响应
        async for event in processor.process_stream(agent, messages):
            yield event

    except Exception as e:
        import traceback
        logger.error(f"❌ 处理聊天流时出错: {str(e)}")
        logger.error(traceback.format_exc())
        # 发送错误事件
        error_event = {
            "type": "error",
            "error": str(e)
        }
        yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

