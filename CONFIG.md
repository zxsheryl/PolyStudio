# 配置说明（以代码/requirements 为准）

本项目采用「OpenAI 兼容接口」方式接入对话模型（默认 SiliconFlow），并通过后端工具调用完成图片生成/编辑与本地持久化。

### 环境变量（建议放在 `backend/.env`）

你可以直接复制示例文件：

```bash
cd 001-生图Agent_new/backend
cp env.example .env
```

```env
# 对话模型（OpenAI 兼容）
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.siliconflow.cn/v1
MODEL_NAME=deepseek-ai/DeepSeek-V3.1-Terminus

# 图像生成/编辑模型（可选）
IMAGE_MODEL_NAME=Qwen/Qwen-Image
EDIT_IMAGE_MODEL_NAME=Qwen/Qwen-Image-Edit-2509

# 可选：生成/编辑后保存到本地的图片，会以 /storage/images/... 形式返回给前端
# edit_image 工具在传入本地路径时会拼接 BASE_URL
BASE_URL=http://localhost:8000

# 可选：LangGraph 递归限制（多步生成时避免过早停止）
RECURSION_LIMIT=200
```

### 图像生成/编辑（工具）

后端工具在 `backend/app/tools/image_generation.py`：

- **generate_image**：调用 SiliconFlow 的图片生成接口（当前使用 `Qwen/Qwen-Image`），并下载到 `backend/storage/images/`
- **edit_image**：调用图片编辑接口（当前使用 `Qwen/Qwen-Image-Edit-2509`），并下载到 `backend/storage/images/`

工具返回给前端的 `image_url` 默认形如：

- `/storage/images/<file>.jpg` 或 `/storage/images/<file>.png`

### 颜色一致性（Pillow / sRGB）

后端保存图片时会尝试：

- **ICC -> sRGB 归一化**
- **移除 ICC profile**

依赖 `Pillow`（已在 `backend/requirements.txt` 固定）。对存量图片可使用 `backend/scripts/normalize_storage_images.py` 批量归一化。

