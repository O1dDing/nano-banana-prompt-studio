<p align="center"><img src="./images/logo.png" width="120" alt="Nano Banana" /></p>

# Nano Banana Studio · O1dDing Fork

结构化 Prompt、多渠道图片生成、Codex 订阅通道与适合 Cloudflare 的异步 Web 工作台。

基于 [原作者项目](https://github.com/lissettecarlr/nano-banana-prompt-studio)，沿用 MIT License。上游同步基线：`ad47e6a`。本 Fork 保留其 core/desktop/web 包结构、表单、分类预设、AI 修改差异预览、拖拽/粘贴参考图、图片预览与下载；Web 增强如下。

## 双通道，不拆掉现有 Web

```text
浏览器 → 现有 Flask/Gunicorn Web
             ├─ Prompt：原 API / Codex Subscription
             └─ Image：Gemini / OpenAI Images / Qwen / Seedream / Codex Image
                                     ↓
                            原异步任务、轮询与多标签页
```

选择 Codex 时，Web 经私有网络访问独立 Bridge；Bridge 使用官方 `codex app-server` stdio 协议。不是 ChatGPT 网页抓取，也不是把登录 token 填入 Images API。CLI 固定版本 `0.155.1`，构建时使用实际 CLI 导出的 JSON Schema 校验协议。

**API 通道继续可用；Codex 没登录、额度不足、不支持生成或返回错误，都不会静默改用收费 API。** 选择 API 则按该 API 供应商正常计费。

## Prompt → JSON

- API / Codex 引擎可切换，原有 API 凭据保留。
- 文本或参考图生成、修改现有 JSON、预览和应用到表单均保留。
- Codex 模型从当前登录账户的模型列表读取；空值使用账户默认模型，不把普通 Image 模型当作对话模型。
- `outputSchema` 从项目 `schema.yaml` 生成，并在接收结果时再次校验；`string_list` 保持字符串数组。
- 禁止联网：不提供内置搜索；自动联网：允许 live search，由模型决定；强制联网：必须观察到已完成的实际 search 事件，否则报错。
- SSE 进度、未验证预览与正式 JSON 分开处理；只有通过校验的结果才能应用。
- 停止/断线会取消 Bridge 任务并中断对应 turn；不自动重交任务。

## 图片参数：API 原生控制与 Codex 意图分开

| 参数 | OpenAI Images API | Codex 内置生图 |
|---|---|---|
| 模型 | `gpt-image-2`、`gpt-image-2.5-sunburst`、`gpt-image-2.5-flare` 及对应快照 | 内置工具决定；当前标为 `gpt-image-2`，不能用此处指定 2.5 |
| quality | Image 2：auto/low/medium/high；2.5 另支持 xhigh/max | auto/low/medium/high 仅作为提示性意图，不能核实硬参数生效 |
| size | 合法 WIDTHxHEIGHT 或 auto，后端原生传递 | 提示性期望；展示实际像素，不裁切、放大冒充 |
| output_format | png/jpeg/webp，保留上游原始字节 | 必要时在返回后本地编码为 png/jpeg/webp |
| output_compression | JPEG/WebP 的 0～100 原生参数 | JPEG/WebP 的本地编码质量，与生成质量不同 |
| background | auto/opaque/transparent；JPEG 不支持透明 | 提示性要求；未得到透明通道时警告，不伪造 |
| n | 1～10，全部返回并逐张显示 | 单张任务；多页面/多任务并行 |
| moderation | auto/low，非关闭审核 | 不提供 |

### 合法分辨率

按 2026-09-20 官方接口文档核对，Image 2/2.5 灵活分辨率同时满足：

- 宽、高均为 16 的倍数，每边不超过 3840；
- 宽高比在 1:3～3:1；
- 总像素数 655360～8294400；
- 超过 3686400 像素为实验性范围，账户/供应商可能仍返回限制。

例如：`1024x1024`、`1536x1024`、`2048x1152`、`2048x2048`、`3840x2160`、`2160x3840`。**不支持把两边都拉到 3840 的 `3840x3840`。** 1K/2K/4K + 宽高比预设仍保留，并显示实际对应像素；精确 size 非空时优先。

质量枚举随模型变化，不会在 Image 2 或 Codex 中显示无效的 xhigh/max。非法参数在提交模型前报错，不偷偷降质量、改尺寸或换模型。较旧 SDK 缺少的新字段按已核对的 HTTP 参数传递。

修复了原后端把所有结果重新转成 PNG 的问题：API 返回的 PNG/JPEG/WebP 字节、MIME 和下载扩展名保持一致。参考图按实际内容识别 MIME，而不是只看文件名。PNG/JPEG/WebP 直接上传；其他可解码图片会规范化后再上传。

**Codex Image 是实验通道**。通过 native `imageGeneration` 事件接收图片，绝不让 Codex 写脚本冒充图片，或暗中调用付费 Image API。公开协议、构建和模拟事件可以验证；账户生图权限、实际限额、生成质量及原生工具参数仍需登录后的真实任务验证。官方也建议需要稳定程序化生图时使用 Image Generation API。

## 不污染日常 Codex

每个任务使用独立临时工作目录与 `ephemeral=true` thread；不 resume 日常对话。不读取电脑或宿主机的 `~/.codex`，不接触当前开发项目。

- 强制 ChatGPT 登录；拒绝 API Key 身份，子进程不继承 API Key/第三方网关环境变量。
- 关闭 history、memories、shell、文件修改、插件及多代理等无关能力。
- 参考图、临时状态与运行日志位于专用 tmpfs，任务结束清理。
- 独立持久目录仅留登录凭据和 Codex 必要运行缓存；**并非整个软件零文件写入，也不代表 OpenAI 服务端零保留**。
- 图片仍会进入 Web 的本页历史与短期任务缓存，这是保留原有功能，不是 Codex 对话历史。

## 并发与取消

默认：

```text
IMAGE_TASK_WORKERS=4       # Web 图片任务并行数，API/Codex 图片共享
CODEX_PROMPT_WORKERS=4     # Codex Prompt 并行数
CODEX_IMAGE_WORKERS=4      # Codex 图片桥接并行数
IMAGE_TASK_MAX_PENDING=32
WEB_THREADS=16            # 更新器设置的 HTTP 线程数
```

三个任务并发参数均支持 1～32。提高本地并发不增加账户套餐额度，也不保证供应商相同吞吐。任务固定 Prompt、参考图、模型和参数快照，各页互不覆盖。服务器 API 默认配置仍是全局设置。

Codex 原生任务可发送 `turn/interrupt`；已发出的第三方 Image API 请求可能无法撤回或退费。异步任务在进程内存中，固定 **1 个 Gunicorn worker**，不要直接增加多进程/负载均衡容器数。重启会丢失未完成任务；更新前请等待任务结束并下载要保留的图片。

## Debian 12：升级并登录

要求 Docker、Git、Python 3；执行系统级更新需要 root。不要运行以前的补丁/更新脚本覆盖本次集成。

```bash
curl -fL https://raw.githubusercontent.com/O1dDing/nano-banana-prompt-studio/main/deploy/update_nano_banana_codex.py \
  -o update_nano_banana_codex.py
sudo python3 ./update_nano_banana_codex.py

# 只需首次或授权失效时执行；在自己的浏览器输入终端给出的设备码
sudo python3 ./update_nano_banana_codex.py --login-only
```

更新器先构建新镜像、检查 Bridge，再停旧 Web、取得最终配置快照、校验配置并切换。处理 `ai_config.yaml` 文件/目录冲突；无法恢复真实配置时停止并回滚，不用空配置掩盖错误。保留旧端口及自定义网络；遇到特殊网络或额外挂载会在停止服务前要求人工核对。

这版**不对 `/opt/nano-banana-prompt-studio` 执行 reset --hard**。运行源码使用独立 release 目录，原目录只作为兼容数据来源：

```text
/opt/nano-banana-data/
  config/            # API 配置与字段选项
  presets/           # 预设、分类预设
  codex-auth/        # 专用 Codex 登录，只有 Bridge 挂载
  secrets/           # Web↔Bridge 随机凭证
  releases/<版本>/   # 实际构建源码
  backups/<时间>/    # 回滚清单与旧数据
  deployment.json    # 当前容器、源码、提交位置
```

完成后浏览器 `Ctrl+Shift+R`。设置中刷新 Codex 状态并选择 Prompt 引擎。图片仍默认原渠道，需要套餐生图时手动选择 Codex Image。API 功能不要求先登录 Codex。

八路示例（仍受账户限额与服务器内存约束）：

```bash
sudo env IMAGE_TASK_WORKERS=8 CODEX_PROMPT_WORKERS=8 CODEX_IMAGE_WORKERS=8 \
  python3 ./update_nano_banana_codex.py
```

回滚命令在更新结束时输出，形式为：

```bash
sudo python3 ./update_nano_banana_codex.py --rollback /opt/nano-banana-data/backups/实际目录
```

回滚同时恢复旧容器和原持久目录，保留出错后的数据副本。仅删除新容器是不充分的。不要删除备份及 rollback 容器，直到真实 API/Codex 任务验证完成。

### 访问保护

这是个人自托管工具，不是公共多用户额度代理。现有 Web 没有新增用户系统，**必须保留 Cloudflare Access、Nginx 认证或等价的私人访问控制**。Bridge 不发布宿主端口，内部请求要求随机凭证；容器使用非 root、只读根文件系统、无 Docker socket/项目目录挂载。授权码、auth.json 和 secrets 不应上传 GitHub 或分享。

## 开发与验证

```bash
pip install -e '.[web,dev]'
pytest -q
pip install playwright
python -m playwright install chromium
python tools/browser_smoke.py
```

`.github/workflows/web-regression.yml` 验证 Python、JS、真实浏览器 UI、双 Docker 构建、未登录实际 App Server 探测、文件/目录冲突迁移与回滚。测试不包含真实账户的收费生成调用。

桌面端仍可 `pip install -e '.[desktop]'` 后运行 `python -m nano_banana`；本次 Codex 引擎选择与新参数 UI 主要集成在 Web。

## 官方能力依据

- [Codex App Server](https://developers.openai.com/codex/app-server)
- [Codex Authentication](https://developers.openai.com/codex/auth)
- [Codex Image generation](https://developers.openai.com/codex/image-generation)
- [Images generate](https://developers.openai.com/api/reference/resources/images/methods/generate)
- [Images edit](https://developers.openai.com/api/reference/resources/images/methods/edit)

MIT License；保留上游版权与许可。
