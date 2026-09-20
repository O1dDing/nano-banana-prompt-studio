// API / Codex 双通道。此模块不持有 Codex 或图片 API 登录凭据。
function initCodexControls() {
    const section = elements.configModel.closest('.config-section');
    if (!document.getElementById('configChatEngine')) {
        const box = document.createElement('div');
        box.innerHTML = '<div class="form-group"><label for="configChatEngine">提示词后端</label><select id="configChatEngine" class="select-input"><option value="api">原有 API</option><option value="codex">Codex 套餐（独立临时会话）</option></select></div>'
          + '<div class="form-group"><label>Codex 对话模型（留空使用账户默认）</label><div id="codexModelPicker" class="codex-model-picker"><input id="configCodexModel" type="hidden"><button id="configCodexModelButton" class="select-input codex-model-trigger" type="button" aria-haspopup="listbox" aria-expanded="false"><span class="codex-model-trigger-copy"><strong id="configCodexModelLabel">账户默认模型</strong><span id="configCodexModelId">留空，由 Codex 选择默认模型</span></span></button><div id="codexModelOptions" class="codex-model-menu" role="listbox" hidden></div></div></div>'
          + '<div class="form-group"><label for="configCodexEffort">Codex 推理强度</label><select id="configCodexEffort" class="select-input"><option value="auto">auto</option></select><small id="codexEffortHelp" class="muted-text">选择模型后按账户返回的能力动态更新。</small></div>'
          + '<button id="refreshCodexStatus" class="btn btn-secondary" type="button">检查 Codex 登录/模型</button><p id="codexStatus" role="status" class="muted-text">Codex 状态未检查</p>';
        section.insertBefore(box, section.children[1]);
        document.getElementById('configChatEngine').addEventListener('change', toggleCodexSettings);
        document.getElementById('refreshCodexStatus').addEventListener('click', refreshCodexStatus);
        initCodexModelPicker();
        for (const id of ['configBaseUrl', 'configApiKey', 'configModel']) {
            document.getElementById(id).closest('.form-group').dataset.apiPrompt = 'true';
        }
        elements.configImageProvider.add(new Option('Codex Image', 'codex_images'));
        const notice = document.createElement('div');
        notice.className = 'form-group image-config-group';
        notice.dataset.providerConfig = 'codex_images';
        notice.textContent = '使用专用 Codex 容器中的 ChatGPT 登录，无需 API Key。图片模型由内置工具决定，不支持指定 Image 2.5。生成参数在主界面显示；质量/尺寸为提示性要求，格式转换为本地后处理。';
        elements.configImageProvider.closest('.config-section').appendChild(notice);
        initOpenAIImageModelPicker();
    }
}


const OPENAI_IMAGE_MODEL_FALLBACKS = [
    'gpt-image-2',
    'gpt-image-2.5-sunburst',
    'gpt-image-2.5-flare'
];

function openAIImageModelSuggestions() {
    const providerModels = state.imageProviders?.openai_images?.models || [];
    const current = elements.configOpenAIImageModel?.value?.trim()
        || state.config.openai_image_model
        || '';
    return [...new Set([...providerModels, ...OPENAI_IMAGE_MODEL_FALLBACKS, current].filter(Boolean))];
}

function renderOpenAIImageModelOptions() {
    const menu = document.getElementById('openaiImageModelOptions');
    if (!menu) return;
    const current = elements.configOpenAIImageModel?.value?.trim() || '';
    menu.replaceChildren(...openAIImageModelSuggestions().map(model => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'codex-model-option openai-image-model-option';
        button.dataset.modelId = model;
        button.setAttribute('role', 'option');
        button.setAttribute('aria-selected', String(model === current));
        const label = document.createElement('strong');
        label.textContent = model;
        button.appendChild(label);
        button.addEventListener('click', () => {
            elements.configOpenAIImageModel.value = model;
            elements.configOpenAIImageModel.dispatchEvent(new Event('input', {bubbles: true}));
            closeOpenAIImageModelPicker();
        });
        return button;
    }));
}

