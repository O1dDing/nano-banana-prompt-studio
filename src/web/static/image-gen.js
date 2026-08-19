// ========================================
// Config Management
// ========================================
async function loadImageProviders() {
    try {
        const response = await fetch('/api/image-providers');
        if (!response.ok) throw new Error(response.statusText);
        state.imageProviders = await response.json();
        return true;
    } catch (error) {
        console.error('Load image providers error:', error);
        state.imageProviders = {};
        return false;
    }
}

async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        if (!response.ok) throw new Error(response.statusText);
        const config = await response.json();
        state.config = config;
        return true;
    } catch (error) {
        console.error('Load config error:', error);
        state.config = {};
        return false;
    }
}

function openConfigModal() {
    elements.configBaseUrl.value = state.config.base_url || '';
    elements.configApiKey.value = ''; // Don't show API key
    elements.configModel.value = state.config.model || '';

    const configuredProvider = state.config.image_provider || 'gemini';
    elements.configImageProvider.value = state.imageProviders[configuredProvider]
        ? configuredProvider
        : 'gemini';
    elements.configGeminiBaseUrl.value = state.config.gemini_base_url || '';
    elements.configGeminiApiKey.value = '';
    elements.configGeminiModel.value = state.config.gemini_model || '';
    elements.configOpenAIImageBaseUrl.value = state.config.openai_image_base_url || '';
    elements.configOpenAIImageApiKey.value = '';
    elements.configOpenAIImageModel.value = state.config.openai_image_model || 'gpt-image-2';
    elements.configQwenImageBaseUrl.value = state.config.qwen_image_base_url || '';
    elements.configQwenImageApiKey.value = '';
    elements.configQwenImageModel.value = state.config.qwen_image_model || 'qwen-image-3.0-pro';
    elements.configDoubaoImageBaseUrl.value = state.config.doubao_image_base_url
        || 'https://ark.cn-beijing.volces.com/api/v3';
    elements.configDoubaoImageApiKey.value = '';
    elements.configDoubaoImageModel.value = state.config.doubao_image_model
        || 'doubao-seedream-5-0-pro-260628';
    updateImageConfigVisibility();

    elements.configModal.classList.add('active');
}

async function saveConfigs() {
    const payload = {
        base_url: elements.configBaseUrl.value,
        model: elements.configModel.value,
        image_provider: elements.configImageProvider.value,
        gemini_base_url: elements.configGeminiBaseUrl.value,
        gemini_model: elements.configGeminiModel.value,
        openai_image_base_url: elements.configOpenAIImageBaseUrl.value,
        openai_image_model: elements.configOpenAIImageModel.value,
        qwen_image_base_url: elements.configQwenImageBaseUrl.value,
        qwen_image_model: elements.configQwenImageModel.value,
        doubao_image_base_url: elements.configDoubaoImageBaseUrl.value,
        doubao_image_model: elements.configDoubaoImageModel.value
    };
    if (elements.configApiKey.value) {
        payload.api_key = elements.configApiKey.value;
    }
    if (elements.configGeminiApiKey.value) {
        payload.gemini_api_key = elements.configGeminiApiKey.value;
    }
    if (elements.configOpenAIImageApiKey.value) {
        payload.openai_image_api_key = elements.configOpenAIImageApiKey.value;
    }
    if (elements.configQwenImageApiKey.value) {
        payload.qwen_image_api_key = elements.configQwenImageApiKey.value;
    }
    if (elements.configDoubaoImageApiKey.value) {
        payload.doubao_image_api_key = elements.configDoubaoImageApiKey.value;
    }

    try {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (response.ok) {
            await Promise.all([loadConfig(), loadImageProviders()]);
            await renderImageGenerationControls(elements.configImageProvider.value);
            showToast('配置保存成功', 'success');
            elements.configModal.classList.remove('active');
        } else {
            const error = await response.json().catch(() => ({}));
            showToast('保存失败: ' + (error.error || response.statusText), 'error');
        }
    } catch (e) {
        showToast('保存出错: ' + e, 'error');
    }
}

function getActiveImageProvider() {
    return state.activeImageProvider || elements.imageProviderSelect.value || '';
}

function getActiveImageModel() {
    return state.activeImageModel || elements.imageModelSelect.value || '';
}

function getAvailableImageProviders() {
    return Object.entries(state.imageProviders || {})
        .filter(([, config]) => config.is_configured);
}

