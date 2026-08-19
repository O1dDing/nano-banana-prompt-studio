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
    addImageFilesToList(e.target.files, aiUploadedImages, renderAiUploadedImages);
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
    // 原地清空：拖拽/粘贴上传的闭包持有该数组引用，不能重新赋值
    aiUploadedImages.length = 0;
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
    const thinkingStatusText = elements.aiStatusText.textContent;
    let streamStatusText = '';
    elements.aiModalExecuteBtn.style.display = 'none';
    elements.aiModalStopBtn.style.display = 'inline-block';
    elements.aiModalApplyBtn.style.display = 'none';

    // 耗时反馈：生成期间实时显示已耗时
    const stopStatusTimer = startElapsedTimer(seconds => {
        elements.aiStatusText.textContent = `正在生成 · 已耗时 ${seconds}s`;
        if (streamStatusText) {
            elements.aiStatusText.textContent = streamStatusText;
        }
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

        if (!response.ok) {
            let message = `API request failed (${response.status})`;
            try {
                const payload = await response.json();
                message = payload.error || message;
            } catch (_error) {
                // Keep the HTTP fallback when the response is not JSON.
            }
            throw new Error(message);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullContent = '';
        const sseParser = new SseStream.SseEventParser();
        let receivedDone = false;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const dataEvents = sseParser.push(decoder.decode(value));
            for (const dataStr of dataEvents) {

                    if (dataStr === '[DONE]') {
                        aiFinalStatus = '生成完成';
                        receivedDone = true;
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
                        const event = SseStream.parseSseJsonEvent(dataStr);
                        if (event.type === 'status') {
                            if (event.status === 'thinking') {
                                streamStatusText = thinkingStatusText;
                            }
                        } else if (event.type === 'content') {
                            streamStatusText = '';
                            fullContent += event.content;
                            elements.aiResponsePreview.value = fullContent;
                            elements.aiResponsePreview.scrollTop = elements.aiResponsePreview.scrollHeight;
                        }
                    }
            }
        }
        sseParser.finish();
        if (!receivedDone) {
            throw new Error('AI \u6d41\u5f0f\u54cd\u5e94\u610f\u5916\u4e2d\u65ad');
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