function closeOpenAIImageModelPicker() {
    const picker = document.getElementById('openaiImageModelPicker');
    const toggle = document.getElementById('openaiImageModelToggle');
    const menu = document.getElementById('openaiImageModelOptions');
    if (!picker || !toggle || !menu) return;
    picker.classList.remove('is-open');
    toggle.setAttribute('aria-expanded', 'false');
    menu.hidden = true;
}

function initOpenAIImageModelPicker() {
    const input = elements.configOpenAIImageModel;
    if (!input || document.getElementById('openaiImageModelPicker')) return;

    // Chromium 为 input[list] 绘制自己的 datalist 箭头，无法和 select 统一。
    // 保留自由输入能力，但用自己的无边框箭头 + 建议菜单替代浏览器原生 indicator。
    input.removeAttribute('list');
    const parent = input.parentElement;
    const picker = document.createElement('div');
    picker.id = 'openaiImageModelPicker';
    picker.className = 'openai-image-model-picker';
    parent.insertBefore(picker, input);
    picker.appendChild(input);
    input.classList.add('openai-image-model-input');

    const toggle = document.createElement('button');
    toggle.id = 'openaiImageModelToggle';
    toggle.type = 'button';
    toggle.className = 'openai-image-model-toggle';
    toggle.setAttribute('aria-label', '选择 OpenAI Images 模型');
    toggle.setAttribute('aria-haspopup', 'listbox');
    toggle.setAttribute('aria-expanded', 'false');

    const menu = document.createElement('div');
    menu.id = 'openaiImageModelOptions';
    menu.className = 'codex-model-menu openai-image-model-menu';
    menu.setAttribute('role', 'listbox');
    menu.hidden = true;
    picker.append(toggle, menu);

    toggle.addEventListener('click', event => {
        event.stopPropagation();
        const opening = !picker.classList.contains('is-open');
        closeOpenAIImageModelPicker();
        if (opening) {
            renderOpenAIImageModelOptions();
            picker.classList.add('is-open');
            toggle.setAttribute('aria-expanded', 'true');
            menu.hidden = false;
        }
    });
    input.addEventListener('input', () => {
        if (!menu.hidden) renderOpenAIImageModelOptions();
    });
    input.addEventListener('keydown', event => {
        if (event.key === 'Escape') closeOpenAIImageModelPicker();
    });
    document.addEventListener('click', event => {
        if (!picker.contains(event.target)) closeOpenAIImageModelPicker();
    });
}

function codexModelFriendlyName(modelId) {
    const value = String(modelId || '').trim();
    if (!value) return '账户默认模型';
    const stripped = value.replace(/^gpt-/i, '');
    return stripped.split('-').map(part => {
        if (/^\d+(?:\.\d+)*$/.test(part)) return part;
        return part ? part.charAt(0).toUpperCase() + part.slice(1) : part;
    }).join(' ');
}

function codexEffortValues(model) {
    const raw = model?.supportedReasoningEfforts || [];
    const values = raw.map(item => typeof item === 'string' ? item : item?.reasoningEffort).filter(Boolean);
    return [...new Set(values)];
}

function findCodexModel(modelId) {
    const models = Array.isArray(state.codexModels) ? state.codexModels : [];
    if (modelId) return models.find(item => (item.model || item.id) === modelId) || null;
    return models.find(item => item.isDefault) || null;
}

