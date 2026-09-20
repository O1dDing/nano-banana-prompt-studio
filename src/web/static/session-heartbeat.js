// 无凭据、无网络请求；仅通知主页面发送同源心跳。
setInterval(() => postMessage('heartbeat'), 30000);
