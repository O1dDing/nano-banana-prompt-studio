<p align="center">
  <img src="./images/logo.png" alt="Nano Banana Logo" width="120" />
</p>

<h1 align="center">Nano Banana Studio · O1dDing Fork</h1>

<p align="center">
  <strong>结构化提示词、多渠道生图、第一阶段联网检索，以及适合 Cloudflare 自托管的异步任务队列。</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/OpenAI%20Images-gpt--image--2-412991?logo=openai&logoColor=white" alt="OpenAI Images" />
  <img src="https://img.shields.io/badge/Gemini-Image-4285F4?logo=googlegemini&logoColor=white" alt="Gemini" />
  <img src="https://img.shields.io/badge/Docker-Gunicorn-2496ED?logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/License-MIT-yellow" alt="License" />
</p>

> 本仓库基于 [lissettecarlr/nano-banana-prompt-studio](https://github.com/lissettecarlr/nano-banana-prompt-studio) 维护。当前已同步上游至 `ad47e6a`（2026-08-19），保留其新包结构、拖拽/粘贴参考图、生图历史、取消操作、草稿自动保存和 JSON 围栏清理等更新。

## 本 Fork 的增强

### 1. Prompt → JSON 第一阶段联网三档开关

设置页新增：

- **禁止联网**：完全沿用普通 Chat Completions。
- **自动联网**：向模型开放搜索能力；不支持搜索的第三方中转自动回退普通调用。
- **强制联网**：必须执行可确认的搜索；模型或网关不支持时明确报错。

联网协议按供应商分别适配，而不是给所有 API 强塞同一个参数：

| 第一阶段 API | 搜索方式 |
|---|---|
| OpenAI / xAI / 火山方舟及兼容 Responses 的中转 | `Responses API + web_search` |
| Gemini 官方接口 | Interactions API `google_search` |
| Anthropic Claude 官方接口 | Anthropic Web Search Tool |
| 阿里云百炼 / Qwen | `enable_search` / `forced_search` |
| 其他中转 | `auto` 失败回退；`force` 失败报错 |

该开关只影响提示词生成和修改，不会让第二阶段图片模型自行搜索网页。

### 2. 异步生图，规避 Cloudflare 524

原同步请求需要浏览器和 Cloudflare 一直等待第三方图片 API。现在改为：

```text
POST /api/generate-image
        ↓ 立即返回 HTTP 202 + task_id
线程池后台调用图片模型
        ↓
GET /api/generate-image/status/<task_id>
        ↓
completed / failed / cancelled
```

同时提供：

```text
POST /api/generate-image/cancel/<task_id>
GET  /api/generate-image/capacity
```

前端保留上游新增的拖拽、粘贴、生图历史与取消按钮，但取消操作现在会同时停止本页轮询并向服务器发送任务取消标记。已发往第三方模型的 HTTP 请求不一定能被远端中止；这时本服务会丢弃返回结果并把任务标为已取消。

### 3. OpenAI Images 参考图 MIME 修复

上传参考图时按图片实际内容识别 JPEG、PNG 或 WebP，并显式传递 multipart MIME，避免 WebP 被错误发送为：

```text
application/octet-stream
```

### 4. 多标签页并发生图

Docker 默认配置：

```text
IMAGE_TASK_WORKERS=4
IMAGE_TASK_MAX_PENDING=32
IMAGE_TASK_TTL_SECONDS=1800
WEB_THREADS=8
```

因此同一 Web 服务可以同时打开多个页面或标签页：默认最多 **4 个图片任务真正并行**，更多任务进入队列，最多保留 32 个未完成任务。每个页面使用独立 `task_id`，互不覆盖。

任务表目前保存在 Python 进程内，所以 Docker 固定使用 **1 个 Gunicorn worker + 多线程**。不要直接把 Gunicorn worker 数调到 2 以上；需要多进程或多机器横向扩展时，应先把任务状态迁移到 Redis 等共享存储。

## 上游保留功能

- 新的 `nano_banana` 包结构，拆分 `core / desktop / web`
- 结构化字段与 JSON 实时编辑
- AI 生成和修改提示词
- 参考图文件选择、拖拽与剪贴板粘贴
- 自动恢复本机草稿
- 本次会话生图历史与缩略图切换
- 预设管理、字段选项与 JSON 复制
- Gemini、OpenAI Images、千问图像、豆包 Seedream
- 桌面端与 Web 端

## Debian 12 / Docker 部署

```bash
git clone https://github.com/O1dDing/nano-banana-prompt-studio.git
cd nano-banana-prompt-studio

docker build --pull -f web_dockerfile -t nano-banana-web:o1dding .

docker run -d \
  --name nano-banana-web \
  --restart unless-stopped \
  -p 5000:5000 \
  -e IMAGE_TASK_WORKERS=4 \
  -e IMAGE_TASK_MAX_PENDING=32 \
  -e IMAGE_TASK_TTL_SECONDS=1800 \
  nano-banana-web:o1dding
```

访问：

```text
http://服务器IP:5000
```

### 源码方式

```bash
pip install -e ".[web]"
nano-banana-web
```

桌面端：

```bash
pip install -e ".[desktop]"
python -m nano_banana
```

## 更新已有 Docker 部署

先备份 `src/config/ai_config.yaml`，然后：

```bash
cd /opt/nano-banana-prompt-studio
git fetch origin
git checkout main
git reset --hard origin/main

docker build --no-cache -f web_dockerfile -t nano-banana-web:o1dding .
docker rm -f nano-banana-web

docker run -d \
  --name nano-banana-web \
  --restart unless-stopped \
  -p 5000:5000 \
  nano-banana-web:o1dding
```

## 同步关系

上游项目：

- [lissettecarlr/nano-banana-prompt-studio](https://github.com/lissettecarlr/nano-banana-prompt-studio)

本 Fork 已将定制功能迁移到上游新的包结构中：

- 第一阶段联网：`src/nano_banana/core/web_search.py`
- Web 提示词接口：`src/nano_banana/web/blueprints/chat.py`
- 异步任务：`src/nano_banana/web/image_tasks.py`
- 图片接口：`src/nano_banana/web/blueprints/images.py`
- OpenAI MIME 修复：`src/nano_banana/core/images/openai_images.py`

## License

沿用上游项目的 **MIT License**，保留原作者版权与许可声明。