function renderCodexModelOptions() {
    const menu = document.getElementById('codexModelOptions');
    if (!menu) return;
    const current = document.getElementById('configCodexModel')?.value || '';
    const models = Array.isArray(state.codexModels) ? state.codexModels : [];
    const entries = [{model: '', displayName: '账户默认模型', isDefault: true}, ...models];

    if (current && !entries.some(item => (item.model || item.id || '') === current)) {
        entries.push({model: current, displayName: codexModelFriendlyName(current), unavailable: true});
    }

    menu.replaceChildren(...entries.map(item => {
        const id = item.model || item.id || '';
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'codex-model-option';
        button.setAttribute('role', 'option');
        button.dataset.modelId = id;
        button.setAttribute('aria-selected', String(id === current));

        const primary = document.createElement('strong');
        primary.textContent = id ? codexModelFriendlyName(id) : '账户默认模型';
        const secondary = document.createElement('span');
        secondary.textContent = id || '留空，由 Codex 选择默认模型';
        if (item.unavailable) secondary.textContent += ' · 当前账户列表未返回';

        button.append(primary, secondary);
        button.addEventListener('click', () => {
            setCodexModelSelection(id, true);
            closeCodexModelPicker();
        });
        return button;
    }));
}

function setCodexModelSelection(modelId, updateEffort = true) {
    const input = document.getElementById('configCodexModel');
    const label = document.getElementById('configCodexModelLabel');
    const idText = document.getElementById('configCodexModelId');
    if (!input || !label || !idText) return;

    input.value = modelId || '';
    label.textContent = modelId ? codexModelFriendlyName(modelId) : '账户默认模型';
    idText.textContent = modelId || '留空，由 Codex 选择默认模型';

    document.querySelectorAll('#codexModelOptions .codex-model-option').forEach(option => {
        option.setAttribute('aria-selected', String(option.dataset.modelId === input.value));
    });
    if (updateEffort) updateCodexEffortOptions(input.value, document.getElementById('configCodexEffort')?.value || 'auto');
}

function updateCodexEffortOptions(modelId, preferred = 'auto') {
    const select = document.getElementById('configCodexEffort');
    const help = document.getElementById('codexEffortHelp');
    if (!select) return;

    const model = findCodexModel(modelId);
    const reported = codexEffortValues(model);
    const values = ['auto', ...reported.filter(value => value !== 'auto')];
    if (preferred && !values.includes(preferred) && !model) values.push(preferred);

    select.replaceChildren(...values.map(value => new Option(value, value)));
    const fallback = model?.defaultReasoningEffort && values.includes(model.defaultReasoningEffort)
        ? model.defaultReasoningEffort
        : 'auto';
    select.value = values.includes(preferred) ? preferred : fallback;

    if (help) {
        const target = modelId || (model?.model || model?.id || '');
        help.textContent = reported.length
            ? `${target ? codexModelFriendlyName(target) : '账户默认模型'} 当前账户支持：${reported.join(' / ')}；auto 使用 Codex 默认强度。`
            : '尚未读取该模型能力；点击“检查 Codex 登录/模型”后动态更新。';
    }
}

function closeCodexModelPicker() {
    const picker = document.getElementById('codexModelPicker');
    const button = document.getElementById('configCodexModelButton');
    const menu = document.getElementById('codexModelOptions');
    if (!picker || !button || !menu) return;
    picker.classList.remove('is-open');
    button.setAttribute('aria-expanded', 'false');
    menu.hidden = true;
}

function initCodexModelPicker() {
    const picker = document.getElementById('codexModelPicker');
    const button = document.getElementById('configCodexModelButton');
    const menu = document.getElementById('codexModelOptions');
    if (!picker || !button || !menu || button.dataset.bound === 'true') return;
    button.dataset.bound = 'true';

    button.addEventListener('click', event => {
        event.stopPropagation();
        const opening = !picker.classList.contains('is-open');
        closeCodexModelPicker();
        if (opening) {
            renderCodexModelOptions();
            picker.classList.add('is-open');
            button.setAttribute('aria-expanded', 'true');
            menu.hidden = false;
        }
    });
    button.addEventListener('keydown', event => {
        if (event.key === 'Escape') closeCodexModelPicker();
    });
    document.addEventListener('click', event => {
        if (!picker.contains(event.target)) closeCodexModelPicker();
    });
}

