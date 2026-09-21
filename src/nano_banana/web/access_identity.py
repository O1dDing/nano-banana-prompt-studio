"""只信任固定 team/AUD 的 RS256 Access 用户 JWT；不信任邮箱头、浏览器身份参数或 Service Token。"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass

import httpx
import jwt

from nano_banana.core.access_config import AccessConfig, AccessConfigError, email_key


class AccessDenied(PermissionError):
    pass


class AccessUnavailable(RuntimeError):
    pass


def required():
    return os.getenv('NANO_ACCESS_REQUIRED', '0') == '1'


@dataclass(frozen=True)
class Identity:
    issuer: str
    subject: str
    email: str
    expires: int

    @property
    def key(self):
        return (self.issuer, self.subject)


class AccessVerifier:
    def __init__(self, path, *, fetch_keys=None, clock=time.time):
        self.path, self.clock = path, clock
        self.fetch_keys = fetch_keys or self._download_keys
        self.lock = threading.Lock()
        self.keys, self.key_issuer = {}, ''
        self.fetched = 0.0
        self.attempted = float('-inf')

    def config(self):
        # 每次读取小型只读配置，管理员增删/错误配置下次请求立即生效。
        # 不能在读取失败时回退旧配置，防止已移除管理员继续使用旧权限。
        try:
            return AccessConfig.load(self.path)
        except (OSError, ValueError) as exc:
            raise AccessUnavailable('Access 配置不可用，请联系服务器管理员') from exc

    @staticmethod
    def _download_keys(issuer):
        # URL 只来自服务器已校验配置；不跟随 JWT 中的 jku/x5u 或重定向。
        with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as client:
            with client.stream('GET', issuer + '/cdn-cgi/access/certs') as response:
                response.raise_for_status()
                raw = bytearray()
                for part in response.iter_bytes():
                    raw.extend(part)
                    if len(raw) > 262144:
                        raise AccessUnavailable('Access 公钥响应过大')
        return json.loads(raw)

    def signing_key(self, issuer, kid):
        now = self.clock()
        with self.lock:
            if issuer != self.key_issuer:
                self.keys, self.key_issuer = {}, issuer
                self.fetched, self.attempted = 0.0, float('-inf')
            fresh = now - self.fetched < 300
            if kid in self.keys and fresh:
                return self.keys[kid]
            # 防止伪造随机 kid 造成每次请求都向 Cloudflare 拉公钥。
            if now - self.attempted < 5:
                raise AccessDenied('Access 签名公钥暂不可用，请稍后重试')
            self.attempted = now
            try:
                payload = self.fetch_keys(issuer)
                entries = payload.get('keys') if isinstance(payload, dict) else None
                if not isinstance(entries, list) or not 1 <= len(entries) <= 32:
                    raise ValueError('JWKS 格式错误')
                keys = {}
                for entry in entries:
                    if (not isinstance(entry, dict) or entry.get('kty') != 'RSA'
                            or entry.get('alg', 'RS256') != 'RS256' or entry.get('use', 'sig') != 'sig'):
                        continue
                    name = entry.get('kid')
                    if not isinstance(name, str) or not 1 <= len(name) <= 256 or name in keys:
                        raise ValueError('kid 无效或重复')
                    key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(entry))
                    if key.key_size < 2048:
                        raise ValueError('RSA 公钥太短')
                    keys[name] = key
                if not keys:
                    raise ValueError('没有可用公钥')
                self.keys, self.fetched = keys, now
            except Exception as exc:
                raise AccessUnavailable('无法更新 Cloudflare 公钥；拒绝未验证请求') from exc
            if kid not in self.keys:
                raise AccessDenied('Access 签名公钥不匹配')
            return self.keys[kid]

    def verify(self, token):
        settings = self.config()
        if not isinstance(token, str) or not 1 <= len(token) <= 16384 or token.count('.') != 2:
            raise AccessDenied('缺少有效 Cloudflare Access 身份，请通过受保护域名访问')
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get('kid')
            if (header.get('alg') != 'RS256' or not isinstance(kid, str) or not 1 <= len(kid) <= 256
                    or any(k in header for k in ('jku', 'x5u', 'crit'))):
                raise AccessDenied('不接受此 Access 签名算法或头部')
            key = self.signing_key(settings.issuer, kid)
            claims = jwt.decode(token, key, algorithms=['RS256'], audience=list(settings.audiences),
                                issuer=settings.issuer, leeway=10,
                                options={'require': ['iss', 'aud', 'sub', 'email', 'type', 'exp', 'iat', 'nbf']})
            if claims.get('type') != 'app' or claims.get('common_name'):
                raise AccessDenied('只接受用户 Access 身份，不接受服务令牌')
            subject = claims['sub']
            if not isinstance(subject, str) or not 1 <= len(subject) <= 512:
                raise AccessDenied('缺少 Access 用户标识')
            if any(not isinstance(claims[k], (int, float)) or isinstance(claims[k], bool)
                   for k in ('exp', 'iat', 'nbf')):
                raise AccessDenied('Access 时间声明无效')
            if claims['exp'] <= self.clock() or claims['exp'] <= claims['iat']:
                raise AccessDenied('Cloudflare Access 登录已过期')
            identity = Identity(settings.issuer, subject, email_key(claims['email']), int(claims['exp']))
            return identity, settings
        except (jwt.PyJWTError, AccessConfigError, KeyError, TypeError, ValueError) as exc:
            raise AccessDenied('Cloudflare Access 身份校验失败，请重新登录') from exc
