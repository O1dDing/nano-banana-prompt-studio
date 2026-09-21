"""把已验证 Access 身份绑定到既有页签租约，不改变 Codex 临时授权协议。"""
from __future__ import annotations

import hashlib
import os
import time

from flask import g, jsonify, request

from nano_banana.web.access_identity import AccessDenied, AccessUnavailable, AccessVerifier
from nano_banana.web.profiles import ProfileConflict, ProfileStore
from nano_banana.codex_bridge.leases import ExpiredSession


class AccessBinding:
    def __init__(self, app, sessions):
        self.sessions = sessions
        self.verifier = AccessVerifier(os.environ.get('NANO_ACCESS_CONFIG_FILE', '/run/nano-access/cloudflare.json'))
        self.verifier.config()  # 启动失败必须在部署健康检查暴露，不能悄悄退成匿名。
        self.profiles = ProfileStore(os.environ.get('NANO_PROFILES_DIR', '/app/users'))
        from nano_banana.web.context import _legacy
        self.profiles.protect_legacy(_legacy)
        app.extensions['nano_access'] = self

        @app.errorhandler(AccessDenied)
        def denied(_exc):
            return jsonify(error='Cloudflare Access 身份校验失败，请通过受保护域名重新登录',
                           access_required=True), 403

        @app.errorhandler(AccessUnavailable)
        def unavailable(_exc):
            return jsonify(error='Access 验证配置或公钥暂不可用，请联系服务器管理员',
                           access_required=True), 503

        @app.errorhandler(ProfileConflict)
        def conflict(exc):
            return jsonify(error=str(exc)), 409

        @app.before_request
        def verify_access():
            if not request.path.startswith('/api/') or request.path == '/api/health':
                return
            identity, settings = self.verifier.verify(request.headers.get('Cf-Access-Jwt-Assertion', ''))
            g.nano_access_identity, g.nano_access_settings = identity, settings
            if request.path in {'/api/session/info', '/api/session/open'}:
                return
            lease = sessions.leases.get(request.headers.get('X-Nano-Session', ''))
            scope = lease.state['scope']
            if getattr(scope, 'cf_key', None) != identity.key:
                # 别人的合法 JWT + 被复制的页签令牌也不能进入该 Profile。
                # 不让攻击者仅凭别人的令牌即可注销受害者会话。
                return jsonify(error='网站登录身份已改变，请刷新页面', session_expired=True,
                               identity_changed=True), 401
            if (scope.owner != settings.is_admin(identity.subject, identity.email)
                    or scope.cf_email != identity.email
                    or scope.cf_canonical != settings.canonical_subject(identity.subject)):
                sessions.leases.expire_key(lease.key)
                return jsonify(error='管理员权限或身份映射已更新，请刷新页面',
                               session_expired=True), 401
            self._access_deadline(lease, identity)
            if request.path == '/api/session/owner':
                return jsonify(error='管理员只由服务器 Access 配置指定；网页密钥提权已关闭'), 403

    def _access_deadline(self, lease, identity):
        with lease.lock:
            lease.state['access_deadline'] = self.sessions.leases.clock() + max(0, identity.expires - time.time())

    def info(self):
        identity = g.nano_access_identity
        settings = g.nano_access_settings
        return {'identity_provider': 'cloudflare', 'email': identity.email,
                'is_admin': settings.is_admin(identity.subject, identity.email),
                'profile_persistent': True,
                'identity_key': hashlib.sha256((identity.issuer + '\0' + identity.subject).encode()).hexdigest()}

    def attach(self, lease):
        identity, settings = g.nano_access_identity, g.nano_access_settings
        scope = lease.state['scope']
        try:
            with scope.lock:
                scope.cf_key = identity.key
                scope.cf_email = identity.email
                scope.cf_canonical = settings.canonical_subject(identity.subject)
                scope.owner = settings.is_admin(identity.subject, identity.email)
                scope.profile_id = 'server' if scope.owner else ''
                if not scope.owner:
                    profile_id, bundle = self.profiles.resolve(identity, settings)
                    scope.profile_id = profile_id
                    scope.config_manager = bundle.config_manager
                    scope.preset_manager = bundle.preset_manager
                    scope.yaml_handler = bundle.yaml_handler
                self._access_deadline(lease, identity)
        except BaseException:
            self.sessions.leases.expire_key(lease.key)
            raise

    def summary(self, lease):
        return {**self.info(), 'profile_id': lease.state['scope'].profile_id}
