"""临时集成的第二阶段；安全修正同样进入实际生产源码并被完整回归覆盖。"""
from pathlib import Path


def edit(path, old, new):
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise RuntimeError(f'{path}: missing {old[:100]!r}')
    p.write_text(text.replace(old, new))


p = Path('src/web/static/index.html')
s = p.read_text()
s = s.replace('<script src="/static/session-bootstrap.js"></script>\n', '')
s = s.replace('<script src="/static/sse-parser.js">', '<script src="/static/session-bootstrap.js"></script>\n<script src="/static/sse-parser.js">')
p.write_text(s)

# 官方运行时元数据而非仅用模拟登录证明设备码协议可用。
p = 'tools/verify_codex_protocol.py'
edit(p, '        if not caps["interrupt"]:\n', '''        caps['device_code_auth'] = all(key in all_text for key in (
            '"chatgptDeviceCode"', '"verificationUrl"', '"userCode"', '"loginId"'))
        if not caps['device_code_auth']:
            raise RuntimeError('此 Codex 版本没有正式设备码协议，拒绝部署多用户授权')
        if not caps["interrupt"]:
''')

# 清扫器对单个资源的清理错误不会终止所有其他用户的到期回收。
p = 'src/nano_banana/codex_bridge/leases.py'
edit(p, '        self.items: dict[str, Lease] = {}\n', '        self.items: dict[str, Lease] = {}\n        self.pending_disposals = {}\n')
edit(p, '        if lease is not None:\n            lease.closed.set()\n            self.dispose(lease)\n', '''        if lease is not None:
            lease.closed.set()
            try:
                self.dispose(lease)
            except Exception:
                with self.lock:
                    self.pending_disposals[key] = lease
''')
edit(p, '        for key in keys:\n            self.expire_key(key)\n\n    def _loop', '''        for key in keys:
            self.expire_key(key)
        with self.lock:
            pending = list(self.pending_disposals.items())
        for key, lease in pending:
            try:
                self.dispose(lease)
            except Exception:
                continue
            with self.lock:
                self.pending_disposals.pop(key, None)

    def _loop''')

# 终止已过期请求的交付，不能在长请求期间到期后仍返回私有结果。
p = 'src/nano_banana/web/user_sessions.py'
edit(p, '    def no_cache(response):\n', '''    def no_cache(response):
        scope = getattr(g, 'nano_scope', None)
        lease = getattr(g, 'nano_lease', None)
        if (scope is not None and lease is not None and manager.leases.is_expired(lease)
                and request.path != '/api/session/current'):
            response = _response({'error': '会话已失效', 'session_expired': True}, 401)
''')

# 原单用户模板在多用户下不再让裸状态标记丢失身份。
p = 'src/web/static/session-bootstrap.js'
edit(p, "    window.addEventListener('pagehide', () => {stopHeartbeats();});", "    window.addEventListener('pagehide', () => {stopHeartbeats(); clearTimeout(loginTimer);});")

# 回归必须给出具体缺少令牌的请求路径，禁止仅用无信息的 all 断言。
p = 'tools/multiuser_browser_smoke.py'
edit(p, "            assert all(token for path, token in calls if path not in {'/api/session/info', '/api/session/open'})", "            missing = [path for path, token in calls if not token and path not in {'/api/session/info', '/api/session/open'}]\n            assert missing == [], missing")
print('Multiuser finalization applied')