async function renderImageGenerationControls(preferredProvider = '') {
    const availableProviders = getAvailableImageProviders();
    elements.imageProviderSelect.replaceChildren();

    if (availableProviders.length === 0) {
        const emptyOption = new Option('请先配置图片渠道', '');
        elements.imageProviderSelect.add(emptyOption);
        elements.imageProviderSelect.disabled = true;
        elements.imageModelSelect.replaceChildren();
        elements.imageModelSelect.add(new Option('暂无可用模型', ''));
        elements.imageModelSelect.disabled = true;
        state.activeImageProvider = '';
        state.activeImageModel = '';
        elements.imageProviderOptions.replaceChildren();
        updateImageGenerationAvailability();
        return;
    }

    availableProviders.forEach(([provider, config]) => {
        elements.imageProviderSelect.add(new Option(config.label || provider, provider));
    });
    elements.imageProviderSelect.disabled = false;

    const availableIds = availableProviders.map(([provider]) => provider);
    const selectedProvider = [preferredProvider, state.config.image_provider]
        .find(provider => availableIds.includes(provider)) || availableIds[0];
    elements.imageProviderSelect.value = selectedProvider;
    state.activeImageProvider = selectedProvider;
    renderImageModelChoices(selectedProvider);
    await persistImageGenerationSettings(false, true);
}

function renderImageModelChoices(provider, preferredModel = '') {
    const providerConfig = state.imageProviders[provider];
    elements.imageModelSelect.replaceChildren();
    if (!providerConfig) {
        state.activeImageModel = '';
        elements.imageModelSelect.disabled = true;
        renderImageProviderOptions();
        return;
    }

    const configuredModel = state.config[providerConfig.model_config_key]
        || providerConfig.configured_model
        || providerConfig.default_model
        || '';
    const models = [...(providerConfig.models || [])];
    if (configuredModel && !models.includes(configuredModel)) models.push(configuredModel);
    models.forEach(model => elements.imageModelSelect.add(new Option(model, model)));

    const selectedModel = [preferredModel, configuredModel, providerConfig.default_model]
        .find(model => model && models.includes(model)) || models[0] || '';
    elements.imageModelSelect.value = selectedModel;
    elements.imageModelSelect.disabled = models.length === 0;
    state.activeImageModel = selectedModel;
    renderImageProviderOptions();
}

function getSavedImageOptions(provider, model) {
    const allOptions = state.config.image_generation_options || {};
    const providerOptions = allOptions[provider] || {};
    return providerOptions[model || '__default__'] || {};
}

function renderImageProviderOptions() {
    if (!elements.imageProviderOptions) return;

    const provider = getActiveImageProvider();
    const model = getActiveImageModel();
    const providerConfig = state.imageProviders[provider];
    const capabilities = providerConfig?.capabilities?.[model];
    const providerOptions = capabilities?.options || {};
    const savedOptions = getSavedImageOptions(provider, model);

    if (!providerConfig || Object.keys(providerOptions).length === 0) {
        elements.imageProviderOptions.replaceChildren();
        updateImageGenerationAvailability();
        return;
    }

    elements.imageProviderOptions.innerHTML = Object.entries(providerOptions).map(([key, option]) => {
        const values = option.values || [];
        const options = values.map(value => {
            const savedValue = savedOptions[key];
            const selectedValue = values.includes(savedValue) ? savedValue : option.default;
            const selected = value === selectedValue ? 'selected' : '';
            return `<option value="${value}" ${selected}>${value}</option>`;
        }).join('');

        return `
            <div class="form-group">
                <label>${option.label}</label>
                <select class="select-input image-option-input" data-option-key="${key}">
                    ${options}
                </select>
            </div>
        `;
    }).join('');

    document.querySelectorAll('.image-option-input').forEach(input => {
        input.addEventListener('change', () => persistImageGenerationSettings(true));
    });
    updateImageGenerationAvailability();
}

function collectImageOptions() {
    const options = {};
    document.querySelectorAll('.image-option-input').forEach(input => {
        options[input.dataset.optionKey] = input.value;
    });
    return options;
}

function persistImageGenerationSettings(includeOptions = true, quiet = false) {
    const save = () => saveImageGenerationSettings(includeOptions, quiet);
    state.imageSettingsSaveQueue = state.imageSettingsSaveQueue.then(save, save);
    return state.imageSettingsSaveQueue;
}

