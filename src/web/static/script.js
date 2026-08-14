// ========================================
// 全局状态管理
// ========================================
const state = {
    currentData: null,
    presets: [],
    config: {},

    imageProviders: {},
    activeImageProvider: '',
    activeImageModel: '',
    imageSettingsSaveQueue: Promise.resolve(),
    uploadedImages: [], // Base64 strings
    isGenerating: false
};

const DEFAULT_NEGATIVE_PROMPT = '水印、签名、文字';

const categoryPresetConfig = {
    basic: [
        ['styleMode', ['风格模式']],
        ['atmosphere', ['画面气质']]
    ],
    scene: [
        ['location', ['场景', '环境', '地点设定']],
        ['lighting', ['场景', '环境', '光线']],
        ['weather', ['场景', '环境', '天气氛围']],
        ['background', ['场景', '背景', '描述']],
        ['depth', ['场景', '背景', '景深']]
    ],
    subject: [
        ['description', ['场景', '主体', '整体描述']],
        ['bodyShape', ['场景', '主体', '外形特征', '身材']],
        ['face', ['场景', '主体', '外形特征', '面部']],
        ['hair', ['场景', '主体', '外形特征', '头发']],
        ['eyes', ['场景', '主体', '外形特征', '眼睛']],
        ['emotion', ['场景', '主体', '表情与动作', '情绪']],
        ['action', ['场景', '主体', '表情与动作', '动作']],
        ['clothing', ['场景', '主体', '服装', '穿着']],
        ['clothingDetails', ['场景', '主体', '服装', '细节']],
        ['accessories', ['场景', '主体', '配饰']]
    ],
    camera: [
        ['angle', ['相机', '机位角度']],
        ['composition', ['相机', '构图']],
        ['lensCharacteristics', ['相机', '镜头特性']],
        ['sensorQuality', ['相机', '传感器画质']]
    ],
    aesthetic: [
        ['intent', ['审美控制', '呈现意图']],
        ['materialRealism', ['审美控制', '材质真实度']],
        ['overallTone', ['审美控制', '色彩风格', '整体色调']],
        ['contrast', ['审美控制', '色彩风格', '对比度']],
        ['specialEffects', ['审美控制', '色彩风格', '特殊效果']]
    ]
};

// ========================================
// DOM 元素
// ========================================
const elements = {
    // 侧边栏表单 - 基础设置
    styleMode: document.getElementById('styleMode'),
    atmosphere: document.getElementById('atmosphere'),

    // 场景设置
    location: document.getElementById('location'),
    lighting: document.getElementById('lighting'),
    weather: document.getElementById('weather'),

    // 主体设置
    description: document.getElementById('description'),
    bodyShape: document.getElementById('bodyShape'),
    face: document.getElementById('face'),
    hair: document.getElementById('hair'),
    eyes: document.getElementById('eyes'),
    emotion: document.getElementById('emotion'),
    action: document.getElementById('action'),
    clothing: document.getElementById('clothing'),
    clothingDetails: document.getElementById('clothingDetails'),
    accessories: document.getElementById('accessories'),
    background: document.getElementById('background'),
    depth: document.getElementById('depth'),

    // 相机设置
    angle: document.getElementById('angle'),
    composition: document.getElementById('composition'),
    lensCharacteristics: document.getElementById('lensCharacteristics'),
    sensorQuality: document.getElementById('sensorQuality'),

    // 审美控制
    intent: document.getElementById('intent'),
    materialRealism: document.getElementById('materialRealism'),
    overallTone: document.getElementById('overallTone'),
    contrast: document.getElementById('contrast'),
    specialEffects: document.getElementById('specialEffects'),

    // 高级设置
    specialRequirementEnabled: document.getElementById('specialRequirementEnabled'),
    specialRequirementGroup: document.getElementById('specialRequirementGroup'),
    specialRequirementInput: document.getElementById('specialRequirementInput'),

    lineArtModeEnabled: document.getElementById('lineArtModeEnabled'),
    lineArtGroup: document.getElementById('lineArtGroup'),
    lineArtPromptInput: document.getElementById('lineArtPromptInput'),
    saveLineArtPromptBtn: document.getElementById('saveLineArtPromptBtn'),

    negativePromptEnabled: document.getElementById('negativePromptEnabled'),
    negativePromptGroup: document.getElementById('negativePromptGroup'),
    negativeTagsContainer: document.getElementById('negativeTagsContainer'),
    negativeTagInput: document.getElementById('negativeTagInput'),
    addNegativeTagBtn: document.getElementById('addNegativeTagBtn'),
    negativePromptInput: document.getElementById('negativePromptInput'),

    // 预设
    presetSelect: document.getElementById('presetSelect'),
    savePresetBtn: document.getElementById('savePresetBtn'),
    deletePresetBtn: document.getElementById('deletePresetBtn'),

    // 顶部工具栏
    aiGenerateOpenBtn: document.getElementById('aiGenerateOpenBtn'),
    aiModifyOpenBtn: document.getElementById('aiModifyOpenBtn'),
    configBtn: document.getElementById('configBtn'),
    resetFormBtn: document.getElementById('resetFormBtn'),

    // JSON 预览（可折叠）
    jsonPreviewPane: document.getElementById('jsonPreviewPane'),
    jsonPreviewToggleBtn: document.getElementById('jsonPreviewToggleBtn'),
    jsonPreviewHideBtn: document.getElementById('jsonPreviewHideBtn'),
    jsonPreviewText: document.getElementById('jsonPreviewText'),
    copyJsonBtn: document.getElementById('copyJsonBtn'),

    // 生图区域
    activeImageProvider: document.getElementById('activeImageProvider'),
    imageProviderStatus: document.getElementById('imageProviderStatus'),
    imageProviderStatusButton: document.getElementById('imageProviderStatusButton'),
    imageProviderStatusPopover: document.getElementById('imageProviderStatusPopover'),
    imageProviderSelect: document.getElementById('imageProviderSelect'),
    imageModelSelect: document.getElementById('imageModelSelect'),
    imageProviderOptions: document.getElementById('imageProviderOptions'),
    // genThinkingLevel: document.getElementById('genThinkingLevel'), // Removed from HTML
    imageInput: document.getElementById('imageInput'),
    uploadImageBtn: document.getElementById('uploadImageBtn'),
    imagePreview: document.getElementById('imagePreview'),
    generateImageBtn: document.getElementById('generateImageBtn'),
    resultPreview: document.getElementById('resultPreview'),

    // AI 对话框
    aiModal: document.getElementById('aiModal'),
    aiModalTitle: document.getElementById('aiModalTitle'),
    aiModalLabel: document.getElementById('aiModalLabel'),
    aiPromptInput: document.getElementById('aiPromptInput'),
    // aiProgress: document.getElementById('aiProgress'), // Removed
    
    // AI Modal New Elements
    aiImageInput: document.getElementById('aiImageInput'),
    aiUploadImageBtn: document.getElementById('aiUploadImageBtn'),
    aiImagePreview: document.getElementById('aiImagePreview'),
    aiResponsePreview: document.getElementById('aiResponsePreview'),
    aiStatusText: document.getElementById('aiStatusText'),
    
    aiModalCancelBtn: document.getElementById('aiModalCancelBtn'),
    aiModalExecuteBtn: document.getElementById('aiModalExecuteBtn'),
    aiModalStopBtn: document.getElementById('aiModalStopBtn'),
    aiModalApplyBtn: document.getElementById('aiModalApplyBtn'),
    aiDiffContainer: document.getElementById('aiDiffContainer'),

    // 配置对话框
    configModal: document.getElementById('configModal'),
    // OpenAI Config
    configBaseUrl: document.getElementById('configBaseUrl'),
    configApiKey: document.getElementById('configApiKey'),
    configModel: document.getElementById('configModel'),
    // Image generation Config
    configImageProvider: document.getElementById('configImageProvider'),
    configGeminiBaseUrl: document.getElementById('configGeminiBaseUrl'),
    configGeminiApiKey: document.getElementById('configGeminiApiKey'),
    configGeminiModel: document.getElementById('configGeminiModel'),
    configOpenAIImageBaseUrl: document.getElementById('configOpenAIImageBaseUrl'),
    configOpenAIImageApiKey: document.getElementById('configOpenAIImageApiKey'),
    configOpenAIImageModel: document.getElementById('configOpenAIImageModel'),
    configQwenImageBaseUrl: document.getElementById('configQwenImageBaseUrl'),
    configQwenImageApiKey: document.getElementById('configQwenImageApiKey'),
    configQwenImageModel: document.getElementById('configQwenImageModel'),

    saveConfigBtn: document.getElementById('saveConfigBtn')
};

