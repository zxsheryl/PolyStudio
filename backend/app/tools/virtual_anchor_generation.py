"""
虚拟主播生成工具 - 支持图片+音频生成虚拟人视频
"""
import json
import logging
import os
import base64
import uuid
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def sanitize_error_message(error_msg: str) -> str:
    """
    截断错误信息，避免在日志中打印过长内容
    
    Args:
        error_msg: 原始错误信息
    
    Returns:
        截断后的错误信息
    """
    if not isinstance(error_msg, str):
        error_msg = str(error_msg)
    
    # 简单截断，超过1000字符就截断
    if len(error_msg) > 1000:
        return error_msg[:1000] + "...(已截断)"
    return error_msg

# 优先加载 backend/.env
BASE_DIR = Path(__file__).parent.parent.parent
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

# 注意：人脸检测工具函数使用延迟导入，避免直接运行脚本时的路径问题

# 虚拟主播生成相关配置
VIRTUAL_ANCHOR_PROVIDER = os.getenv("VIRTUAL_ANCHOR_PROVIDER", "d-id").strip()
FACE_DETECTION_METHOD = os.getenv("FACE_DETECTION_METHOD", "opencv").strip()  # opencv 或 llm

# 大模型人脸检测配置（使用火山引擎，从 .env 读取）
VOLCANO_API_KEY = os.getenv("VOLCANO_API_KEY", "").strip()
VOLCANO_BASE_URL = os.getenv("VOLCANO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").strip()
VOLCANO_MODEL_NAME = os.getenv("VOLCANO_MODEL_NAME", "doubao-seed-1-6-251015").strip()

# 存储目录
STORAGE_DIR = BASE_DIR / "storage"
IMAGES_DIR = STORAGE_DIR / "images"
AUDIOS_DIR = STORAGE_DIR / "audios"
VIDEOS_DIR = STORAGE_DIR / "videos"

# 确保存储目录存在
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
AUDIOS_DIR.mkdir(parents=True, exist_ok=True)
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

# Mock 模式配置
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() == "true"


def prepare_image_path(image_url: str) -> Path:
    """
    准备图片路径，支持本地文件和URL
    
    Args:
        image_url: 本地路径（如 /storage/images/xxx.jpg）或 URL
    
    Returns:
        Path: 本地文件路径
    """
    # 检查是否是本地路径
    if image_url.startswith("/storage/") or image_url.startswith("storage/"):
        file_path = BASE_DIR / image_url.lstrip("/")
        if not file_path.exists():
            raise FileNotFoundError(f"本地文件不存在: {file_path}")
        return file_path
    
    # 如果是URL，需要先下载（这里暂时不支持，后续可以扩展）
    raise ValueError(f"暂不支持URL图片，请使用本地路径: {image_url}")


def prepare_image_base64(image_path: Path) -> str:
    """
    将图片转换为base64编码（用于大模型输入）
    
    根据火山引擎官方示例，使用 data URI 格式：data:image/png;base64,{base64_image}
    
    Args:
        image_path: 图片路径
    
    Returns:
        str: base64编码的图片字符串（data URI 格式：data:image/格式;base64,base64数据）
    """
    # 读取图片文件
    with open(image_path, "rb") as f:
        image_data = f.read()
    
    # 根据文件扩展名确定图片格式（MIME类型）
    ext = image_path.suffix.lower()
    if ext in [".jpg", ".jpeg"]:
        mime_type = "image/jpeg"
    elif ext == ".png":
        mime_type = "image/png"
    elif ext == ".webp":
        mime_type = "image/webp"
    elif ext == ".gif":
        mime_type = "image/gif"
    else:
        # 默认使用 png（与官方示例一致）
        mime_type = "image/png"
        logger.warning(f"⚠️ 未知图片格式 {ext}，使用 image/png")
    
    # 转换为base64
    base64_data = base64.b64encode(image_data).decode("utf-8")
    
    # 返回完整的 data URI 格式（与官方示例一致）
    data_uri = f"data:{mime_type};base64,{base64_data}"
    
    logger.info(f"📷 图片已转换为Base64: 格式={mime_type}, 大小={len(image_data)} bytes, base64长度={len(base64_data)}")
    
    return data_uri