async function saveImageGenerationSettings(includeOptions, quiet) {
    const provider = getActiveImageProvider();
    const model = getActiveImageModel();
    if (!provider || !model) return false;

    const payload = { provider, model };
    if (includeOptions) payload.options = collectImageOptions();

    try {
        const response = await fetch('/api/image-generation-settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.error || response.statusText);
        }

        state.config.image_provider = provider;
        const providerConfig = state.imageProviders[provider];
        state.config[providerConfig.model_config_key] = model;
        providerConfig.configured_model = model;
        if (includeOptions) {
            state.config.image_generation_options ||= {};
            state.config.image_generation_options[provider] ||= {};
            state.config.image_generation_options[provider][model] = payload.options;
        }
        return true;
    } catch (error) {
        console.error('Save image generation settings error:', error);
        if (!quiet) showToast('生图设置保存失败: ' + error.message, 'error');
        return false;
    }
}

function renderImageProviderStatus() {
    const providers = Object.values(state.imageProviders || {});
    const configuredProviders = providers.filter(config => config.is_configured);
    const unconfiguredCount = providers.length - configuredProviders.length;

    elements.activeImageProvider.hidden = configuredProviders.length > 0;
    elements.activeImageProvider.textContent = configuredProviders.length === 0
        ? '尚未配置图片渠道，请点击右上角“设置”添加渠道密钥'
        : '';
    elements.imageProviderStatusButton.hidden = configuredProviders.length === 0;
    elements.imageProviderStatusButton.setAttribute(
        'aria-label',
        `图片渠道状态：${configuredProviders.length} 个已配置，${unconfiguredCount} 个未配置`
    );

    const popover = elements.imageProviderStatusPopover;
    popover.replaceChildren();
    const title = document.createElement('strong');
    title.className = 'provider-status-title';
    title.textContent = '图片渠道状态';
    popover.appendChild(title);
    providers.forEach(config => {
        const row = document.createElement('div');
        row.className = `provider-status-row${config.is_configured ? ' is-configured' : ''}`;
        const dot = document.createElement('span');
        dot.className = 'provider-status-dot';
        dot.setAttribute('aria-hidden', 'true');
        const label = document.createElement('span');
        label.textContent = config.label;
        const value = document.createElement('span');
        value.textContent = config.is_configured ? '已配置' : '未配置';
        row.append(dot, label, value);
        popover.appendChild(row);
    });
}

function setImageProviderStatusOpen(open) {
    if (elements.imageProviderStatusButton.hidden) open = false;
    elements.imageProviderStatus.classList.toggle('is-open', open);
    elements.imageProviderStatusButton.setAttribute('aria-expanded', String(open));
}

function updateImageGenerationAvailability() {
    const provider = getActiveImageProvider();
    const providerConfig = state.imageProviders[provider];
    const ready = Boolean(providerConfig?.is_configured && getActiveImageModel());

    renderImageProviderStatus();
    elements.generateImageBtn.disabled = state.isGenerating || !ready;
}

function updateImageConfigVisibility() {
    const provider = elements.configImageProvider.value || 'gemini';
    document.querySelectorAll('.image-config-group').forEach(group => {
        group.style.display = group.dataset.providerConfig === provider ? '' : 'none';
    });
}

// ========================================
// Image Upload for Reference (Shared)
// ========================================
function handleImageUpload(e) {
    const files = Array.from(e.target.files);
    files.forEach(file => {
        if (!file.type.startsWith('image/')) {
            showToast('请选择图片', 'error');
            return;
        }
        const reader = new FileReader();
        reader.onload = (evt) => {
            const data = evt.target.result;
            if (state.uploadedImages.length >= 3) {
                showToast('最多上传3张', 'warning');
                return;
            }
            state.uploadedImages.push(data);
            renderUploadedImages();
        };
        reader.readAsDataURL(file);
    });
    e.target.value = ''; // reset
}

function renderUploadedImages() {
    elements.imagePreview.innerHTML = '';
    state.uploadedImages.forEach((data, idx) => {
        const div = document.createElement('div');
        div.className = 'image-preview-item';
        div.style.position = 'relative';

        const img = document.createElement('img');
        img.src = data;
        img.style.objectFit = 'cover';
        img.style.borderRadius = '4px';
        img.style.cursor = 'pointer';
        img.onclick = (e) => {
            e.stopPropagation();
            openImagePreview(data);
        };

        const btn = document.createElement('button');
        btn.innerHTML = '×';
        btn.style.position = 'absolute';
        btn.style.top = '-5px';
        btn.style.right = '-5px';
        btn.style.background = 'red';
        btn.style.color = 'white';
        btn.style.border = 'none';
        btn.style.borderRadius = '50%';
        btn.style.width = '18px';
        btn.style.height = '18px';
        btn.style.cursor = 'pointer';
        btn.onclick = () => {
            state.uploadedImages.splice(idx, 1);
            renderUploadedImages();
        };

        div.appendChild(img);
        div.appendChild(btn);
        elements.imagePreview.appendChild(div);
    });
}