function loadCodexSettings() {
    initCodexControls();
    document.getElementById('configChatEngine').value = state.config.chat_engine || 'api';
    setCodexModelSelection(state.config.codex_model || '', false);
    updateCodexEffortOptions(state.config.codex_model || '', state.config.codex_effort || 'auto');
    toggleCodexSettings();
}

function collectCodexSettings() {
    return {chat_engine: document.getElementById('configChatEngine').value,
            codex_model: document.getElementById('configCodexModel').value.trim(),
            codex_effort: document.getElementById('configCodexEffort').value};
}

function toggleCodexSettings() {
    const codex = document.getElementById('configChatEngine').value === 'codex';
    document.querySelectorAll('[data-api-prompt]').forEach(el => el.hidden = codex);
    // Codex 对话模型也供 Codex Image 的调度使用，始终保留配置入口。
}

function setCodexStatusState(output, stateName, message, detail = '') {
    output.classList.remove('is-success', 'is-error', 'is-pending');
    output.classList.add(stateName);
    output.textContent = message;
    output.title = detail || '';
}

async function refreshCodexStatus() {
    const output = document.getElementById('codexStatus');
    setCodexStatusState(output, 'is-pending', '检查中…');
    try {
        const response = await fetch('/api/codex/status', {cache: 'no-store'});
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        if (data.logged_in) {
            setCodexStatusState(output, 'is-success', 'ChatGPT 已登录');
        } else {
            setCodexStatusState(output, 'is-error', 'ChatGPT 未登录', data.error || '');
        }
        state.codexModels = Array.isArray(data.models) ? data.models : [];
        renderCodexModelOptions();
        setCodexModelSelection(document.getElementById('configCodexModel').value || state.config.codex_model || '', false);
        updateCodexEffortOptions(
            document.getElementById('configCodexModel').value || state.config.codex_model || '',
            document.getElementById('configCodexEffort').value || state.config.codex_effort || 'auto'
        );
        // 只读取元数据，不触发设置保存，也不改变本页已选中的 API/模型。
        await loadImageProviders();
        if (data.logged_in && !Array.from(elements.imageProviderSelect.options).some(o => o.value === 'codex_images')) {
            elements.imageProviderSelect.add(new Option('Codex Image', 'codex_images'));
            elements.imageProviderSelect.disabled = false;
        }
    } catch (error) {
        setCodexStatusState(output, 'is-error', 'Codex 状态检查失败', error.message);
    }
}