def detect_face_with_llm(image_path: Path) -> Dict[str, Any]:
    """
    使用大模型进行人脸检测（火山引擎 doubao-seed-1-6-251015）
    
    Args:
        image_path: 图片路径
    
    Returns:
        人脸检测结果字典
    """
    if not VOLCANO_API_KEY:
        raise ValueError("未配置 VOLCANO_API_KEY（请在 backend/.env 设置）")
    
    # 将图片转换为base64
    base64_image = prepare_image_base64(image_path)
    
    # 构建请求（使用火山引擎官方格式：/responses 端点）
    api_url = f"{VOLCANO_BASE_URL.rstrip('/')}/responses"
    logger.info(f"🌐 API地址: {api_url}")
    headers = {
        "Authorization": f"Bearer {VOLCANO_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # 构建多模态输入（使用火山引擎官方格式）
    # 根据官方文档，格式应该是：
    # - type: "input_image"
    # - type: "text"
    payload = {
        "model": VOLCANO_MODEL_NAME,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_image",
                        "image_url": base64_image  # data URI 格式：data:image/png;base64,{base64_image}
                    },
                    {
                        "type": "input_text",
                        "text": "请分析这张图片中是否包含人脸。如果包含人脸，请告诉我：1. 检测到几张人脸 2. 人脸是否清晰 3. 人脸在图片中的位置（大致描述）4. 是否适合用于虚拟主播生成。请用JSON格式返回，包含字段：has_face(bool), face_count(int), is_clear(bool), position(str), suitable_for_virtual_anchor(bool), message(str)"
                    }
                ]
            }
        ]
    }
    
    logger.info(f"🤖 使用大模型检测人脸: model={VOLCANO_MODEL_NAME}")
    
    # 打印请求参数（截断长字符串）
    payload_str = json.dumps(payload, ensure_ascii=False, indent=2)
    if len(payload_str) > 500:
        payload_str = payload_str[:500] + "...(已截断)"
    logger.info(f"📤 请求参数: {payload_str}")
    
    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=30)
        
        # 如果请求失败，记录详细错误信息
        if response.status_code != 200:
            error_text = response.text[:500] if len(response.text) > 500 else response.text
            logger.error(f"❌ API请求失败: status={response.status_code}")
            logger.error(f"   错误响应: {error_text}")
            try:
                error_data = response.json()
                error_str = json.dumps(error_data, ensure_ascii=False, indent=2)
                if len(error_str) > 500:
                    error_str = error_str[:500] + "...(已截断)"
                logger.error(f"   错误详情: {error_str}")
            except:
                pass
            response.raise_for_status()
        
        data = response.json()
        # 打印响应（截断长字符串）
        data_str = json.dumps(data, ensure_ascii=False, indent=2)
        if len(data_str) > 500:
            data_str = data_str[:500] + "...(已截断)"
        logger.info(f"📥 大模型响应: {data_str}")
        
        # 解析响应（根据实际API返回格式）
        # 火山引擎响应格式：{ "output": [{ "type": "reasoning", "summary": [{ "type": "summary_text", "text": "..." }] }] }
        content = ""
        
        # 尝试1: 包含 output 字段（火山引擎标准格式）
        if "output" in data and isinstance(data["output"], list) and len(data["output"]) > 0:
            output_list = data["output"]
            logger.info(f"📋 解析 output 数组，共 {len(output_list)} 个元素")
            # 遍历 output 数组，查找文本内容
            for idx, output_item in enumerate(output_list):
                if isinstance(output_item, dict):
                    output_type = output_item.get("type", "unknown")
                    logger.info(f"   元素 {idx}: type={output_type}")
                    
                    # 检查是否有 summary 字段（reasoning 类型）
                    if "summary" in output_item and isinstance(output_item["summary"], list):
                        logger.info(f"   找到 summary 数组，共 {len(output_item['summary'])} 个元素")
                        for summary_idx, summary_item in enumerate(output_item["summary"]):
                            if isinstance(summary_item, dict):
                                summary_type = summary_item.get("type", "unknown")
                                if summary_type == "summary_text":
                                    text = summary_item.get("text", "")
                                    if text:
                                        logger.info(f"   提取 summary_text: {text[:100]}...")
                                        content += text + "\n"
                    # 检查是否有直接的 text 或 content 字段
                    if "text" in output_item:
                        text = output_item["text"]
                        if isinstance(text, str) and text:
                            logger.info(f"   提取 text 字段: {text[:100]}...")
                            content += text + "\n"
                    elif "content" in output_item:
                        content_value = output_item["content"]
                        # content 可能是字符串或列表
                        if isinstance(content_value, str) and content_value:
                            logger.info(f"   提取 content 字段(字符串): {content_value[:100]}...")
                            content += content_value + "\n"
                        elif isinstance(content_value, list):
                            # content 是列表，遍历提取文本
                            logger.info(f"   提取 content 字段(列表)，共 {len(content_value)} 个元素")
                            for content_item in content_value:
                                if isinstance(content_item, dict):
                                    # 检查是否有 text 字段
                                    if "text" in content_item:
                                        text = content_item["text"]
                                        if isinstance(text, str) and text:
                                            logger.info(f"   提取 content 中的 text: {text[:100]}...")
                                            content += text + "\n"
                                    # 检查是否有其他文本字段
                                    elif "content" in content_item:
                                        text = content_item["content"]
                                        if isinstance(text, str) and text:
                                            logger.info(f"   提取 content 中的 content: {text[:100]}...")
                                            content += text + "\n"
            content = content.strip()
            logger.info(f"✅ 提取的内容长度: {len(content)} 字符")
        # 尝试2: 直接是字符串
        elif isinstance(data, str):
            content = data
        # 尝试3: OpenAI 兼容格式（choices）
        elif "choices" in data and len(data["choices"]) > 0:
            content = data["choices"][0].get("message", {}).get("content", "")
        # 尝试4: 直接包含 content 或 text 字段
        elif "content" in data:
            content = data["content"] if isinstance(data["content"], str) else ""
        elif "text" in data:
            content = data["text"] if isinstance(data["text"], str) else ""
        
        if not content:
            # 如果所有尝试都失败，记录完整响应并抛出错误
            logger.error(f"❌ 无法从响应中提取内容")
            data_str = json.dumps(data, ensure_ascii=False, indent=2)
            if len(data_str) > 500:
                data_str = data_str[:500] + "...(已截断)"
            logger.error(f"   完整响应: {data_str}")
            raise ValueError(f"无法从响应中提取内容。请检查响应格式。完整响应已记录在日志中。")
        
        if content:
            
            # 尝试从content中提取JSON（大模型可能返回文本+JSON）
            # 这里简化处理，实际可能需要更复杂的解析
            try:
                # 尝试直接解析为JSON
                result = json.loads(content)
            except json.JSONDecodeError:
                # 如果直接解析失败，尝试提取JSON部分
                import re
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    # 如果都失败，返回默认结果
                    logger.warning(f"⚠️ 无法解析大模型返回的JSON，使用默认结果")
                    result = {
                        "has_face": False,
                        "face_count": 0,
                        "is_clear": False,
                        "position": "unknown",
                        "suitable_for_virtual_anchor": False,
                        "message": "无法解析大模型返回结果"
                    }
            
            # 转换为统一格式
            return {
                "has_face": result.get("has_face", False),
                "face_count": result.get("face_count", 0),
                "face_boxes": [],  # 大模型不提供精确坐标
                "confidence": 1.0 if result.get("suitable_for_virtual_anchor", False) else 0.5,
                "largest_face": {
                    "box": None,
                    "confidence": 1.0 if result.get("is_clear", False) else 0.5,
                    "position": result.get("position", "unknown")
                } if result.get("has_face", False) else None,
                "llm_result": result,
                "method": "llm"
            }
        else:
            raise ValueError("大模型响应格式异常")
            
    except Exception as e:
        error_msg = sanitize_error_message(str(e))
        logger.error(f"❌ 大模型人脸检测失败: {error_msg}")
        logger.error(f"   API地址: {api_url}")
        raise


