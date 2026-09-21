"""服务器专属 Access 配置。不能经 /api/config 修改，不保存任何 OAuth 凭证。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


class AccessConfigError(ValueError):
    pass


def email_key(value: str) -> str:
    if not isinstance(value, str):
        raise AccessConfigError('邮箱必须是字符串')
    value = value.strip().casefold()
    if len(value) > 254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value):
        raise AccessConfigError('邮箱格式无效；不接受通配符')
    if '*' in value:
        raise AccessConfigError('管理员邮箱不接受通配符')
    return value


def string_list(data, key, *, required=False):
    values = data.get(key, [])
    if (not isinstance(values, list) or len(values) > 256
            or any(not isinstance(v, str) or not v.strip() or len(v) > 512 for v in values)):
        raise AccessConfigError(f'{key} 必须是字符串数组')
    result = tuple(dict.fromkeys(v.strip() for v in values))
    if required and not result:
        raise AccessConfigError(f'{key} 不能为空')
    return result


@dataclass(frozen=True)
class AccessConfig:
    issuer: str
    audiences: tuple[str, ...]
    admin_emails: tuple[str, ...]
    admin_subjects: tuple[str, ...]
    auto_create: bool
    subject_aliases: dict[str, str]

    @classmethod
    def parse(cls, data):
        allowed = {'issuer', 'audiences', 'admin_emails', 'admin_subjects', 'auto_create', 'subject_aliases'}
        if not isinstance(data, dict) or set(data) - allowed:
            raise AccessConfigError('Access 配置包含未知字段或不是 JSON 对象')
        issuer = data.get('issuer', '')
        if not isinstance(issuer, str):
            raise AccessConfigError('issuer 必须是 HTTPS team domain')
        issuer = issuer.strip().rstrip('/')
        parsed = urlsplit(issuer)
        if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path or parsed.port is not None
                or not re.fullmatch(r'[a-z0-9][a-z0-9-]*\.cloudflareaccess\.com', parsed.netloc)):
            raise AccessConfigError('issuer 必须是 https://你的团队.cloudflareaccess.com，不从来访 JWT 自动学习')
        admins = tuple(email_key(v) for v in string_list(data, 'admin_emails'))
        subjects = string_list(data, 'admin_subjects')
        if not admins and not subjects:
            raise AccessConfigError('至少配置一名管理员：admin_emails 或 admin_subjects')
        auto = data.get('auto_create', True)
        aliases = data.get('subject_aliases', {})
        if not isinstance(auto, bool) or not isinstance(aliases, dict) or len(aliases) > 256:
            raise AccessConfigError('auto_create / subject_aliases 类型无效')
        for new, old in aliases.items():
            if (not isinstance(new, str) or not isinstance(old, str) or not new or not old
                    or max(len(new), len(old)) > 512 or new == old or old in aliases):
                raise AccessConfigError('subject_aliases 必须为新 sub → 原 sub，禁止链式或循环映射')
        return cls(issuer, string_list(data, 'audiences', required=True), admins, subjects, auto, dict(aliases))

    @classmethod
    def load(cls, path):
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise AccessConfigError('缺少服务器 Access 配置文件')
        raw = path.read_bytes()
        if len(raw) > 65536:
            raise AccessConfigError('Access 配置过大')
        try:
            return cls.parse(json.loads(raw))
        except (ValueError, TypeError) as exc:
            raise AccessConfigError('Access 配置无效：' + str(exc)) from exc

    def is_admin(self, subject, email):
        # 授权只匹配当前经签名验证的身份，不因数据库别名自动获得管理员权限。
        return subject in self.admin_subjects or email_key(email) in self.admin_emails

    def canonical_subject(self, subject):
        return self.subject_aliases.get(subject, subject)
