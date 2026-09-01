// Schema-driven prompt document helpers. Requires window.PROMPT_SCHEMA.
(function (global) {
    'use strict';

    function getSchema() {
        return global.PROMPT_SCHEMA;
    }

    function schemaFields() {
        const schema = getSchema();
        if (!schema) return [];
        return schema.categories.flatMap(category =>
            category.fields.map(field => ({ ...field, categoryId: category.id }))
        );
    }

    function categoryPresetConfig() {
        const schema = getSchema();
        const result = {};
        if (!schema) return result;
        schema.categories.forEach(category => {
            result[category.id] = category.fields.map(field => [field.id, field.path]);
        });
        return result;
    }

    function setAtPath(target, path, value) {
        let current = target;
        path.slice(0, -1).forEach(key => {
            if (!current[key] || typeof current[key] !== 'object' || Array.isArray(current[key])) {
                current[key] = {};
            }
            current = current[key];
        });
        current[path[path.length - 1]] = value;
    }

    function getAtPath(source, path) {
        let current = source;
        for (const key of path) {
            if (current === null || current === undefined) return undefined;
            current = current[key];
        }
        return current;
    }

    function encodeField(field, raw) {
        if (field.type === 'string_list') {
            const text = (raw || '').trim();
            if (!text) return [];
            const items = text.split(',').map(item => item.trim()).filter(Boolean);
            return items.length ? items : [raw];
        }
        return raw || '';
    }

    function decodeField(field, value) {
        if (field.type === 'string_list' && Array.isArray(value)) {
            return value.join(', ');
        }
        if (value === null || value === undefined) return '';
        return String(value);
    }

    function nestFromElements(elements) {
        const data = {};
        schemaFields().forEach(field => {
            const el = elements[field.id] || document.getElementById(field.id);
            const raw = el ? el.value : '';
            setAtPath(data, field.path, encodeField(field, raw));
        });
        return data;
    }

    function fillElementsFromData(elements, data) {
        if (!data) return;
        schemaFields().forEach(field => {
            const el = elements[field.id] || document.getElementById(field.id);
            if (!el) return;
            const value = getAtPath(data, field.path);
            if (value === undefined) return;
            el.value = decodeField(field, value);
        });
        const expression = getAtPath(data, ['场景', '主体', '表情与动作']);
        if (typeof expression === 'string' && elements.action && elements.emotion) {
            elements.action.value = expression;
            elements.emotion.value = '';
        }
    }

    function subsetFromData(data, categoryId) {
        const schema = getSchema();
        const result = {};
        const category = (schema?.categories || []).find(item => item.id === categoryId);
        if (!category) return result;
        category.fields.forEach(field => {
            const value = getAtPath(data, field.path);
            if (value === undefined) return;
            setAtPath(result, field.path, value);
        });
        return result;
    }

    function overlayDefault(id) {
        const overlay = (getSchema()?.overlays || []).find(item => item.id === id);
        return overlay?.default || '';
    }

    global.PromptDoc = {
        getSchema,
        schemaFields,
        categoryPresetConfig,
        nestFromElements,
        fillElementsFromData,
        subsetFromData,
        overlayDefault,
        getAtPath,
        setAtPath,
    };

    global.promptSchemaPromise = fetch('/api/schema')
        .then(response => response.json())
        .then(schema => {
            global.PROMPT_SCHEMA = schema;
            return schema;
        });
})(window);