def detect_face(image_url: str, method: Optional[str] = None) -> Dict[str, Any]:
    """
    检测人脸（支持OpenCV和大模型两种方法）
    
    Args:
        image_url: 图片URL或本地路径
        method: 检测方法（"opencv" 或 "llm"），如果为None则从环境变量读取
    
    Returns:
        人脸检测结果字典
    """
    # 确定使用的检测方法
    if method is None:
        method = FACE_DETECTION_METHOD
    
    # 准备图片路径
    image_path = prepare_image_path(image_url)
    
    logger.info(f"🔍 开始检测人脸: method={method}, image={image_path}")
    
    # 延迟导入人脸检测工具函数（避免直接运行脚本时的路径问题）
    from app.utils.face_detection import detect_face_opencv, validate_face_quality
    
    # 根据方法选择检测函数
    if method == "llm":
        face_info = detect_face_with_llm(image_path)
    else:  # 默认使用opencv
        face_info = detect_face_opencv(image_path)
        face_info["method"] = "opencv"
    
    # 验证人脸质量
    is_valid, error_msg = validate_face_quality(face_info, image_path)
    face_info["is_valid"] = is_valid
    face_info["validation_message"] = error_msg
    
    return face_info


class DetectFaceInput(BaseModel):
    """人脸检测输入参数"""
    image_url: str = Field(description="图片URL或本地路径（如 /storage/images/xxx.jpg）")
    method: Optional[str] = Field(default=None, description="检测方法：opencv（轻量级）或 llm（大模型），默认从环境变量读取")