function renderAdvancedImageOptions() {
    const provider = getActiveImageProvider(), model = getActiveImageModel();
    const caps = state.imageProviders[provider]?.capabilities?.[model] || {};
    const saved = getSavedImageOptions(provider, model);
    const target = elements.imageProviderOptions;
    target.replaceChildren();
    if (caps.notice) {
        const notice = document.createElement('p');
        notice.className = 'muted-text'; notice.style.gridColumn = '1 / -1';
        notice.textContent = caps.notice;
        target.appendChild(notice);
    }
    const inputs = {};
    for (const [key, option] of Object.entries(caps.options || {})) {
        const group = document.createElement('div'); group.className = 'form-group';
        const label = document.createElement('label'); label.textContent = option.label;
        label.htmlFor = 'image-option-' + key;
        let input;
        if (option.type === 'text' || option.type === 'number') {
            input = document.createElement('input'); input.type = option.type; input.className = 'text-input image-option-input';
            input.value = saved[key] ?? option.default ?? '';
            input.placeholder = option.placeholder || '';
            for (const attr of ['min', 'max', 'step']) if (option[attr] !== undefined) input[attr] = option[attr];
            if (option.values?.length) {
                const list = document.createElement('datalist'); list.id = 'image-values-' + key;
                list.replaceChildren(...option.values.map(value => new Option(value, value)));
                input.setAttribute('list', list.id); group.appendChild(list);
            }
        } else {
            input = document.createElement('select'); input.className = 'select-input image-option-input';
            input.replaceChildren(...(option.values || []).map(value => new Option(value, value)));
            input.value = (option.values || []).includes(saved[key]) ? saved[key] : option.default;
        }
        input.id = label.htmlFor; input.dataset.optionKey = key;
        inputs[key] = input;
        group.prepend(label); group.appendChild(input);
        if (option.help) {
            const help = document.createElement('small'); help.className = 'muted-text'; help.textContent = option.help;
            group.appendChild(help);
        }
        target.appendChild(group);
        input.addEventListener('change', () => {updateHints(); void persistImageGenerationSettings(true);});
        input.addEventListener('input', updateHints);
    }
    const hint = document.createElement('p'); hint.id = 'imageParameterHint'; hint.setAttribute('role', 'status');
    hint.style.gridColumn = '1 / -1'; target.appendChild(hint);
    function updateHints() {
        hint.classList.remove('is-experimental', 'is-error');
        if (!caps.size_presets) {hint.textContent = ''; return;}
        const size = inputs.size?.value.trim() || caps.size_presets[inputs.image_size?.value]?.[inputs.aspect_ratio?.value];
        const error = imageOptionsError();
        if (error) {
            hint.classList.add('is-error');
            hint.textContent = error;
            return;
        }

        if (size && size !== 'auto') {
            const [w, h] = size.split('x').map(Number);
            if (w * h > 3686400) {
                const strong = document.createElement('strong');
                strong.textContent = '实验性尺寸';
                hint.classList.add('is-experimental');
                hint.replaceChildren(document.createTextNode(size + ' · '), strong);
                return;
            }
        }

        const soft = caps.parameter_control === 'prompt_hints';
        hint.textContent = `${soft ? '期望' : '请求'}像素：${size || 'auto'}${soft ? '（不能保证；不进行放大）' : ''}`;
    }
    updateHints();
    updateImageGenerationAvailability();
}

function imageOptionsError() {
    const caps = state.imageProviders[getActiveImageProvider()]?.capabilities?.[getActiveImageModel()] || {};
    const options = collectImageOptions();
    for (const el of document.querySelectorAll('.image-option-input')) {
        if (!el.disabled && el.type === 'number' && el.value !== '' && !el.checkValidity()) return `${el.dataset.optionKey} 超出范围或不是整数`;
    }
    if (options.background === 'transparent' && options.output_format === 'jpeg') return 'JPEG 不支持透明背景';
    const size = options.size?.trim().toLowerCase();
    if (!size || size === 'auto') return '';
    if (!/^\d+x\d+$/.test(size)) return 'size 格式须为 WIDTHxHEIGHT，例如 2048x1152';
    const [w, h] = size.split('x').map(Number), limits = caps.size_limits;
    if (limits && (w % limits.step || h % limits.step || Math.max(w,h) > limits.max_side || Math.min(w,h) <= 0
       || Math.max(w,h) > Math.min(w,h)*limits.max_ratio || w*h < limits.min_pixels || w*h > limits.max_pixels)) {
        return '不合法的尺寸：检查 16 倍数、边长、比例和总像素数';
    }
    return '';
}

function storeImageTaskResults(result) {
    state.generationMetadata ||= new Map();
    const images = result.images?.length ? result.images : [result.image];
    for (const image of images) {
        state.generationHistory.push(image);
        state.generationMetadata.set(image, result.metadata || {});
    }
    while (state.generationHistory.length > 32) {
        const old = state.generationHistory.shift();
        if (!state.generationHistory.includes(old)) state.generationMetadata.delete(old);
    }
}

