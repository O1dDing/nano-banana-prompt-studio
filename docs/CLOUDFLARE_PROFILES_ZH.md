# Cloudflare Access 身份、持久个人 API 与多管理员

## 行为

Cloudflare Access 是网站长期身份；Codex Device Auth 只是当前页签可选的计算凭据。通过第一层 Access 登录后即可读取自己的 API 配置，不必先登录 Codex。不同 Cloudflare 用户隔离；同一身份在不同设备/页签恢复同一个 Profile。Codex 登录邮箱不要求和 Access 相同，也不会决定 API 配置归属。

管理员可以有多位，由服务器 `access/cloudflare.json` 的 `admin_emails` / `admin_subjects` 指定。管理员自动使用现有服务器 `config/`、`presets/` 和管理员 Codex 身份。**多位管理员共管同一套服务器配置，不是各一套；所有普通用户使用自己的独立 Profile。** 网站内不能自封管理员，Access 模式禁止旧 `web-admin-token` 的网页提权入口。

## 首次部署

重新下载仓库 `deploy/update_nano_banana_codex.sh` 后执行：

```bash
bash ./update_nano_banana_codex.sh --configure-access
```

终端依次询问：

1. Team 域名，例如 `my-team.cloudflareaccess.com`。这不是 Nano Banana 网站域名。
2. 当前网站 Access Application 的 Application Audience (AUD) Tag；可配置多个，逗号分隔。
3. 多位管理员邮箱，逗号分隔。
4. 可选管理员 `sub`，逗号分隔；已有值输入 `-` 可清空。
5. 输入 `YES` 确认保存并开始部署。

也可预先编写文件并使用 `--access-config /路径/cloudflare.json --require-access`。更新器会在停止旧 Web 前用新镜像的解析器检查配置；新的 Web 容器挂载策略目录为只读、个人 Profile 为持久卷。未提供配置的旧安装仍保留旧多用户模式；检测到已有 Access 配置的后续更新会继续启用 Access，不需要再次输入。

首次启用需要实际的 Team、AUD、管理员名单；不会从任意来访 JWT 自动学习信任配置或把第一个访客设成管理员。未改 Cloudflare 控制台、Tunnel 或 Nginx 配置；这些仍由站长管理。

## 配置示例与后续添加管理员

文件：`/opt/nano-banana-data/access/cloudflare.json`

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

将示例替换成实际值。`admin_emails` 匹配签名已验证的邮箱（不分大小写、无通配符）；`admin_subjects` 匹配签名已验证的原始 `sub`。两组是 OR 关系，issuer/AUD 始终一起校验。至少保留一名管理员。

Root 编辑此文件即可增删管理员，不必提交私人邮箱到 GitHub。运行中的 Web 每次请求重读配置；权限变化时旧页签会话作废，刷新后按新权限进入。通常会在下一次请求/30 秒心跳发现变化。不通过已缓存的管理员角色绕过移除。

建议先写临时文件、校验后用 `os.replace` 原子替换。配置缺失、JSON 损坏、未知字段等会拒绝请求，不回退旧策略；配置权限 0600，目录 0700。目录整体只读挂载，原子替换后容器可看到新文件。修改 issuer/AUD 也会切换信任边界，务必核对。

## 认证边界

只接受 `Cf-Access-Jwt-Assertion` 的 RS256 签名；固定 issuer、AUD，并校验 exp/iat/nbf、type=app、sub、email。拒绝 Service Token、普通邮箱头、无签名/错签名/错 audience。JWKS 只从配置的 team `/cdn-cgi/access/certs` 拉取，不读取 JWT 的外部公钥 URL；缓存 5 分钟，未知 kid 刷新有限流。