@tool("detect_face", args_schema=DetectFaceInput)
def detect_face_tool(image_url: str, method: Optional[str] = None) -> str:
    """
    人脸检测服务：检测图片中是否包含人脸，并验证是否适合用于虚拟主播生成。
    
    支持两种检测方法：
    1. opencv（轻量级）：使用OpenCV Haar Cascade，速度快，无需API调用
    2. llm（大模型）：使用火山引擎多模态模型，准确度高，支持更复杂的分析
    
    Args:
        image_url: 图片URL或本地路径（如 /storage/images/xxx.jpg）
        method: 检测方法（"opencv" 或 "llm"），如果为None则从环境变量 FACE_DETECTION_METHOD 读取
    
    Returns:
        人脸检测结果的JSON字符串，包含：
        - has_face: 是否检测到人脸
        - face_count: 检测到的人脸数量
        - is_valid: 是否适合用于虚拟主播生成
        - validation_message: 验证信息
        - face_boxes: 人脸边界框列表
        - largest_face: 最大人脸的信息
    """
    try:
        logger.info(f"🔍 开始人脸检测: image_url={image_url}, method={method}")
        
        # 执行人脸检测
        face_info = detect_face(image_url, method)
        
        # 构建返回结果
        result = {
            "has_face": face_info["has_face"],
            "face_count": face_info["face_count"],
            "is_valid": face_info["is_valid"],
            "validation_message": face_info["validation_message"],
            "method": face_info.get("method", "unknown"),
            "face_boxes": face_info.get("face_boxes", []),
            "largest_face": face_info.get("largest_face"),
        }
        
        # 如果使用大模型，添加额外信息
        if "llm_result" in face_info:
            result["llm_analysis"] = face_info["llm_result"]
        
        result_json = json.dumps(result, ensure_ascii=False)
        logger.info(f"✅ 人脸检测完成: has_face={face_info['has_face']}, is_valid={face_info['is_valid']}")
        return result_json
        
    except Exception as e:
        error_msg = sanitize_error_message(str(e))
        logger.error(f"❌ 人脸检测失败: {error_msg}")
        import traceback
        # 清理traceback中的base64
        tb_str = traceback.format_exc()
        tb_sanitized = sanitize_error_message(tb_str)
        logger.error(tb_sanitized)
        return json.dumps({
            "error": f"人脸检测失败: {error_msg}",
            "has_face": False,
            "is_valid": False
        }, ensure_ascii=False)


class GenerateVirtualAnchorInput(BaseModel):
    """虚拟主播生成输入参数"""
    image_url: str = Field(description="肖像图片URL或本地路径")
    audio_url: str = Field(description="音频文件URL或本地路径")
    provider: Optional[str] = Field(default=None, description="提供商（d-id, heygen等），默认从环境变量读取")


