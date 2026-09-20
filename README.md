<p align="center"><img src="./images/logo.png" width="120" alt="Nano Banana" /></p>

# Nano Banana Studio · O1dDing Fork

结构化 Prompt、多渠道图片生成、Codex 订阅通道与适合 Cloudflare 的异步 Docker Web 工作台。

基于 [原作者项目](https://github.com/lissettecarlr/nano-banana-prompt-studio)，沿用 MIT License。上游同步基线：`ad47e6a`。保留 core/desktop/web 包结构、表单、分类预设、AI 修改差异预览、拖拽/粘贴参考图、图片预览、下载和多标签页。

## 多用户设备授权

**本次升级需要重新下载更新入口，不能复用旧的 pinned updater。** 升级后默认进入个人模式，原服务器 API 配置没有丢失，仅管理员模式可以使用。

点击 **我的 Codex → 登录我的 ChatGPT / Codex**，页面展示官方设备码和授权链接。每个人使用自己的账户、模型列表和额度，Prompt/图片任务不会串号。设备码按不透明字符串显示，不写死数字数量。

| 设置 | 行为 |
|---|---|
| 心跳 | 浏览器每 30 秒发送；任务轮询不续租 |
| 关闭页签 | 90 秒失联后回收；后台每 5 秒清扫 |
| 绝对期限 | 完成授权后最多 24 小时，持续心跳也不能延期 |
| 刷新 | 保留本页签短期身份 |
| 复制页签 | 新建独立身份，不继承另一页签的授权 |
| 退出/到期 | 取消本用户任务、停止对应 Codex 进程、清理临时凭据和结果 |

个人配置、自己输入的 API Key 和个人预设使用独立临时目录，随会话回收；重要内容应先导出。原有服务器配置和预设继续持久保存。完整机制、限制和数据生命周期见 **[多用户部署与使用说明](docs/MULTIUSER_ZH.md)**。

## 双通道，不拆掉现有 Web

```text
浏览器 → Flask/Gunicorn Web → 页签身份
             ├─ Prompt：原 API / Codex Subscription
             └─ Image：Gemini / OpenAI Images / Qwen / Seedream / Codex Image
                                     ↓
                         异步任务、所有者检查、轮询与取消
```

Codex 通过私有 Bridge 调用官方 `codex app-server` stdio 协议，不抓 ChatGPT 网页或 Cookie。固定 CLI `0.155.1`；镜像构建时用实际 CLI 导出的 Schema 检查临时会话、结构化输出、中断与设备码协议。

**Codex 未登录、额度不足或返回错误时，绝不自动切换到付费 API。** 手动选择 API 则使用本用户提供的凭据。个人模式只允许官方 HTTPS API 地址；管理员保留自定义中转支持。

## Prompt → JSON

文本/参考图生成、修改 JSON、差异预览和应用到表单均保留。Codex 模型及推理强度读取当前身份的 `model/list`；输出使用从 `schema.yaml` 生成的 `outputSchema`，接收后再次校验。

禁止联网关闭搜索；自动联网提供实时搜索；强制联网必须观察到实际完成的 search 事件，否则失败。SSE 未验证预览和正式 JSON 分开，未通过校验不应用。个人模型、联网设置和字段选项不覆盖其他用户。

## 图片控制

OpenAI Images API 保留模型选择、合法精确尺寸、宽高比/尺寸档位、质量、PNG/JPEG/WebP、背景、审核强度和多图生成。各模型只显示其声明支持的质量档位；非法尺寸在请求前拒绝，不偷偷降质或缩放。精确尺寸输入为空时按预设计算，显式 `auto` 交由供应商选择。

API 返回的图片原始字节、MIME 和下载扩展名保持一致；Web 不再显示 JPEG/WebP 压缩输入框，后端原生 API 调用仍保留兼容。参考图按实际内容识别 MIME。

**Codex Image 仍是实验能力**：图片模型由内置工具决定，尺寸/质量/背景仅为提示性要求；格式必要时本地转换，实际尺寸会显示，不放大或裁切冒充。缺少原生图片结果会报错，不让 Codex 写脚本伪造图片或调用收费 Image API。

## 不污染日常 Codex

每个任务独立工作目录与 `ephemeral=true` thread，不 resume 日常对话，不读取宿主 `~/.codex`，不接触开发项目。关闭 history、memories、shell、插件及多代理等无关能力。

个人 Codex 身份位于 Bridge tmpfs `/run/nano-codex/sessions/`；个人 Web 数据位于 `/run/nano-web-sessions/`，不进入 `/opt` 的持久备份。管理员原先的长期 Codex 身份仍保存在专用 `codex-auth` 卷。浏览器只保存本服务随机令牌，不接收 OpenAI access/refresh token。

tmpfs 不等于物理零落盘：宿主 swap、休眠或内存转储仍可能写盘。会话清理不代表 OpenAI 服务端零保留或全设备 OAuth 撤销。

## 并发与取消

```text
IMAGE_TASK_WORKERS=4       # API/Codex 图片共享的全局并发
CODEX_PROMPT_WORKERS=4     # Codex Prompt 全局并发
CODEX_IMAGE_WORKERS=4      # Codex 图片 Bridge 全局并发
IMAGE_TASK_MAX_PENDING=32
WEB_THREADS=16
```

并发可配置 1～32，每用户另有未完成任务限制。并发不是每新增一个用户自动增加四路，也不绕过供应商速率或套餐额度。固定一个 Gunicorn worker；多进程/多机器扩展必须先引入共享任务存储。

已发出的第三方 API 请求不保证撤回或退款；失效后不再允许取用该用户任务，未交付结果丢弃。更新前等待正在生成的任务结束并下载需要保留的结果。

## Debian 12 更新

要求 root、Docker、Git、Python 3、curl。

```bash
cd /root && \
curl -fL --retry 3 \
  'https://raw.githubusercontent.com/O1dDing/nano-banana-prompt-studio/main/deploy/update_nano_banana_codex.sh' \
  -o update_nano_banana_codex.sh && \
bash ./update_nano_banana_codex.sh
```

更新器验证固定 Python 更新器内容，先构建双镜像并检查 Bridge，再停旧 Web、备份和校验数据、迁移、启动并检查。保留旧端口和自定义网络，处理 `ai_config.yaml` 文件/目录冲突，失败自动回滚；不对原项目目录执行 `reset --hard`。

```text
/opt/nano-banana-data/
  config/             # 管理员原 API 配置/字段选项
  presets/            # 管理员原预设
  codex-auth/         # 管理员专用 Codex 长期身份
  secrets/            # Bridge 内部凭证及 Web 管理员密钥
  releases/<版本>/    # 运行源码
  backups/<时间>/     # 回滚清单与旧数据
  deployment.json
```

更新后 `Ctrl+Shift+R`，个人用户在 Web 自行设备授权，不需要服务器 SSH。原服务器配置在 **我的 Codex → 服务器管理员** 中解锁，密钥只在自己的终端查看：

```bash
cat /opt/nano-banana-data/secrets/web-admin-token
```

不要将管理员密钥交给普通用户或发送到聊天。个人会话不跨容器重建保留，更新后需重新授权；管理员长期身份不删除。

回滚使用更新日志提供的命令，或：

```bash
bash ./update_nano_banana_codex.sh --rollback /opt/nano-banana-data/backups/实际目录
```

### 部署边界

这是一套应用层身份隔离，不等价于每人独立虚拟机或零信任凭据托管。服务器 root 仍可访问内存；只在信任的服务器使用。保留 HTTPS、Cloudflare Access/反向代理准入和限流。Bridge 不发布宿主端口，使用非 root、只读根文件系统，无 Docker socket 挂载。

浏览器关闭、崩溃、冻结或网络中断无法被服务器瞬时可靠区分，统一按租约失效处理。不得宣传为关页签毫秒级注销或无条件无限并发。

## 开发与验证

```bash
pip install -e '.[web,dev]' playwright
pytest -q
python -m playwright install chromium
python tools/browser_smoke.py
python tools/multiuser_browser_smoke.py
```

CI 覆盖旧 Web 回归、多用户身份/任务权限、假时钟 30/90 秒和24小时边界、真实浏览器设备码/刷新/复制页签、两个生产镜像、实际 Codex 协议以及 Docker 数据迁移和回滚。认证与生成测试使用替身，不消耗用户套餐或真实 API 费用；每个账户的首次真实登录和生图仍需用户实际验证。

桌面端可 `pip install -e '.[desktop]'` 后 `python -m nano_banana`；多用户身份系统集成在 Web。

## 官方接口依据

- [Codex App Server](https://developers.openai.com/codex/app-server)
- [Codex Authentication](https://developers.openai.com/codex/auth)
- [Codex Image generation](https://developers.openai.com/codex/image-generation)
- [Images generate](https://developers.openai.com/api/reference/resources/images/methods/generate)
- [Images edit](https://developers.openai.com/api/reference/resources/images/methods/edit)

MIT License；保留上游版权与许可。
