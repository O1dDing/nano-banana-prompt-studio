<p align="center"><img src="./images/logo.png" width="120" alt="Nano Banana" /></p>

# Nano Banana Studio · O1dDing Fork

结构化 Prompt、多渠道图片生成、Codex 订阅通道与 Cloudflare Access 多用户 Docker 工作台。

基于 [原作者项目](https://github.com/lissettecarlr/nano-banana-prompt-studio)，沿用 MIT License。上游同步基线 `ad47e6a`；保留 core/desktop/web 包结构、表单、分类预设、AI 修改差异预览、拖拽/粘贴参考图、图片预览/下载和多标签页。

## Cloudflare Access：长期身份与持久配置

启用 Access 身份模式后，用户通过网站现有 Cloudflare Access 登录即可恢复自己的 API 配置、模型和预设，**不需要先登录 Codex**。本服务验证 Access 的签名 JWT、issuer、Application AUD、有效期和用户声明，不信任单独邮箱请求头或浏览器传来的用户 ID。

| 角色/凭据 | 用途和生命周期 |
|---|---|
| Cloudflare 用户身份 | `(issuer, sub)` 绑定长期个人 Profile，邮箱作为辅助信息 |
| 个人 API 配置 | 独立持久保存，跨页面关闭、24h 到期及容器重启恢复 |
| 多位管理员 | 服务器配置指定，自动使用原有共享服务器配置；网页不能自助提权 |
| Codex Device Auth | 仅为当前页签提供 Codex 额度，不决定 API 配置归属 |

管理员名单保存在服务器 `/opt/nano-banana-data/access/cloudflare.json`，支持多个邮箱或 subject，修改后下一次请求/心跳重新校验；不能经网页修改。所有管理员共管同一套原服务器 API/预设/长期 Codex 身份。普通用户绝不继承管理员 Key 或其他用户配置。

API Key 按部署需求明文存储在受限目录，不作应用层加密，也不会在 GET `/api/config` 中回显。留空保存不改变原 Key；明确输入新值才能替换，另有“清除已保存密钥”按钮。同 Profile 配置操作受文件锁保护，API 配置原子写入。

完整设置、边界和恢复说明：**[Cloudflare 身份、持久档案与多管理员](docs/CLOUDFLARE_PROFILES_ZH.md)**。

## Docker 首次启用与后续更新

要求 Debian 12/Linux、root、Docker、Git、Python 3、curl。更新前等待生成任务结束并下载需要的图片。

```bash
cd /root && \
curl -fL --retry 3 \
  'https://raw.githubusercontent.com/O1dDing/nano-banana-prompt-studio/main/deploy/update_nano_banana_codex.sh' \
  -o update_nano_banana_codex.sh && \
bash ./update_nano_banana_codex.sh --configure-access
```

终端依次填写 Team 域名（不是网站域名）、Access Application Audience (AUD)、多位管理员邮箱和可选 subject。多个值用逗号分隔，确认 `YES` 后更新。也支持 `--access-config /路径/cloudflare.json --require-access`。

配置示例，必须替换为自己的实际值：

```json
{
  "issuer": "https://YOUR-TEAM.cloudflareaccess.com",
  "audiences": ["YOUR-ACCESS-APPLICATION-AUD"],
  "admin_emails": ["admin1@example.com", "admin2@example.com"],
  "admin_subjects": [],
  "auto_create": true,
  "subject_aliases": {}
}
```

后续直接执行：

```bash
bash /root/update_nano_banana_codex.sh
```

已经启用的 Access 模式和配置持久卷会继续保留。更新器校验固定版本 Python 更新器，先构建双镜像并检查 Bridge，再备份、迁移和启动；失败时回滚。保留旧端口/自定义 Docker 网络，处理 `ai_config.yaml` 文件/目录冲突，不对原项目目录执行 `git reset --hard`。

```text
/opt/nano-banana-data/
  access/cloudflare.json   # 服务器专属 Access 信任配置与多管理员名单
  users/profiles.sqlite    # 身份索引
  users/<uuid>/            # 各用户 ai_config.yaml / options.yaml / presets
  config/                  # 管理员共享的原 API 配置/字段选项
  presets/                 # 管理员共享的原预设
  codex-auth/              # 管理员专用 Codex 长期身份
  secrets/                 # Bridge 内部凭证
  releases/<版本>/         # 实际运行源码
  backups/<时间>/          # 回滚清单与旧数据
  deployment.json
```

回滚按更新日志给出的路径执行：

```bash
bash /root/update_nano_banana_codex.sh --rollback /opt/nano-banana-data/backups/实际目录
```

回滚不覆盖升级后新保存的个人 Profile。更新会终止临时 Codex 会话，但不删除持久个人 API/预设或管理员原身份。更新后浏览器 `Ctrl+Shift+R`。

**未提供 Access 配置的旧安装仍支持临时多用户模式**，使用服务器密钥解锁管理员。该旧模式个人 API 配置随会话回收；见 [旧版多用户说明](docs/MULTIUSER_ZH.md)。首次切到 Access 必须用新版更新入口和 `--configure-access`，不能复用旧 pinned updater。

## Codex 设备授权和短期页签

需要使用 Codex Prompt/Image 时点击 **我的 Codex → 登录我的 ChatGPT / Codex**。页面显示官方设备码、复制按钮和官方授权链接；授权完成状态变绿，模型列表来自该次授权账户。Access 与 Codex 邮箱允许不同。

| 设置 | 行为 |
|---|---|
| 心跳 | 浏览器每 30 秒发送；任务轮询不续租 |
| 关闭页签 | 90 秒失联后回收；后台每 5 秒清扫 |
| 绝对期限 | Codex 授权最多 24 小时，持续心跳不能延期 |
| 刷新 | 租约有效时保留当前页签短期身份 |
| 多页签 | 同一 Access 用户共享 Profile，Codex 授权和任务仍按页签独立 |
| 退出/到期 | 取消本页签任务、停止相关 Codex 进程、删除临时凭据；不删持久 Profile |

使用官方 `codex app-server` stdio，不抓 ChatGPT 网页/Cookie。固定 CLI `0.155.1`；构建时检查真实运行时导出的临时会话、结构化输出、中断和设备码协议。**Codex 未登录、额度不足或报错时绝不自动切换到收费 API。**

## Prompt、图片与界面

```text
Cloudflare Access → Web 身份/Profile → 独立页签任务
                     ├─ Prompt：原 API / Codex Subscription
                     └─ Image：Gemini / OpenAI Images / Qwen / Seedream / Codex Image
                                      ↓
                              异步任务、所有者校验、轮询、取消
```

Prompt 保留文字/参考图生成、修改 JSON、差异预览和应用到表单。Codex 模型及推理强度动态读取 `model/list`，输出用项目 `schema.yaml` 转出的 `outputSchema`，最终再校验。强制联网必须观察到实际完成的搜索事件，否则失败；禁止联网关闭搜索，自动模式允许模型选择是否搜索。

OpenAI Images 保留合法精确尺寸、宽高比/尺寸档位、模型支持的质量、PNG/JPEG/WebP、背景、审核强度和多张生成。精确尺寸留空按预设计算，显式 `auto` 交给供应商。非法尺寸拒绝，不偷偷缩放或降质；实验性尺寸显示黄色状态。API 返回的原始字节、MIME、下载扩展名一致。Web 不展示压缩参数，原生调用兼容保留。

**Codex Image 的能力边界未改变**：图片模型由内置工具决定，尺寸/质量/背景是提示性要求，格式必要时本地转换；实际尺寸会显示，不放大/裁切冒充。没有真实原生图片结果就报错，不写脚本伪造图片，也不自动改用收费 Image API。

## 不污染日常 Codex

每任务临时目录和 `ephemeral=true` thread，不恢复日常对话或读取宿主 `~/.codex`。关闭 history/memories/shell/插件/多代理等无关能力。个人 Codex 凭据位于 Bridge tmpfs `/run/nano-codex/sessions/`，不进入持久 Profile；浏览器只持有本服务随机短期令牌，不接收 OpenAI access/refresh token。

tmpfs 不保证物理零落盘：宿主 swap、休眠、内存转储仍可能写盘。清理本地凭据不等于 OpenAI 远端零保留或全设备 OAuth 撤销。

## 并发、部署边界与验证

默认全局图片线程池 4 路，Codex Prompt 和 Codex Image 各 4 路；环境参数可配置至 32。新用户不会额外增加并发，供应商速率和套餐额度仍有效。一个 Gunicorn worker 配合多线程；多进程横向扩展前必须引入共享任务存储。

继续用 HTTPS 和 Cloudflare Access 白名单。Nginx 要保留 `Cf-Access-Jwt-Assertion`，Web 尽量只绑定回环或 Tunnel 网络，Bridge 不公开端口、不挂 Docker socket，非 root/只读根文件系统。所有管理员及服务器 root 受到信任；这不是每用户虚拟机或零信任托管。普通用户默认只允许官方 HTTPS API，自定义中转由管理员配置使用。

浏览器冻结/休眠/网络失联按相同租约过期，不能保证关闭瞬时注销；已经发往第三方的请求不保证撤回或退款。Access JWT 验证不能离线立即感知所有远程撤销，须配合边缘策略、JWT 到期与短租约。

开发测试：

```bash
pip install -e '.[web,dev]' playwright
pytest -q
python -m playwright install chromium
python tools/browser_smoke.py
python tools/multiuser_browser_smoke.py
python tools/access_browser_smoke.py
```

CI 使用本地 RSA 测试 JWT、账户替身、真实浏览器和真实 Docker 迁移/回滚，不消费个人 API/Codex 额度。部署后的实际 Team/AUD/反向代理转发和首个真实授权仍需站长核对。

## License

沿用上游 MIT License，保留原作者许可声明。