def prepare_audio_input(audio_url: str) -> str:
    """
    准备音频输入，处理本地文件（转Base64）或公网URL
    
    Args:
        audio_url: 本地路径（如 /storage/audios/xxx.mp3）或 localhost URL 或公网URL
    
    Returns:
        Base64编码字符串（本地文件）或URL字符串（公网URL）
    
    Raises:
        FileNotFoundError: 本地文件不存在
    """
    # 检查是否是本地路径
    if audio_url.startswith("/storage/"):
        # 本地文件，读取并转换为Base64
        file_path = BASE_DIR / audio_url.lstrip("/")
        if not file_path.exists():
            raise FileNotFoundError(f"本地文件不存在: {file_path}")
        
        logger.info(f"📁 读取本地音频文件: {file_path}")
        
        # 读取文件
        with open(file_path, "rb") as f:
            audio_data = f.read()
        
        # 获取文件扩展名，确定音频格式
        ext = file_path.suffix.lower()
        if ext in [".mp3"]:
            audio_format = "mp3"
        elif ext in [".wav"]:
            audio_format = "wav"
        elif ext in [".m4a"]:
            audio_format = "m4a"
        elif ext in [".aac"]:
            audio_format = "aac"
        else:
            audio_format = "mp3"
            logger.warning(f"未知音频格式 {ext}，使用 mp3")
        
        # 转换为Base64
        base64_data = base64.b64encode(audio_data).decode("utf-8")
        return f"data:audio/{audio_format};base64,{base64_data}"
    
    # 检查是否是localhost URL
    elif audio_url.startswith("http://localhost") or audio_url.startswith("http://127.0.0.1"):
        # localhost URL，也转换为Base64
        try:
            import urllib.request
            with urllib.request.urlopen(audio_url) as response:
                audio_data = response.read()
            
            # 从URL推断格式
            if audio_url.endswith(".mp3"):
                audio_format = "mp3"
            elif audio_url.endswith(".wav"):
                audio_format = "wav"
            elif audio_url.endswith(".m4a"):
                audio_format = "m4a"
            else:
                audio_format = "mp3"
            
            base64_data = base64.b64encode(audio_data).decode("utf-8")
            return f"data:audio/{audio_format};base64,{base64_data}"
        except Exception as e:
            logger.error(f"❌ 无法下载 localhost 音频: {e}")
            raise
    
    # 公网URL，直接返回
    else:
        logger.info(f"🌐 使用公网音频URL: {audio_url}")
        return audio_url


