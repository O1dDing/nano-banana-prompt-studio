# Architecture

依赖只允许 inward：`desktop` / `web` → `core`。core 零 Qt / Flask 依赖。对外 JSON 继续用中文 key；英文 `id` 只给 Web DOM / 内部 flatten。

```
src/nano_banana/
  core/                 schema、prompt_doc、chat、config、images
  desktop/              PyQt 窗体、FormPanel、ImageGenController、对话框
  web/                  Flask blueprints；静态文件仍在 src/web/static/
src/config/             options.yaml（选项库，不是 schema）
src/presets/
schema SSOT: src/nano_banana/core/schema.yaml
```

## 数据流

```mermaid
flowchart LR
  form["桌面/Web 表单"]
  doc["prompt_doc flatten/nest"]
  json["结构化 JSON（中文 key）"]
  chat["core.chat stream_chat"]
  img["images.Registry"]
  form --> doc --> json
  json --> chat
  json --> img
  img --> gemini[Gemini]
  img --> openai[OpenAI Images]
  img --> qwen[千问]
  img --> doubao[豆包]
```

## 加字段

```mermaid
flowchart TB
  yaml["改 schema.yaml + options.yaml"]
  desktop["桌面 FormPanel 按 schema 遍历"]
  web["Web GET /api/schema → PromptDoc collect/fill"]
  prompt["SYSTEM_PROMPT 示例 JSON 由 nest(example) 生成"]
  tests["契约测试：field id ↔ HTML id"]
  yaml --> desktop
  yaml --> web
  yaml --> prompt
  yaml --> tests
```

Web 表单 HTML 目前仍手写（1a）：新字段要在对应 tab 加 `id="<field.id>"` 的控件。collect/fill/分类预设已经走 schema，不会再双端漂移。

## 加渠道

```mermaid
flowchart TB
  meta["IMAGE_PROVIDER_META 登记扁平兼容 key"]
  cls["新建 provider：CAPABILITIES + generate_image"]
  reg["protocol._registry() 注册一行"]
  cfg["旧扁平 yaml 仍能读；新写入嵌套 image.providers"]
  meta --> cls --> reg --> cfg
```

兼容入口（不改旧命令）：

- `python src/main.py` → `nano_banana.desktop.main`
- `python src/web/app.py` → `nano_banana.web.app`
- `from utils.ai_config import AIConfigManager` 仍可用，内部 re-export core