function appendImageMetadata(container, src) {
    const metadata = state.generationMetadata?.get(src);
    if (!metadata) return;
    const detail = document.createElement('p'); detail.className = 'muted-text';
    detail.style.whiteSpace = 'pre-wrap'; detail.style.overflowWrap = 'anywhere';
    const billing = metadata.billing === 'codex_subscription' ? 'Codex 套餐额度' : '图片 API';
    detail.textContent = `${billing} · 实际像素：${(metadata.actual_sizes || []).join(', ')} · ${metadata.output_mime || ''}`;
    if (metadata.warnings?.length) detail.textContent += '\n' + metadata.warnings.join('\n');
    container.appendChild(detail);
}


const PROMPT_SEARCH_LABELS = {
    disabled: '禁止联网',
    auto: '自动联网',
    force: '强制联网'
};

function initAiPromptBackendControls() {
    const select = document.getElementById('aiPromptEngineSelect');
    const settings = document.getElementById('aiPromptBackendSettings');
    if (!select || !settings || select.dataset.bound === 'true') return;
    select.dataset.bound = 'true';

    select.addEventListener('change', async () => {
        const requested = select.value;
        const previous = state.config.chat_engine || 'api';
        select.disabled = true;
        try {
            if (requested === 'codex') {
                const statusResponse = await fetch('/api/codex/status', {cache: 'no-store'});
                const status = await statusResponse.json().catch(() => ({}));
                if (!statusResponse.ok || !status.logged_in) {
                    throw new Error(status.error || 'Codex 尚未登录，请先在服务器完成设备授权');
                }
            }
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({chat_engine: requested})
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.error || response.statusText);
            await loadConfig();
            await refreshAiPromptBackendBar({reloadConfig: false});
            showToast(requested === 'codex' ? '提示词后端已切换到 Codex 套餐' : '提示词后端已切换到原有 API', 'success');
        } catch (error) {
            select.value = previous;
            showToast('切换失败: ' + error.message, 'error');
            await refreshAiPromptBackendBar({reloadConfig: true});
        } finally {
            select.disabled = false;
        }
    });

    settings.addEventListener('click', () => {
        elements.aiModal.classList.remove('active');
        openConfigModal();
    });
}

async function refreshAiPromptBackendBar({reloadConfig = true} = {}) {
    initAiPromptBackendControls();
    const select = document.getElementById('aiPromptEngineSelect');
    const title = document.getElementById('aiPromptBackendTitle');
    const meta = document.getElementById('aiPromptBackendMeta');
    const strip = document.getElementById('aiBackendStrip');
    if (!select || !title || !meta || !strip) return;

    if (reloadConfig) await loadConfig();
    const engine = state.config.chat_engine || 'api';
    const searchMode = state.config.chat_web_search_mode || 'auto';
    const searchLabel = PROMPT_SEARCH_LABELS[searchMode] || searchMode;
    select.value = engine;

    strip.classList.remove('is-api', 'is-codex', 'is-error');
    strip.classList.add(engine === 'codex' ? 'is-codex' : 'is-api');

    if (engine !== 'codex') {
        title.textContent = '原有 API';
        meta.textContent = `${state.config.model || '模型未配置'} · ${searchLabel}`;
        return;
    }

    title.textContent = 'Codex 套餐';
    const model = state.config.codex_model || '账户默认模型';
    const effort = state.config.codex_effort || 'auto';
    meta.textContent = `${model} · ${effort} · ${searchLabel} · 正在检查登录…`;
    try {
        const response = await fetch('/api/codex/status', {cache: 'no-store'});
        const status = await response.json().catch(() => ({}));
        if (!response.ok || !status.logged_in) {
            strip.classList.add('is-error');
            meta.textContent = `${model} · ${effort} · ${searchLabel} · ${status.error || 'Codex 未登录'}`;
            return;
        }
        meta.textContent = `${model} · ${effort} · ${searchLabel} · ChatGPT 已登录 · Prompt ${status.prompt_workers || status.workers || '?'} 并发`;
    } catch (error) {
        strip.classList.add('is-error');
        meta.textContent = `${model} · ${effort} · ${searchLabel} · 状态检查失败：${error.message}`;
    }
}