@tool("generate_virtual_anchor", args_schema=GenerateVirtualAnchorInput)
def generate_virtual_anchor_tool(
    image_url: str,
    audio_url: str,
    provider: Optional[str] = None
) -> str:
    """
    虚拟主播生成服务：根据图片和音频生成口型同步的虚拟人视频。
    
    使用火山引擎单图音频驱动API，包含两个步骤：
    1. 形象创建：上传角色形象图片，创建虚拟人形象
    2. 视频生成：使用创建的形象和音频文件生成视频
    
    Args:
        image_url: 肖像图片URL或本地路径（如 /storage/images/xxx.jpg）
        audio_url: 音频文件URL或本地路径（如 /storage/audios/xxx.mp3）
        provider: 提供商，目前仅支持 "volcano"（火山引擎），默认从环境变量读取
    
    Returns:
        生成的视频文件路径的JSON字符串或错误信息
    """
    try:
        # 确定使用的提供商
        if provider is None:
            provider = VIRTUAL_ANCHOR_PROVIDER
        
        if provider != "volcano":
            return json.dumps({
                "error": f"不支持的提供商: {provider}",
                "message": "目前仅支持 volcano（火山引擎）"
            }, ensure_ascii=False)
        
        if not VOLCANO_API_KEY:
            return json.dumps({
                "error": "未配置 VOLCANO_API_KEY",
                "message": "请在 backend/.env 中设置 VOLCANO_API_KEY"
            }, ensure_ascii=False)
        
        logger.info(f"🎬 开始生成虚拟人视频: image={image_url}, audio={audio_url}")
        
        # 步骤1：准备图片输入
        image_input = prepare_image_base64(prepare_image_path(image_url))
        logger.info(f"✅ 图片已准备: {len(image_input)} 字符")
        
        # 步骤2：准备音频输入
        audio_input = prepare_audio_input(audio_url)
        logger.info(f"✅ 音频已准备: {len(audio_input) if isinstance(audio_input, str) else 'URL'} 字符")
        
        # 步骤3：创建形象（调用步骤1：形象创建）
        # 根据火山引擎文档：https://www.volcengine.com/docs/86081/1804514?lang=zh
        # 注意：API端点可能需要根据实际文档调整
        # 可能的端点：/video/avatars, /avatars, /api/v3/video/avatars 等
        avatar_url = f"{VOLCANO_BASE_URL.rstrip('/')}/video/avatars"
        headers = {
            "Authorization": f"Bearer {VOLCANO_API_KEY}",
            "Content-Type": "application/json"
        }
        
        avatar_payload = {
            "image": image_input  # base64编码的图片
        }
        
        logger.info(f"📤 步骤1: 创建虚拟人形象")
        logger.info(f"   API地址: {avatar_url}")
        
        avatar_response = requests.post(avatar_url, json=avatar_payload, headers=headers, timeout=60)
        
        if avatar_response.status_code != 200:
            error_text = avatar_response.text[:500] if len(avatar_response.text) > 500 else avatar_response.text
            logger.error(f"❌ 形象创建失败: status={avatar_response.status_code}")
            logger.error(f"   错误响应: {error_text}")
            return json.dumps({
                "error": f"形象创建失败: status={avatar_response.status_code}",
                "message": error_text
            }, ensure_ascii=False)
        
        avatar_data = avatar_response.json()
        logger.info(f"📥 形象创建响应: {json.dumps(avatar_data, ensure_ascii=False)[:500]}...")
        
        # 提取形象ID
        avatar_id = None
        if "avatar_id" in avatar_data:
            avatar_id = avatar_data["avatar_id"]
        elif "id" in avatar_data:
            avatar_id = avatar_data["id"]
        elif "data" in avatar_data and isinstance(avatar_data["data"], dict):
            avatar_id = avatar_data["data"].get("avatar_id") or avatar_data["data"].get("id")
        
        if not avatar_id:
            logger.error(f"❌ 无法从响应中提取形象ID")
            logger.error(f"   完整响应: {json.dumps(avatar_data, ensure_ascii=False)}")
            return json.dumps({
                "error": "形象创建成功但无法提取形象ID",
                "response": avatar_data
            }, ensure_ascii=False)
        
        logger.info(f"✅ 形象创建成功: avatar_id={avatar_id}")
        
        # 步骤4：生成视频（调用步骤2：视频生成）
        # 根据火山引擎文档：https://www.volcengine.com/docs/86081/1804515?lang=zh
        # 注意：API端点可能需要根据实际文档调整
        # 可能的端点：/video/generations, /videos, /api/v3/video/generations 等
        video_url = f"{VOLCANO_BASE_URL.rstrip('/')}/video/generations"
        
        video_payload = {
            "avatar_id": avatar_id,
            "audio": audio_input  # base64编码的音频或URL
        }
        
        logger.info(f"📤 步骤2: 生成虚拟人视频")
        logger.info(f"   API地址: {video_url}")
        logger.info(f"   形象ID: {avatar_id}")
        
        video_response = requests.post(video_url, json=video_payload, headers=headers, timeout=120)
        
        if video_response.status_code != 200:
            error_text = video_response.text[:500] if len(video_response.text) > 500 else video_response.text
            logger.error(f"❌ 视频生成失败: status={video_response.status_code}")
            logger.error(f"   错误响应: {error_text}")
            return json.dumps({
                "error": f"视频生成失败: status={video_response.status_code}",
                "message": error_text
            }, ensure_ascii=False)
        
        video_data = video_response.json()
        logger.info(f"📥 视频生成响应: {json.dumps(video_data, ensure_ascii=False)[:500]}...")
        
        # 提取视频URL
        video_url_result = None
        if "video_url" in video_data:
            video_url_result = video_data["video_url"]
        elif "url" in video_data:
            video_url_result = video_data["url"]
        elif "data" in video_data:
            if isinstance(video_data["data"], dict):
                video_url_result = video_data["data"].get("video_url") or video_data["data"].get("url")
            elif isinstance(video_data["data"], str):
                video_url_result = video_data["data"]
        
        if not video_url_result:
            logger.error(f"❌ 无法从响应中提取视频URL")
            logger.error(f"   完整响应: {json.dumps(video_data, ensure_ascii=False)}")
            return json.dumps({
                "error": "视频生成成功但无法提取视频URL",
                "response": video_data
            }, ensure_ascii=False)
        
        logger.info(f"✅ 视频生成成功: video_url={video_url_result}")
        
        # 步骤5：下载视频并保存到本地
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        video_filename = f"virtual_anchor_{timestamp}_{unique_id}.mp4"
        video_path = VIDEOS_DIR / video_filename
        
        logger.info(f"📥 下载视频到本地: {video_path}")
        
        try:
            video_download_response = requests.get(video_url_result, timeout=300)
            if video_download_response.status_code == 200:
                with open(video_path, "wb") as f:
                    f.write(video_download_response.content)
                logger.info(f"✅ 视频已保存: {video_path}")
            else:
                logger.warning(f"⚠️ 视频下载失败，使用原始URL: {video_url_result}")
                video_path = None
        except Exception as e:
            logger.warning(f"⚠️ 视频下载异常: {e}，使用原始URL: {video_url_result}")
            video_path = None
        
        # 构建返回结果
        result = {
            "success": True,
            "avatar_id": avatar_id,
            "video_url": video_url_result,
            "video_path": f"/storage/videos/{video_filename}" if video_path else None,
            "provider": "volcano"
        }
        
        logger.info(f"🎉 虚拟人视频生成完成")
        return json.dumps(result, ensure_ascii=False)
        
    except FileNotFoundError as e:
        error_msg = sanitize_error_message(str(e))
        logger.error(f"❌ 文件不存在: {error_msg}")
        return json.dumps({
            "error": f"文件不存在: {error_msg}",
            "success": False
        }, ensure_ascii=False)
    except Exception as e:
        error_msg = sanitize_error_message(str(e))
        logger.error(f"❌ 虚拟人视频生成失败: {error_msg}")
        import traceback
        tb_str = traceback.format_exc()
        tb_sanitized = sanitize_error_message(tb_str)
        logger.error(tb_sanitized)
        return json.dumps({
            "error": f"虚拟人视频生成失败: {error_msg}",
            "success": False
        }, ensure_ascii=False)