Nginx 必须保留 `Cf-Access-Jwt-Assertion`；Cloudflare 必须以身份型 Access 策略保护整个网站及 API。不要对 API 添加 Bypass 策略。Bridge 不公开端口；建议 Web 只绑定回环或 cloudflared 所在 Docker 网络，避免绕过第一层。即使有人直连 Web，缺少有效 JWT 也不能调用业务 API。`/api/health` 只返回无敏感信息的存活/模式/容量标记，供容器检查。

每个 `X-Nano-Session` 同时绑定创建时的 Access issuer/sub。换 Cloudflare 账户后不能接着用旧页签令牌；刷新创建新会话。Access JWT 到期也限制本地租约。Edge 撤销/策略修改与本地签名有效期不等价；以边缘拦截、短心跳租约和 JWT exp 共同控制，不声称离线 JWT 能即时感知所有远程撤销。

## Profile 与目录

```text
/opt/nano-banana-data/
  access/cloudflare.json     # 仅服务器可写的信任配置与多管理员名单
  users/profiles.sqlite      # (issuer, sub) → 随机 Profile ID；邮箱仅辅助识别
  users/<uuid>/
    ai_config.yaml           # 此用户自己的 API Key/模型/参数；按要求不加密
    options.yaml
    presets/
    .lock
  config/                    # 管理员共享的原服务器配置
  presets/                   # 管理员共享的原服务器预设
  codex-auth/                # 原管理员长期 Codex 身份
```

API Key 明文仅存在服务器受限目录；GET 不回传密钥，只回传 has_* 状态。留空保存不覆盖已有 Key；填新值保存替换；“清除已保存密钥”是显式 DELETE，不等于撤销供应商账户上的 Key。管理员/root 能读取磁盘和备份，请只向信任此服务器的朋友开放。

同一人的多个页签共享配置/预设，但任务、参考图、结果和 Codex 授权仍按页签隔离。每 Profile 有线程锁和进程文件锁，API 配置原子写入；界面只提交改变的字段。相同字段同时修改仍最后保存者生效，已提交任务使用自己的快照。

关闭页签/90 秒失联/24 小时到期只删除短期会话、Codex 凭据和任务，不删除 Profile。刷新保留有效短期会话；服务器/容器重启后 Profile 保留，个人 Codex 需重新授权。持久目录和备份不使用加密；临时 Codex 凭据继续走 tmpfs，不把 OAuth 凭据写入 Profile。

## 身份重建

长期主键是 `(issuer, sub)`，不按浏览器提交的 profile_id 选目录。若 Cloudflare 删除后重建用户导致 sub 改变，同邮箱不会自动取得旧配置，以避免重新分配邮箱时误绑定。

站长确认确为原人后在配置中添加：

```json
"subject_aliases": {"NEW-SUB": "ORIGINAL-SUB"}
```

只允许单跳映射，不支持循环；管理员权限仍匹配当前签名身份，别名不自动授予管理员。更换整个 Cloudflare 团队时需要人工迁移索引，不自动跨 issuer 合并。

## 更新、备份、回滚

后续更新使用同一新版 `.sh`，自动继承 Access 配置并重新挂载 users。升级前停止旧 Web 后备份个人目录；回滚恢复旧容器/配置，但不覆盖升级后新写入的用户 Profile。重要持久数据应另做站长备份；升级时活跃的个人 Codex 会话会失效，这是临时授权策略。

原有 30 秒心跳、90 秒失联（5 秒后台清扫）、24 小时绝对上限和全局 4 路图片并发保持。个人 API 模式默认仅允许已支持的官方 HTTPS 服务；管理员继续支持原自定义中转。

## 验证

使用本地 RSA 测试密钥做真实 JWT 验证，覆盖多用户持久恢复、两位管理员/撤权、拒绝伪造邮箱头、同用户多标签写锁、跨身份换号、显式清除、旧模式兼容、真实 Chromium 和 Docker 持久卷升级/回滚。没有实际使用站长 Cloudflare 配置或朋友 API/Codex 额度；首次真实 Access 请求仍需站长按自己的 team/AUD 验收。

官方参考：
- https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/
- https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/application-token/
