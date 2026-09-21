// 页签仅保存本服务的短期随机令牌；不保存或显示 OpenAI access/refresh token。
(() => {
    'use strict';
    const rawFetch = window.fetch.bind(window);
    const KEY = 'nano.private.tab.v1';
    let token = '', active = false, role = 'personal', worker = null, fallback = null;
    let heartbeatBusy = false, loginTimer = null, releaseLock = null, channel = null;
    let lost = false, authCode = '';
    let accessInfo = null;
    const instance = crypto.randomUUID();
    const apiURL = value => new URL(typeof value === 'string' ? value : value.url, location.href);
    async function jsonRequest(path, options = {}) {
        const headers = new Headers(options.headers);
        headers.set('X-Nano-Client', 'web');
        if (token) headers.set('X-Nano-Session', token);
        const response = await rawFetch(path, {...options, headers, cache: 'no-store'});
        const data = await response.json();
        if (!response.ok) {
            if (data.session_expired || data.access_required) expireUI();
            throw new Error(data.error || `HTTP ${response.status}`);
        }
        return data;
    }
    function stopHeartbeats() {
        worker?.terminate(); worker = null;
        clearInterval(fallback); fallback = null;
    }
    function expireUI() {
        lost = true;
        token = '';
        sessionStorage.removeItem(KEY);
        stopHeartbeats(); clearTimeout(loginTimer);
        authCode = '';
        if (typeof state !== 'undefined') state.codexModels = [];
        const code = document.getElementById('nanoDeviceCode');
        if (code) code.textContent = '';
        document.querySelectorAll('input[type="password"]').forEach(el => {el.value = '';});
        renderStatus('会话已结束，请重新认证', 'error');
        const status = document.getElementById('codexStatus');
        if (status) {status.textContent = 'ChatGPT 未登录'; status.className = 'muted-text is-error';}
        window.dispatchEvent(new CustomEvent('nano-session-expired'));
    }
    function renderStatus(text, kind = '') {
        const el = document.getElementById('nanoSessionStatus');
        if (el) {el.textContent = text; el.dataset.state = kind;}
        const badge = document.getElementById('nanoAccountBtn');
        if (badge) {badge.textContent = role === 'owner' ? '管理员' : '我的 Codex'; badge.title = accessInfo?.email || '';}
        const identity = document.getElementById('nanoSiteIdentity');
        if (identity) identity.textContent = accessInfo ? '网站身份：' + accessInfo.email + (role === 'owner' ? ' · 管理员' : '') : '';
    }
    async function claimTab(candidate) {
        if (navigator.locks) {
            return new Promise(resolve => {
                navigator.locks.request('nano-tab-' + candidate, {ifAvailable: true}, lock => {
                    if (!lock) {resolve(false); return;}
                    resolve(true);
                    return new Promise(done => {releaseLock = done;});
                }).catch(() => resolve(false));
            });
        }
        // 老浏览器：避免“复制标签页”复制 sessionStorage 后无意中共享同一身份。
        if (typeof BroadcastChannel === 'undefined') return false;
        channel?.close();
        channel = new BroadcastChannel('nano-tabs');
        let conflict = false;
        channel.onmessage = event => {
            const d = event.data || {};
            if (d.token !== candidate || d.instance === instance) return;
            if (d.type === 'probe') channel.postMessage({type: 'owned', token: candidate, instance});
            if (d.type === 'owned') conflict = true;
        };
        channel.postMessage({type: 'probe', token: candidate, instance});
        await new Promise(resolve => setTimeout(resolve, 180));
        return !conflict;
    }
    async function openSession() {
        releaseLock?.(); releaseLock = null;
        channel?.close(); channel = null;
        token = '';
        const data = await jsonRequest('/api/session/open', {method: 'POST'});
        token = data.token; role = data.role; lost = false;
        sessionStorage.setItem(KEY, token);
        await claimTab(token);
        startHeartbeats();
        return data;
    }
    async function beat() {
        if (!token || heartbeatBusy) return;
        heartbeatBusy = true;
        try {
            const data = await jsonRequest('/api/session/heartbeat', {method: 'POST'});
            role = data.role;
            if (data.codex?.logged_in) renderStatus('ChatGPT 已登录', 'success');
        } catch (error) {
            if (!lost) renderStatus('连接暂时中断；恢复后重新检查授权', 'error');
        } finally {heartbeatBusy = false;}
    }
    function startHeartbeats() {
        stopHeartbeats();
        // Worker 避免普通隐藏标签页的部分计时器节流；系统冻结仍可能导致租约过期。
        try {
            worker = new Worker('/static/session-heartbeat.js');
            worker.onmessage = () => {void beat();};
            worker.onerror = () => {
                worker?.terminate(); worker = null;
                fallback ||= setInterval(() => {void beat();}, 30000);
            };
        } catch (_) {fallback = setInterval(() => {void beat();}, 30000);}
    }
    async function bootstrap() {
        const info = await jsonRequest('/api/session/info');
        if (!info.enabled) return; // 兼容单用户旧部署和离线 UI 测试。
        accessInfo = info.identity_provider === 'cloudflare' ? info : null;
        if (accessInfo) {
            const previous = sessionStorage.getItem('nano.access.identity');
            if (previous && previous !== info.identity_key) {
                sessionStorage.removeItem(KEY);
                sessionStorage.removeItem('nano-banana-form-draft');
            }
            sessionStorage.setItem('nano.access.identity', info.identity_key);
        }
        active = true;
        const saved = sessionStorage.getItem(KEY);
        if (saved && await claimTab(saved)) {
            token = saved;
            try {
                const state = await jsonRequest('/api/session/heartbeat', {method: 'POST'});
                role = state.role; lost = false; startHeartbeats(); return;
            } catch (_) {token = ''; sessionStorage.removeItem(KEY);}
        }
        await openSession();
    }
    const ready = bootstrap();
    // 既有表单/预设/图片/流式 Prompt 请求统一带上本页签身份，绝不放进 URL。
    window.fetch = async (input, init = {}) => {
        const url = apiURL(input);
        if (url.origin !== location.origin || !url.pathname.startsWith('/api/')) return rawFetch(input, init);
        await ready;
        if (!active) return rawFetch(input, init);
        if (!token || lost) throw new Error('本页会话已结束，请重新登录');
        const headers = new Headers(input instanceof Request ? input.headers : undefined);
        new Headers(init.headers).forEach((value, key) => headers.set(key, value));
        headers.set('X-Nano-Session', token);
        const response = await rawFetch(input, {...init, headers, cache: 'no-store'});
        if (response.status === 401 || response.status === 403 || response.status === 503) {
            const data = await response.clone().json().catch(() => ({}));
            if (data.session_expired || data.access_required) expireUI();
        }
        return response;
    };
    function mount() {
        if (document.getElementById('nanoSessionModal')) return;
        const modal = document.createElement('div');
        modal.id = 'nanoSessionModal'; modal.className = 'modal';
        modal.innerHTML = '<div class="modal-content"><div class="modal-header"><h3>我的 Codex 账户</h3><button id="nanoSessionClose" class="modal-close" type="button" aria-label="关闭">×</button></div>'
          + '<div class="modal-body nano-auth-body"><p id="nanoSiteIdentity"></p><p id="nanoSessionStatus" role="status">尚未认证</p>'
          + '<p>仅使用你自己的额度。刷新保留登录；关闭页签后按心跳失联回收，最长 24 小时。</p>'
          + '<button id="nanoDeviceStart" type="button" class="btn btn-primary">登录我的 ChatGPT / Codex</button>'
          + '<div id="nanoDevicePanel" hidden><p>请在 OpenAI 官方页面输入下面的设备码：</p><strong id="nanoDeviceCode"></strong>'
          + '<div class="nano-auth-actions"><button id="nanoDeviceCopy" type="button" class="btn btn-secondary">复制设备码</button><a id="nanoDeviceLink" class="btn btn-secondary" target="_blank" rel="noopener noreferrer">打开官方授权页面</a></div>'
          + '<p>授权的是此服务器上的临时 Codex 客户端；不要把设备码交给别人。</p></div>'
          + '<button id="nanoSessionLogout" type="button" class="btn btn-secondary">退出并销毁此会话</button>'
          + '<details><summary>服务器管理员</summary><p>管理员模式才可以使用服务器已有 API 配置和 Codex 身份。</p><input id="nanoOwnerKey" type="password" class="text-input" autocomplete="off" placeholder="管理员密钥"><button id="nanoOwnerLogin" type="button" class="btn btn-secondary">进入管理员模式</button></details></div></div>';
        if (accessInfo) {
            modal.querySelector('details').hidden = true;
            document.getElementById('nanoSessionStatus');
            const description = modal.querySelector('.nano-auth-body > p:nth-of-type(3)');
            if (description) description.textContent = '网站身份由 Cloudflare 验证；API 配置和预设永久保存。Codex 授权仅用于当前页签，30 秒心跳、90 秒失联回收、最长 24 小时。';
        }
        document.body.appendChild(modal);
        const button = document.createElement('button');
        button.id = 'nanoAccountBtn'; button.className = 'btn btn-secondary'; button.type = 'button';
        button.textContent = role === 'owner' ? '管理员' : '我的 Codex';
        button.title = accessInfo?.email || '';
        document.getElementById('nanoSiteIdentity').textContent = accessInfo ? '网站身份：' + accessInfo.email + (role === 'owner' ? ' · 管理员' : '') : '';
        (document.querySelector('.header-actions') || document.querySelector('.app-header') || document.body).appendChild(button);
        button.onclick = () => {modal.classList.add('active'); void refreshLogin();};
        document.getElementById('nanoSessionClose').onclick = () => modal.classList.remove('active');
        document.getElementById('nanoDeviceCopy').onclick = async () => {
            try {await navigator.clipboard.writeText(authCode);} catch (_) {renderStatus('请选中设备码手动复制');}
        };
        document.getElementById('nanoDeviceStart').onclick = async event => {
            event.target.disabled = true;
            try {
                if (!token) await openSession();
                renderStatus('正在创建官方设备授权…');
                await jsonRequest('/api/session/codex/login', {method: 'POST'});
                await refreshLogin(true);
            } catch (error) {renderStatus(error.message, 'error');}
            finally {event.target.disabled = false;}
        };
        document.getElementById('nanoSessionLogout').onclick = async () => {
            try {if (token) await jsonRequest('/api/session/current', {method: 'DELETE'});} catch (_) {}
            expireUI(); releaseLock?.(); releaseLock = null;
            channel?.close(); channel = null;
            // 新建空白个人身份，保留页面编辑器，但不恢复已销毁的凭据/私有配置。
            try {await openSession(); await reloadWorkbench(); renderStatus(accessInfo ? 'Codex 会话已销毁；已重新加载此 Cloudflare 身份的持久配置' : '已退出；当前是新的未认证个人会话');}
            catch (error) {renderStatus(error.message, 'error');}
        };
        document.getElementById('nanoOwnerLogin').onclick = async () => {
            const input = document.getElementById('nanoOwnerKey'), key = input.value;
            input.value = '';
            try {
                if (!token) await openSession();
                const data = await jsonRequest('/api/session/owner', {method: 'POST',
                    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({key})});
                role = data.role;
                await reloadWorkbench(); renderStatus('管理员模式；使用服务器配置', 'success');
            } catch (error) {renderStatus(error.message, 'error');}
        };
    }
    async function reloadWorkbench() {
        if (typeof loadConfig === 'function') await loadConfig();
        if (typeof loadImageProviders === 'function') await loadImageProviders();
        if (typeof loadCodexSettings === 'function') loadCodexSettings();
    }
    async function refreshLogin(poll = false) {
        clearTimeout(loginTimer);
        if (!token) {renderStatus('会话已结束，请重新登录', 'error'); return;}
        try {
            const data = await jsonRequest('/api/codex/status');
            const panel = document.getElementById('nanoDevicePanel');
            panel.hidden = !data.user_code;
            if (data.user_code) {
                authCode = data.user_code;
                document.getElementById('nanoDeviceCode').textContent = authCode;
                const url = new URL(data.verification_url);
                if (url.protocol !== 'https:' || url.hostname !== 'auth.openai.com') throw new Error('非官方授权地址已拒绝');
                document.getElementById('nanoDeviceLink').href = url.href;
                renderStatus('等待你在官方页面完成授权…');
            } else if (data.logged_in) {
                authCode = ''; document.getElementById('nanoDeviceCode').textContent = '';
                renderStatus('ChatGPT 已登录', 'success');
                if (typeof refreshCodexStatus === 'function' && document.getElementById('codexStatus')) await refreshCodexStatus();
                await beat();
                return;
            } else renderStatus(data.error || (data.state === 'starting' ? '正在获取设备码…' : 'ChatGPT 未登录'), data.error ? 'error' : '');
            if (poll && ['starting', 'pending'].includes(data.state)) loginTimer = setTimeout(() => {void refreshLogin(true);}, 2000);
        } catch (error) {renderStatus(error.message, 'error');}
    }
    window.NanoSession = {ready, get enabled() {return active;}, get role() {return role;}, get accessIdentity() {return accessInfo;},
        open() {document.getElementById('nanoSessionModal')?.classList.add('active'); void refreshLogin();}};
    ready.then(() => {
        if (!active) return;
        if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, {once: true});
        else mount();
    }).catch(error => {
        console.error('页面会话初始化失败');
        const show = () => {mount(); renderStatus(error.message, 'error'); document.getElementById('nanoSessionModal').classList.add('active');};
        if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', show, {once: true}); else show();
    });
    document.addEventListener('visibilitychange', () => {if (!document.hidden && active) void beat();});
    window.addEventListener('pageshow', () => {if (active && token) {startHeartbeats(); void beat();}});
    window.addEventListener('pagehide', () => {stopHeartbeats(); clearTimeout(loginTimer);}); // 不注销：刷新也会触发 pagehide。
})();