if __name__ == "__main__":
    """测试工具"""
    import sys
    from pathlib import Path
    
    # 添加 backend 目录到 Python 路径，以便能够导入 app 模块
    # 这必须在调用任何使用延迟导入的函数之前执行
    backend_dir = Path(__file__).parent.parent.parent
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # 测试人脸检测（由于使用了延迟导入，现在可以正常工作了）
    result = detect_face_tool.invoke({
        "image_url": "/storage/images/volcano_20260121_172941_2e425df2_特写主角面部眼神中闪过一丝迷茫随即恢复坚定展现内心的抉.jpg",
        "method": "opencv"
    })
    print("检测结果:", result)

    result = detect_face_tool.invoke({
        "image_url": "/storage/images/20251215_111010_633e9de4_Shanghai_Yu_Garden_classical_C.png",
        "method": "opencv"
    })
    print("检测结果:", result)


    # 测试人脸检测（由于使用了延迟导入，现在可以正常工作了）
    result = detect_face_tool.invoke({
        "image_url": "/storage/images/volcano_20260121_172941_2e425df2_特写主角面部眼神中闪过一丝迷茫随即恢复坚定展现内心的抉.jpg",
        "method": "llm"
    })
    print("检测结果llm:", result)

    result = detect_face_tool.invoke({
        "image_url": "/storage/images/20251215_111010_633e9de4_Shanghai_Yu_Garden_classical_C.png",
        "method": "llm"
    })
    print("检测结果llm:", result)