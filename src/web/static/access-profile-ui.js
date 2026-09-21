// 只展示是否已配置；API Key 明文不由 GET 回传。身份/管理员名单不能在此修改。
function refreshProfileKeyControls() {
    const fields = {
        configApiKey: 'api_key', configGeminiApiKey: 'gemini_api_key',
        configOpenAIImageApiKey: 'openai_image_api_key', configQwenImageApiKey: 'qwen_image_api_key',
        configDoubaoImageApiKey: 'doubao_image_api_key'
    };
    for (const [id, key] of Object.entries(fields)) {
        const input = document.getElementById(id);
        if (!input) continue;
        let row = document.getElementById(id + 'SavedState');
        if (!row) {
            row = document.createElement('div'); row.id = id + 'SavedState';
            row.className = 'nano-key-state';
            const status = document.createElement('small');
            const clear = document.createElement('button');
            clear.type = 'button'; clear.className = 'btn btn-secondary btn-sm';
            clear.textContent = '清除已保存密钥';
            clear.onclick = async () => {
                if (!confirm('确定清除当前配置中的这把 API Key？此操作不会撤销供应商账户上的 Key。')) return;
                clear.disabled = true;
                try {
                    const response = await fetch('/api/config/keys/' + encodeURIComponent(key), {method: 'DELETE'});
                    if (!response.ok) throw new Error((await response.json()).error || response.statusText);
                    input.value = '';
                    await Promise.all([loadConfig(), loadImageProviders()]);
                    refreshProfileKeyControls();
                    showToast('已清除保存的密钥', 'success');
                } catch (error) {showToast(error.message, 'error');}
                finally {clear.disabled = false;}
            };
            row.append(status, clear); input.insertAdjacentElement('afterend', row);
        }
        const saved = Boolean(state.config['has_' + key]);
        row.querySelector('small').textContent = saved ? '已保存；留空不修改，输入新值后保存即可替换。' : '尚未保存';
        row.querySelector('button').hidden = !saved;
    }
}