// ========================================
// 工具函数
// ========================================
let toastContainer = null;

function showToast(message, type = 'info') {
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container';
        document.body.appendChild(toastContainer);
    }
    const item = document.createElement('div');
    item.className = `toast-item ${type}`;
    item.setAttribute('role', 'status');
    item.textContent = message;
    toastContainer.appendChild(item);
    requestAnimationFrame(() => item.classList.add('show'));
    setTimeout(() => {
        item.classList.remove('show');
        setTimeout(() => item.remove(), 300);
    }, 3000);
}

/**
 * 启动一个秒级计时器，每秒回调 setText(已耗时秒数)，返回停止函数。
 * 用于生图等长任务的耗时反馈。
 */
function startElapsedTimer(setText) {
    const startTime = Date.now();
    setText(0);
    const timerId = setInterval(() => {
        setText(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);
    return () => clearInterval(timerId);
}

// ========================================
// 表单数据处理 (保持原有的逻辑)
// ========================================
function normalizeNegativePrompt(value) {
    if (typeof value === 'string') return value;
    if (!value || typeof value !== 'object') return '';

    const values = [];
    ['禁止元素', '禁止风格'].forEach(key => {
        const item = value[key];
        if (Array.isArray(item)) {
            values.push(...item);
        } else if (item) {
            values.push(item);
        }
    });
    return values.filter(Boolean).join(', ');
}

function getFormData() {
    function stringToArray(str) {
        if (!str || !str.trim()) return [];
        return str.split(',').map(item => item.trim()).filter(item => item);
    }

    const materialRealismValue = elements.materialRealism.value.trim();
    const materialRealismArray = materialRealismValue ? stringToArray(materialRealismValue) : [];


    const data = {
        "风格模式": elements.styleMode.value,
        "画面气质": elements.atmosphere.value,
        "场景": {
            "环境": {
                "地点设定": elements.location.value,
                "光线": elements.lighting.value,
                "天气氛围": elements.weather.value
            },
            "主体": {
                "整体描述": elements.description.value,
                "外形特征": {
                    "身材": elements.bodyShape.value,
                    "面部": elements.face.value,
                    "头发": elements.hair.value,
                    "眼睛": elements.eyes.value
                },
                "表情与动作": {
                    "情绪": elements.emotion.value,
                    "动作": elements.action.value
                },
                "服装": {
                    "穿着": elements.clothing.value,
                    "细节": elements.clothingDetails.value
                },
                "配饰": elements.accessories.value
            },
            "背景": {
                "描述": elements.background.value,
                "景深": elements.depth.value
            }
        },
        "相机": {
            "机位角度": elements.angle.value,
            "构图": elements.composition.value,
            "镜头特性": elements.lensCharacteristics.value,
            "传感器画质": elements.sensorQuality.value
        },
        "审美控制": {
            "呈现意图": elements.intent.value,
            "材质真实度": materialRealismArray.length > 0 ? materialRealismArray : [elements.materialRealism.value],
            "色彩风格": {
                "整体色调": elements.overallTone.value,
                "对比度": elements.contrast.value,
                "特殊效果": elements.specialEffects.value
            }
        }
    };

    // Add Special Requirements if enabled
    if (elements.specialRequirementEnabled.checked) {
        data["特别要求"] = elements.specialRequirementInput.value;
    }

    // Add Line Art if enabled
    if (elements.lineArtModeEnabled.checked) {
        data["角色线稿生成"] = {
            "启用": true,
            "提示词": elements.lineArtPromptInput.value
        };
    }

    // Add Negative Prompt if enabled
    if (elements.negativePromptEnabled.checked) {
        data["反向提示词"] = elements.negativePromptInput.value.trim();
    }

    return data;
}

function setFormData(data) {
    if (!data) return;

    function getValue(obj, ...path) {
        let current = obj;
        for (const key of path) {
            if (current === null || current === undefined) return '';
            current = current[key];
        }
        return current === null || current === undefined ? '' : current;
    }

    function arrayToString(val) {
        if (Array.isArray(val)) return val.join(', ');
        return val || '';
    }

    elements.styleMode.value = getValue(data, "风格模式");
    elements.atmosphere.value = getValue(data, "画面气质");

    elements.location.value = getValue(data, "场景", "环境", "地点设定");
    elements.lighting.value = getValue(data, "场景", "环境", "光线");
    elements.weather.value = getValue(data, "场景", "环境", "天气氛围");

    elements.description.value = getValue(data, "场景", "主体", "整体描述");
    elements.bodyShape.value = getValue(data, "场景", "主体", "外形特征", "身材");
    elements.face.value = getValue(data, "场景", "主体", "外形特征", "面部");
    elements.hair.value = getValue(data, "场景", "主体", "外形特征", "头发");
    elements.eyes.value = getValue(data, "场景", "主体", "外形特征", "眼睛");

    const emotionVal = getValue(data, "场景", "主体", "表情与动作", "情绪");
    const actionVal = getValue(data, "场景", "主体", "表情与动作", "动作");

    // Legacy support for merged string
    const expressionActionParams = getValue(data, "场景", "主体", "表情与动作");
    if (typeof expressionActionParams === 'string') {
        elements.action.value = expressionActionParams;
        elements.emotion.value = '';
    } else {
        elements.emotion.value = emotionVal;
        elements.action.value = actionVal;
    }

    elements.clothing.value = getValue(data, "场景", "主体", "服装", "穿着");
    elements.clothingDetails.value = getValue(data, "场景", "主体", "服装", "细节");
    elements.accessories.value = getValue(data, "场景", "主体", "配饰");
    elements.background.value = getValue(data, "场景", "背景", "描述");
    elements.depth.value = getValue(data, "场景", "背景", "景深");

    elements.angle.value = getValue(data, "相机", "机位角度");
    elements.composition.value = getValue(data, "相机", "构图");
    elements.lensCharacteristics.value = getValue(data, "相机", "镜头特性");
    elements.sensorQuality.value = getValue(data, "相机", "传感器画质");

    elements.intent.value = getValue(data, "审美控制", "呈现意图");
    elements.materialRealism.value = arrayToString(getValue(data, "审美控制", "材质真实度"));
    elements.overallTone.value = getValue(data, "审美控制", "色彩风格", "整体色调");
    elements.contrast.value = getValue(data, "审美控制", "色彩风格", "对比度");
    elements.specialEffects.value = getValue(data, "审美控制", "色彩风格", "特殊效果");

    // Special Requirements
    const specialReq = getValue(data, "特别要求");
    if (specialReq) {
        elements.specialRequirementEnabled.checked = true;
        elements.specialRequirementInput.value = specialReq;
        elements.specialRequirementGroup.style.display = 'block';
    } else {
        elements.specialRequirementEnabled.checked = false;
        elements.specialRequirementInput.value = '';
        elements.specialRequirementGroup.style.display = 'none';
    }

    // Line Art
    const lineArt = getValue(data, "角色线稿生成");
    if (lineArt && lineArt["启用"]) {
        elements.lineArtModeEnabled.checked = true;
        elements.lineArtPromptInput.value = lineArt["提示词"] || '';
        elements.lineArtGroup.style.display = 'block';
        // Trigger event to disable other fields (will add listener later)
        elements.lineArtModeEnabled.dispatchEvent(new Event('change'));
    } else {
        elements.lineArtModeEnabled.checked = false;
        elements.lineArtPromptInput.value = '';
        elements.lineArtGroup.style.display = 'none';
        elements.lineArtModeEnabled.dispatchEvent(new Event('change'));
    }

    // Negative Prompt
    const negativePrompt = normalizeNegativePrompt(getValue(data, "反向提示词"));

    elements.negativePromptInput.value = negativePrompt;
    elements.negativePromptEnabled.checked = Boolean(negativePrompt);
    elements.negativePromptGroup.style.display = negativePrompt ? 'flex' : 'none';

    // Trigger update for preview
    updateJsonPreview();
}

function setNestedValue(target, path, value) {
    let current = target;
    path.slice(0, -1).forEach(key => {
        if (!current[key]) current[key] = {};
        current = current[key];
    });
    current[path[path.length - 1]] = value;
}

function collectCategoryPresetData(scope) {
    const fullData = getFormData();
    const result = {};
    (categoryPresetConfig[scope] || []).forEach(([, path]) => {
        const value = getNestedValue(fullData, path);
        if (value !== undefined) setNestedValue(result, path, value);
    });
    return result;
}

function applyCategoryPresetData(scope, data) {
    (categoryPresetConfig[scope] || []).forEach(([elementId, path]) => {
        const value = getNestedValue(data, path);
        if (value === undefined) return;
        const element = document.getElementById(elementId);
        if (!element) return;
        element.value = Array.isArray(value) ? value.join(', ') : (value ?? '');
        element.dispatchEvent(new Event('input', { bubbles: true }));
    });
    updateJsonPreview();
}

async function loadCategoryPresetOptions(scope, selectedName = '') {
    const bar = document.querySelector(`.category-preset-bar[data-preset-scope="${scope}"]`);
    if (!bar) return;
    const selector = bar.querySelector('select');
    try {
        const response = await fetch(`/api/category-presets/${scope}`);
        if (!response.ok) throw new Error('加载分类预设失败');
        const presets = await response.json();
        selector.innerHTML = '<option value="">分类预设...</option>';
        presets.forEach(preset => {
            const option = document.createElement('option');
            option.value = preset.name;
            option.textContent = preset.name;
            selector.appendChild(option);
        });
        if (selectedName) selector.value = selectedName;
    } catch (error) {
        console.error(error);
    }
}

function initCategoryPresets() {
    document.querySelectorAll('.category-preset-bar').forEach(bar => {
        const scope = bar.dataset.presetScope;
        const label = bar.dataset.presetLabel;
        bar.innerHTML = `
            <span class="category-preset-label">分类预设</span>
            <select class="select-input" aria-label="${label}预设">
                <option value="">分类预设...</option>
            </select>
            <button type="button" class="btn btn-secondary btn-compact" data-action="save">保存当前分类</button>
            <button type="button" class="btn btn-danger btn-compact" data-action="delete">删除</button>
        `;
        const selector = bar.querySelector('select');

        selector.addEventListener('change', async () => {
            if (!selector.value) return;
            try {
                const name = encodeURIComponent(selector.value);
                const response = await fetch(`/api/category-presets/${scope}/${name}`);
                if (!response.ok) throw new Error('加载分类预设失败');
                applyCategoryPresetData(scope, await response.json());
                showToast(`已应用${label}预设: ${selector.value}`);
            } catch (error) {
                console.error(error);
                showToast('分类预设加载失败');
            }
        });

        bar.querySelector('[data-action="save"]').addEventListener('click', async () => {
            const name = prompt(`请输入${label}预设名称:`, selector.value);
            if (!name || !name.trim()) return;
            const response = await fetch(`/api/category-presets/${scope}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name.trim(), data: collectCategoryPresetData(scope) })
            });
            if (!response.ok) {
                showToast('分类预设保存失败');
                return;
            }
            await loadCategoryPresetOptions(scope, name.trim());
            showToast(`${label}预设已保存: ${name.trim()}`);
        });

        bar.querySelector('[data-action="delete"]').addEventListener('click', async () => {
            const name = selector.value;
            if (!name || !confirm(`确定删除${label}预设「${name}」吗?`)) return;
            const response = await fetch(
                `/api/category-presets/${scope}/${encodeURIComponent(name)}`,
                { method: 'DELETE' }
            );
            if (!response.ok) {
                showToast('分类预设删除失败');
                return;
            }
            await loadCategoryPresetOptions(scope);
            showToast(`已删除分类预设: ${name}`);
        });

        loadCategoryPresetOptions(scope);
    });
}

function clearForm() {
    Object.values(elements).forEach(el => {
        if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT')) {
            if (!el.id.startsWith('gen') && !el.id.startsWith('config') && el.id !== 'presetSelect') {
                if (el.type === 'checkbox') {
                    el.checked = false;
                    el.dispatchEvent(new Event('change'));
                } else {
                    el.value = '';
                }
            }
        }
    });
    elements.negativePromptEnabled.checked = true;
    elements.negativePromptInput.value = DEFAULT_NEGATIVE_PROMPT;
    elements.negativePromptGroup.style.display = 'flex';


    updateJsonPreview();
}

function updateJsonPreview() {
    let finalOutput = "";

    if (elements.lineArtModeEnabled.checked) {
        // Line Art Mode: Use raw prompt + special requirements
        let prompt = elements.lineArtPromptInput.value.trim();
        if (elements.specialRequirementEnabled.checked) {
            const special = elements.specialRequirementInput.value.trim();
            if (special) {
                prompt += "\n\n额外要求：" + special;
            }
        }
        finalOutput = prompt;
    } else {
        // Normal Mode: Use JSON + special requirements
        const data = getFormData();
        let jsonStr = JSON.stringify(data, null, 2);
        
        if (elements.specialRequirementEnabled.checked) {
            const special = elements.specialRequirementInput.value.trim();
            if (special) {
                // Append special requirements outside of JSON
                jsonStr += "\n\n特别要求：" + special;
            }
        }
        finalOutput = jsonStr;
    }
    
    elements.jsonPreviewText.value = finalOutput;
}

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
        qwen_image_model: elements.configQwenImageModel.value
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
// AI Generate Prompt / Modify Prompt
// ========================================
let currentAiMode = null; // 'generate' or 'modify'
let aiUploadedImages = []; // Local images for AI modal
let aiAbortController = null;
let latestDiffChanges = []; // Store diff changes

// ========================================
// Diff Utils
// ========================================
function isObject(item) {
    return (item && typeof item === 'object' && !Array.isArray(item));
}

function diffJson(obj1, obj2, path = []) {
    let changes = [];
    
    // Union of keys
    const keys1 = isObject(obj1) ? Object.keys(obj1) : [];
    const keys2 = isObject(obj2) ? Object.keys(obj2) : [];
    const allKeys = new Set([...keys1, ...keys2]);

    for (const key of allKeys) {
        const val1 = isObject(obj1) ? obj1[key] : undefined;
        const val2 = isObject(obj2) ? obj2[key] : undefined;
        const currentPath = [...path, key];

        if (isObject(val1) && isObject(val2)) {
            changes = changes.concat(diffJson(val1, val2, currentPath));
        } else if (Array.isArray(val1) && Array.isArray(val2)) {
            // Simple array comparison
            if (JSON.stringify(val1) !== JSON.stringify(val2)) {
                changes.push({
                    path: currentPath,
                    pathStr: currentPath.join(' > '),
                    oldValue: val1,
                    newValue: val2
                });
            }
        } else if (val1 !== val2) {
             // Ignore if both are empty/null/undefined equivalent
             const v1Empty = val1 === null || val1 === undefined || val1 === '';
             const v2Empty = val2 === null || val2 === undefined || val2 === '';
             if (v1Empty && v2Empty) continue;

             changes.push({
                path: currentPath,
                pathStr: currentPath.join(' > '),
                oldValue: val1 === undefined ? '(空)' : val1,
                newValue: val2 === undefined ? '(删除)' : val2
             });
        }
    }
    return changes;
}

function renderDiff(changes) {
    elements.aiDiffContainer.innerHTML = '';
    latestDiffChanges = changes;
    
    if (changes.length === 0) {
        elements.aiDiffContainer.innerHTML = '<div class="empty-state">未检测到更改</div>';
        return;
    }

    changes.forEach((change, idx) => {
        const item = document.createElement('div');
        item.className = 'diff-item';
        
        const header = document.createElement('div');
        header.style.display = 'flex';
        header.style.alignItems = 'center';
        header.style.marginBottom = '5px';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = true;
        checkbox.id = `diff-check-${idx}`;
        checkbox.dataset.idx = idx;
        
        const label = document.createElement('label');
        label.htmlFor = `diff-check-${idx}`;
        label.textContent = change.pathStr;
        label.style.marginLeft = '8px';
        label.style.fontWeight = 'bold';
        label.style.cursor = 'pointer';

        header.appendChild(checkbox);
        header.appendChild(label);

        const content = document.createElement('div');
        content.style.marginLeft = '24px';
        content.style.fontSize = '13px';

        // Format values for display
        const formatVal = (v) => {
            if (Array.isArray(v)) return JSON.stringify(v);
            return v;
        };

        const oldDiv = document.createElement('div');
        oldDiv.className = 'diff-old';
        oldDiv.textContent = `旧: ${formatVal(change.oldValue)}`;
        
        const newDiv = document.createElement('div');
        newDiv.className = 'diff-new';
        newDiv.textContent = `新: ${formatVal(change.newValue)}`;

        content.appendChild(oldDiv);
        content.appendChild(newDiv);

        item.appendChild(header);
        item.appendChild(content);
        
        elements.aiDiffContainer.appendChild(item);
    });
}

function handleAiImageUpload(e) {
    const files = Array.from(e.target.files);
    files.forEach(file => {
        if (!file.type.startsWith('image/')) {
            showToast('请选择图片', 'error');
            return;
        }
        const reader = new FileReader();
        reader.onload = (evt) => {
            const data = evt.target.result;
            if (aiUploadedImages.length >= 3) {
                showToast('最多上传3张', 'warning');
                return;
            }
            aiUploadedImages.push(data);
            renderAiUploadedImages();
        };
        reader.readAsDataURL(file);
    });
    e.target.value = ''; // reset
}

function renderAiUploadedImages() {
    elements.aiImagePreview.innerHTML = '';
    aiUploadedImages.forEach((data, idx) => {
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
            aiUploadedImages.splice(idx, 1);
            renderAiUploadedImages();
        };

        div.appendChild(img);
        div.appendChild(btn);
        elements.aiImagePreview.appendChild(div);
    });
}

function openAiModal(mode) {
    currentAiMode = mode;
    elements.aiModal.classList.add('active');
    
    // Reset State
    elements.aiPromptInput.value = '';
    elements.aiResponsePreview.value = '';
    elements.aiStatusText.textContent = '';
    aiUploadedImages = [];
    renderAiUploadedImages();
    latestDiffChanges = [];

    // Reset View
    elements.aiDiffContainer.style.display = 'none';
    elements.aiResponsePreview.style.display = 'block';
    elements.aiDiffContainer.innerHTML = '';
    
    // Reset Buttons
    elements.aiModalExecuteBtn.style.display = 'inline-block';
    elements.aiModalExecuteBtn.disabled = false;
    elements.aiModalStopBtn.style.display = 'none';
    elements.aiModalApplyBtn.style.display = 'none';

    if (mode === 'generate') {
        elements.aiModalTitle.textContent = 'AI 生成提示词';
        elements.aiModalLabel.textContent = '描述你想要的画面';
    } else {
        elements.aiModalTitle.textContent = 'AI 修改提示词';
        elements.aiModalLabel.textContent = '描述修改要求';
    }
}

async function handleAiExecute() {
    const prompt = elements.aiPromptInput.value.trim();
    if (!prompt) {
        showToast('请输入内容', 'warning');
        return;
    }

    // UI Update
    elements.aiResponsePreview.value = '';
    elements.aiStatusText.textContent = '正在思考...';
    elements.aiModalExecuteBtn.style.display = 'none';
    elements.aiModalStopBtn.style.display = 'inline-block';
    elements.aiModalApplyBtn.style.display = 'none';

    // 耗时反馈：生成期间实时显示已耗时
    const stopStatusTimer = startElapsedTimer(seconds => {
        elements.aiStatusText.textContent = `正在生成 · 已耗时 ${seconds}s`;
    });
    let aiFinalStatus = '';

    // Create AbortController
    aiAbortController = new AbortController();
    const signal = aiAbortController.signal;

    try {
        let url = currentAiMode === 'generate' ? '/api/generate' : '/api/modify';
        let body = {
            images: aiUploadedImages // Use local images
        };

        if (currentAiMode === 'generate') {
            body.prompt = prompt;
        } else {
            body.current_data = elements.jsonPreviewText.value;
            body.modify_request = prompt;
        }

        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            signal: signal
        });

        if (!response.ok) throw new Error('API request failed');

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullContent = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const dataStr = line.slice(6);
                    if (dataStr === '[DONE]') {
                        aiFinalStatus = '生成完成';
                        elements.aiModalStopBtn.style.display = 'none';
                        elements.aiModalApplyBtn.style.display = 'inline-block';
                        elements.aiModalExecuteBtn.style.display = 'inline-block';

                        // Logic for Modify Mode: Show Diff
                        if (currentAiMode === 'modify') {
                            try {
                                let jsonText = fullContent;
                                // Try to extract JSON from Markdown
                                const jsonMatch = jsonText.match(/```json\s*([\s\S]*?)\s*```/);
                                if (jsonMatch) {
                                    jsonText = jsonMatch[1];
                                } else {
                                     const firstBrace = jsonText.indexOf('{');
                                     const lastBrace = jsonText.lastIndexOf('}');
                                     if (firstBrace !== -1 && lastBrace !== -1) {
                                         jsonText = jsonText.substring(firstBrace, lastBrace + 1);
                                     }
                                }
                                
                                const newData = JSON.parse(jsonText);
                                const currentData = getFormData();
                                const changes = diffJson(currentData, newData);
                                
                                renderDiff(changes);
                                
                                // Switch View
                                elements.aiResponsePreview.style.display = 'none';
                                elements.aiDiffContainer.style.display = 'block';
                                
                            } catch (e) {
                                console.error('Diff calculation failed:', e);
                                showToast('对比生成失败，显示原始结果', 'warning');
                                // Fallback to raw view
                                elements.aiResponsePreview.style.display = 'block';
                                elements.aiDiffContainer.style.display = 'none';
                            }
                        }
                    } else {
                        try {
                            const parsed = JSON.parse(dataStr);
                            if (parsed.content) {
                                fullContent += parsed.content;
                                elements.aiResponsePreview.value = fullContent;
                                elements.aiResponsePreview.scrollTop = elements.aiResponsePreview.scrollHeight;
                            }
                            if (parsed.error) throw new Error(parsed.error);
                        } catch (e) {
                            // ignore partial chunks
                        }
                    }
                }
            }
        }

    } catch (e) {
        if (e.name === 'AbortError') {
            aiFinalStatus = '已停止';
            showToast('已停止生成', 'info');
        } else {
            aiFinalStatus = '错误: ' + e.message;
            showToast('错误: ' + e.message, 'error');
        }
        elements.aiModalStopBtn.style.display = 'none';
        elements.aiModalExecuteBtn.style.display = 'inline-block';
    } finally {
        stopStatusTimer();
        if (aiFinalStatus) {
            elements.aiStatusText.textContent = aiFinalStatus;
        }
        aiAbortController = null;
    }
}

function handleAiStop() {
    if (aiAbortController) {
        aiAbortController.abort();
    }
}

function applyAiResult() {
    try {
        // If in Modify Mode and Diff View is active
        if (currentAiMode === 'modify' && elements.aiDiffContainer.style.display !== 'none') {
            const checkboxes = elements.aiDiffContainer.querySelectorAll('input[type="checkbox"]');
            const data = getFormData(); // Start with current data
            
            let appliedCount = 0;
            checkboxes.forEach(cb => {
                if (cb.checked) {
                    const idx = parseInt(cb.dataset.idx);
                    const change = latestDiffChanges[idx];
                    if (change) {
                        // Apply change to data object
                        // Helper to set deep value
                        let current = data;
                        for (let i = 0; i < change.path.length - 1; i++) {
                            const key = change.path[i];
                            if (!current[key]) current[key] = {};
                            current = current[key];
                        }
                        const lastKey = change.path[change.path.length - 1];
                        
                        if (change.newValue === undefined) {
                            delete current[lastKey];
                        } else {
                            current[lastKey] = change.newValue;
                        }
                        appliedCount++;
                    }
                }
            });
            
            setFormData(data);
            showToast(`已应用 ${appliedCount} 项更改`, 'success');
            elements.aiModal.classList.remove('active');
            return;
        }

        // Fallback / Generate Mode Logic
        const jsonText = elements.aiResponsePreview.value;
        // Attempt to find JSON if wrapped in markdown
        let cleanJson = jsonText;
        const jsonMatch = jsonText.match(/```json\s*([\s\S]*?)\s*```/);
        if (jsonMatch) {
            cleanJson = jsonMatch[1];
        } else {
             // Try to find the first '{' and last '}'
             const firstBrace = jsonText.indexOf('{');
             const lastBrace = jsonText.lastIndexOf('}');
             if (firstBrace !== -1 && lastBrace !== -1) {
                 cleanJson = jsonText.substring(firstBrace, lastBrace + 1);
             }
        }

        const jsonData = JSON.parse(cleanJson);
        setFormData(jsonData);
        showToast('已应用到表单', 'success');
        elements.aiModal.classList.remove('active');
    } catch (e) {
        showToast('JSON 解析失败，请检查生成内容', 'error');
    }
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
        const errorState = document.createElement('div');
        errorState.className = 'empty-state';
        const title = document.createElement('p');
        title.style.color = 'var(--error-color)';
        title.textContent = '生成失败';
        const hint = document.createElement('p');
        hint.className = 'hint';
        hint.textContent = e.message;
        errorState.appendChild(title);
        errorState.appendChild(hint);
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

// ========================================
// Init
// ========================================
function init() {
    Promise.all([loadImageProviders(), loadConfig()])
        .then(() => renderImageGenerationControls())
        .catch(error => console.error('Initialize image generation controls error:', error));

    // === 移动端侧边栏切换 ===
    const sidebarToggleBtn = document.getElementById('sidebarToggleBtn');
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    if (sidebarToggleBtn && sidebar && sidebarOverlay) {
        sidebarToggleBtn.addEventListener('click', () => {
            sidebar.classList.toggle('open');
            sidebarOverlay.classList.toggle('active');
        });
        sidebarOverlay.addEventListener('click', () => {
            sidebar.classList.remove('open');
            sidebarOverlay.classList.remove('active');
        });
    }

    // Event Listeners
    elements.configBtn.addEventListener('click', openConfigModal);
    elements.configModal.querySelector('.modal-close').addEventListener('click', () => {
        elements.configModal.classList.remove('active');
    });
    elements.saveConfigBtn.addEventListener('click', saveConfigs);
    elements.configImageProvider.addEventListener('change', () => {
        updateImageConfigVisibility();
    });
    elements.imageProviderStatusButton.addEventListener('pointerenter', event => {
        if (event.pointerType === 'mouse') {
            elements.imageProviderStatus.classList.remove('is-touch-input');
        }
    });
    elements.imageProviderStatusButton.addEventListener('pointerdown', event => {
        elements.imageProviderStatus.classList.toggle('is-touch-input', event.pointerType !== 'mouse');
        elements.imageProviderStatusButton.dataset.openOnPointerDown =
            elements.imageProviderStatusButton.getAttribute('aria-expanded');
    });
    elements.imageProviderStatusButton.addEventListener('click', event => {
        event.stopPropagation();
        const wasOpen = elements.imageProviderStatusButton.dataset.openOnPointerDown;
        const isOpen = elements.imageProviderStatusButton.getAttribute('aria-expanded') === 'true';
        const nextOpen = event.detail > 0 && wasOpen !== undefined
            ? wasOpen !== 'true'
            : !isOpen;
        delete elements.imageProviderStatusButton.dataset.openOnPointerDown;
        setImageProviderStatusOpen(nextOpen);
    });
    elements.imageProviderStatusButton.addEventListener('focus', () => {
        setImageProviderStatusOpen(true);
    });
    elements.imageProviderStatusButton.addEventListener('blur', () => {
        window.setTimeout(() => {
            if (!elements.imageProviderStatus.contains(document.activeElement)) {
                setImageProviderStatusOpen(false);
            }
        }, 0);
    });
    elements.imageProviderStatusButton.addEventListener('keydown', event => {
        if (event.key === 'Escape') {
            setImageProviderStatusOpen(false);
            elements.imageProviderStatusButton.blur();
        }
    });
    document.addEventListener('click', event => {
        if (!elements.imageProviderStatus.contains(event.target)) {
            setImageProviderStatusOpen(false);
        }
    });
    elements.imageProviderSelect.addEventListener('change', async () => {
        state.activeImageProvider = elements.imageProviderSelect.value;
        renderImageModelChoices(state.activeImageProvider);
        await persistImageGenerationSettings(false);
    });
    elements.imageModelSelect.addEventListener('change', async () => {
        state.activeImageModel = elements.imageModelSelect.value;
        renderImageProviderOptions();
        await persistImageGenerationSettings(false);
    });

    elements.resetFormBtn.addEventListener('click', clearForm);

    // AI Tools
    elements.aiGenerateOpenBtn.addEventListener('click', () => openAiModal('generate'));
    elements.aiModifyOpenBtn.addEventListener('click', () => openAiModal('modify'));
    elements.aiModal.querySelector('.modal-close').addEventListener('click', () => {
        if (aiAbortController) aiAbortController.abort();
        elements.aiModal.classList.remove('active');
    });
    
    // New AI Modal Listeners
    if (elements.aiModalCancelBtn) {
        elements.aiModalCancelBtn.addEventListener('click', () => {
             if (aiAbortController) aiAbortController.abort();
             elements.aiModal.classList.remove('active');
        });
    }
    if (elements.aiModalExecuteBtn) elements.aiModalExecuteBtn.addEventListener('click', handleAiExecute);
    if (elements.aiModalStopBtn) elements.aiModalStopBtn.addEventListener('click', handleAiStop);
    if (elements.aiModalApplyBtn) elements.aiModalApplyBtn.addEventListener('click', applyAiResult);
    
    // AI Modal Image Upload
    if (elements.aiUploadImageBtn) elements.aiUploadImageBtn.addEventListener('click', () => elements.aiImageInput.click());
    if (elements.aiImageInput) elements.aiImageInput.addEventListener('change', handleAiImageUpload);

    // Image Upload
    elements.uploadImageBtn.addEventListener('click', () => elements.imageInput.click());
    elements.imageInput.addEventListener('change', handleImageUpload);

    // Form inputs change -> update JSON
    document.querySelectorAll('.app-container input, .app-container textarea').forEach(el => {
        if (!el.id.startsWith('gen') && !el.id.startsWith('ai') && !el.id.startsWith('config')) {
            el.addEventListener('input', updateJsonPreview);
        }
    });

    // Copy JSON
    elements.copyJsonBtn.addEventListener('click', () => {
        if (!elements.jsonPreviewText.value) return;
        navigator.clipboard.writeText(elements.jsonPreviewText.value).then(() => {
            showToast('已复制 JSON');
        });
    });

    // JSON 预览 显示/隐藏（通过在 preview-area-row 上切换 json-hidden）
    const previewAreaRow = document.getElementById('previewAreaRow');
    elements.jsonPreviewToggleBtn.addEventListener('click', () => {
        previewAreaRow.classList.remove('json-hidden');
    });
    elements.jsonPreviewHideBtn.addEventListener('click', () => {
        previewAreaRow.classList.add('json-hidden');
    });

    // Generate Image Button
    elements.generateImageBtn.addEventListener('click', generateImage);

    // Tab Switching Logic
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabPanels = document.querySelectorAll('.tab-panel');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');

            // Update buttons
            tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // Update panels
            tabPanels.forEach(panel => {
                if (panel.id === `tab-${targetTab}`) {
                    panel.classList.add('active');
                } else {
                    panel.classList.remove('active');
                }
            });
        });
    });

    // Load presets logic
    loadPresets();
    initCategoryPresets();

    // Init Advanced Settings
    initAdvancedSettings();

    elements.presetSelect.addEventListener('change', async () => {
        const name = elements.presetSelect.value;
        if (name) {
            try {
                const res = await fetch(`/api/presets/${name}`);
                const data = await res.json();
                setFormData(data);
                showToast('预设加载成功');
            } catch (e) { console.error(e); }
        }
    });

    // Save Preset
    elements.savePresetBtn.addEventListener('click', async () => {
        const name = prompt('预设名称:');
        if (!name) return;
        const data = getFormData();
        await fetch('/api/presets', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, data })
        });
        showToast('保存成功');
        loadPresets();
    });

    // Delete Preset
    elements.deletePresetBtn.addEventListener('click', async () => {
        const name = elements.presetSelect.value;
        if (!name) return;
        if (!confirm('确定删除?')) return;
        await fetch(`/api/presets/${name}`, { method: 'DELETE' });
        showToast('删除成功');
        loadPresets();
    });
}

async function initAdvancedSettings() {
    // 1. Toggle Special Requirements
    elements.specialRequirementEnabled.addEventListener('change', () => {
        elements.specialRequirementGroup.style.display = elements.specialRequirementEnabled.checked ? 'block' : 'none';
        updateJsonPreview();
    });
    elements.specialRequirementInput.addEventListener('input', updateJsonPreview);

    // 2. Toggle Line Art Mode
    elements.lineArtModeEnabled.addEventListener('change', () => {
        const enabled = elements.lineArtModeEnabled.checked;
        elements.lineArtGroup.style.display = enabled ? 'block' : 'none';
        
        // Disable other inputs
        const allInputs = document.querySelectorAll('.field-control input, .field-control textarea, .field-control button, #negativePromptEnabled, #negativePromptInput, #negativeTagInput');
        allInputs.forEach(el => {
            // Skip control buttons/checkboxes and special req
            if (el.id === 'lineArtModeEnabled' || 
                el.id === 'lineArtPromptInput' || 
                el.id === 'specialRequirementEnabled' || 
                el.id === 'specialRequirementInput' ||
                el.id.startsWith('gen') || // Generation controls
                el.id.startsWith('config') || // Config controls
                el.id === 'presetSelect' // Preset select
            ) {
                return;
            }
            // Skip buttons
            if (el.type === 'button' || el.type === 'submit') return;

            el.disabled = enabled;
        });

        if (enabled) {
            // Load saved prompt if empty
            if (!elements.lineArtPromptInput.value) {
                loadLineArtPrompt();
            }
        }
        updateJsonPreview();
    });
    elements.lineArtPromptInput.addEventListener('input', updateJsonPreview);

    // Save Line Art Prompt
    elements.saveLineArtPromptBtn.addEventListener('click', async () => {
        const prompt = elements.lineArtPromptInput.value;
        if (!prompt) return;
        try {
            await fetch('/api/line-art-prompt', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt })
            });
            showToast('线稿提示词保存成功', 'success');
        } catch (e) {
            showToast('保存失败: ' + e, 'error');
        }
    });

    async function loadLineArtPrompt() {
        try {
            const res = await fetch('/api/line-art-prompt');
            const data = await res.json();
            if (data.prompt) {
                elements.lineArtPromptInput.value = data.prompt;
                updateJsonPreview();
            }
        } catch (e) { console.error(e); }
    }

    // 3. Toggle Negative Prompt
    elements.negativePromptEnabled.addEventListener('change', () => {
        elements.negativePromptGroup.style.display = elements.negativePromptEnabled.checked ? 'flex' : 'none';
        updateJsonPreview();
    });

    const negativeTagEndpoint =
        '/api/options/' + encodeURIComponent('反向提示词标签');

    const applyNegativeTag = item => {
        const current = elements.negativePromptInput.value.trim();
        if (!current) {
            elements.negativePromptInput.value = item;
        } else if (!current.includes(item)) {
            const separator = /[,，\s]$/.test(current) ? '' : ', ';
            elements.negativePromptInput.value = current + separator + item;
        }
        elements.negativePromptInput.dispatchEvent(
            new Event('input', { bubbles: true })
        );
        elements.negativePromptInput.focus();
    };

    const renderNegativeTags = items => {
        elements.negativeTagsContainer.innerHTML = '';
        if (!items || items.length === 0) {
            elements.negativeTagsContainer.innerHTML =
                '<span style="color: var(--text-tertiary);">无标签</span>';
            return;
        }

        items.forEach(item => {
            const tag = document.createElement('span');
            tag.className = 'negative-tag';

            const applyButton = document.createElement('button');
            applyButton.type = 'button';
            applyButton.className = 'negative-tag-value';
            applyButton.textContent = item;
            applyButton.addEventListener('click', () => applyNegativeTag(item));

            const deleteButton = document.createElement('button');
            deleteButton.type = 'button';
            deleteButton.className = 'negative-tag-delete';
            deleteButton.textContent = '×';
            deleteButton.title = '删除标签：' + item;
            deleteButton.setAttribute('aria-label', '删除标签：' + item);
            deleteButton.addEventListener('click', () => deleteNegativeTag(item));

            tag.appendChild(applyButton);
            tag.appendChild(deleteButton);
            elements.negativeTagsContainer.appendChild(tag);
        });
    };

    async function loadNegativeTags() {
        try {
            const response = await fetch(negativeTagEndpoint);
            if (!response.ok) throw new Error(response.statusText);
            renderNegativeTags(await response.json());
        } catch (e) {
            console.error('Failed to load negative prompt tags', e);
        }
    }

    const deleteNegativeTag = async item => {
        try {
            const response = await fetch(negativeTagEndpoint, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ value: item })
            });
            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.error || response.statusText);
            }
            await loadNegativeTags();
            showToast('标签已删除', 'success');
        } catch (e) {
            showToast('删除失败: ' + e.message, 'error');
        }
    };

    const addNegativeTag = async () => {
        const value = elements.negativeTagInput.value.trim();
        if (!value) {
            showToast('请输入标签内容', 'error');
            return;
        }

        try {
            const response = await fetch(negativeTagEndpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ value })
            });
            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.error || response.statusText);
            }

            elements.negativeTagInput.value = '';
            await loadNegativeTags();
            showToast('标签已添加', 'success');
        } catch (e) {
            showToast('添加失败: ' + e.message, 'error');
        }
    };

    elements.addNegativeTagBtn.addEventListener('click', addNegativeTag);
    elements.negativeTagInput.addEventListener('keydown', event => {
        if (event.key === 'Enter') {
            event.preventDefault();
            addNegativeTag();
        }
    });
    await loadNegativeTags();
}

async function loadPresets() {
    try {
        const res = await fetch('/api/presets');
        const list = await res.json();
        elements.presetSelect.innerHTML = '<option value="">选择预设...</option>';
        list.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.name;
            opt.textContent = p.name;
            elements.presetSelect.appendChild(opt);
        });
    } catch (e) { console.error(e); }
}

function getNestedValue(obj, path) {
    let current = obj;
    for (const key of path) {
        if (current === null || current === undefined) return undefined;
        current = current[key];
    }
    return current;
}

document.addEventListener('DOMContentLoaded', init);