// ========================================
// Image Generation
// ========================================
async function generateImage() {
    // 移动端点击生成后自动关闭侧边栏
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    if (sidebar) sidebar.classList.remove('open');
    if (sidebarOverlay) sidebarOverlay.classList.remove('active');

    const prompt = elements.jsonPreviewText.value;
    if (!prompt || prompt.length < 5) {
        showToast('请先配置提示词', 'warning');
        return;
    }

    const provider = getActiveImageProvider();
    const model = getActiveImageModel();
    const providerConfig = state.imageProviders[provider];
    if (!providerConfig?.is_configured || !model) {
        showToast('请先完成当前图片渠道配置', 'warning');
        updateImageGenerationAvailability();
        return;
    }

    state.isGenerating = true;
    updateImageGenerationAvailability();

    // 生成中状态：骨架屏 + 实时耗时反馈
    const genBtnDefaultHtml = elements.generateImageBtn.innerHTML;
    elements.resultPreview.classList.remove('has-error');
    elements.resultPreview.replaceChildren();
    const generatingState = document.createElement('div');
    generatingState.className = 'generating-state';
    const skeleton = document.createElement('div');
    skeleton.className = 'result-skeleton';
    const elapsedText = document.createElement('div');
    elapsedText.className = 'gen-elapsed';
    generatingState.appendChild(skeleton);
    generatingState.appendChild(elapsedText);
    elements.resultPreview.appendChild(generatingState);

    const stopTimer = startElapsedTimer(seconds => {
        elapsedText.innerHTML = `图片生成中 · 已耗时 <strong>${seconds}</strong> 秒`;
        elements.generateImageBtn.textContent = `⏳ 生成中 ${seconds}s`;
    });

    try {
        const response = await fetch('/api/generate-image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                prompt: prompt,
                images: state.uploadedImages,
                provider,
                model,
                options: collectImageOptions()
            })
        });

        const data = await response.json();

        if (response.ok && data.image) {
            state.currentGeneratedImage = data.image;

            // 用 DOM 构建结果，避免把几 MB 的 dataURL 写进 HTML 属性
            const container = document.createElement('div');
            container.className = 'generated-result-container';
            const wrap = document.createElement('div');
            wrap.className = 'generated-img-wrap';
            const img = document.createElement('img');
            img.src = data.image;
            img.alt = '生成结果';
            img.className = 'generated-img';
            img.addEventListener('click', () => openImagePreview(data.image));
            const hint = document.createElement('div');
            hint.className = 'img-zoom-hint';
            hint.textContent = '🔍 点击放大';
            wrap.appendChild(img);
            wrap.appendChild(hint);
            container.appendChild(wrap);
            elements.resultPreview.replaceChildren(container);
            showToast('图片生成成功!', 'success');
        } else {
            throw new Error(data.error || '生成失败');
        }

    } catch (e) {
        showToast('生成错误: ' + e.message, 'error');
        elements.resultPreview.classList.add('has-error');
        const errorState = document.createElement('div');
        errorState.className = 'generation-error';
        errorState.setAttribute('role', 'alert');
        const title = document.createElement('strong');
        title.className = 'generation-error-title';
        title.textContent = '生成失败';
        const message = document.createElement('p');
        message.className = 'generation-error-message';
        message.textContent = e.message;
        errorState.appendChild(title);
        errorState.appendChild(message);
        elements.resultPreview.replaceChildren(errorState);
    } finally {
        stopTimer();
        state.isGenerating = false;
        updateImageGenerationAvailability();
        elements.generateImageBtn.innerHTML = genBtnDefaultHtml;
    }
}

function openImagePreview(src) {
    const modal = document.getElementById('imagePreviewModal');
    const img = document.getElementById('fullImagePreview');
    const downloadBtn = document.getElementById('downloadFullImageBtn');
    
    if (modal && img) {
        img.src = src;
        modal.classList.add('active');
        
        // Close on background click
        modal.onclick = (e) => {
            if (e.target === modal) {
                modal.classList.remove('active');
            }
        };
        
        // Setup download button in modal
        if (downloadBtn) {
            downloadBtn.onclick = () => downloadImage(src);
        }
    }
}

function downloadImage(dataUrl) {
    if (!dataUrl) return;
    
    const link = document.createElement('a');
    link.href = dataUrl;
    
    // Determine extension
    let ext = 'png';
    if (dataUrl.startsWith('data:image/jpeg')) ext = 'jpg';
    if (dataUrl.startsWith('data:image/webp')) ext = 'webp';
    
    link.download = `generated-${new Date().getTime()}.${ext}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}
