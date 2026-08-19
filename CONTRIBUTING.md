# Contributing

```bash
pip install -e ".[dev,desktop,web]"
pytest
```

桌面：`pip install -e ".[desktop]"` 然后 `python src/main.py`  
Web：`pip install -e ".[web]"` 然后 `python src/web/start.py`  
不要再维护两份钉死版本的 requirements；根目录 `requirements.txt` 只是 extras 的入口。

## 加一个提示词字段

1. 编辑 [`src/nano_banana/core/schema.yaml`](src/nano_banana/core/schema.yaml)：补 `id`、`path`、`widget_key`、`options_key`。`id` 给 Web DOM，`widget_key` 对齐 `options.yaml` / 桌面控件，`path` 是对外 JSON。
2. 在 [`src/config/options.yaml`](src/config/options.yaml) 加上对应选项（combo 才需要）。
3. Web HTML 仍手写：在对应 tab 加 `id="<field.id>"`，`data-field-name` 用 `widget_key`。
4. 跑 `pytest tests/test_prompt_schema.py tests/test_web_scene_fields.py`。

桌面 `FormPanel`、`getFormData` / `setFormData`、分类预设 `subset`、AI 系统提示里的示例 JSON 都会跟 schema 走。不要改 `options.yaml` 去兼做 schema。

## 加一个生图渠道

1. 在 [`src/nano_banana/core/images/provider_config.py`](src/nano_banana/core/images/provider_config.py) 的 `IMAGE_PROVIDER_META` 登记 id / 默认模型 / 扁平兼容 key。
2. 新建 `src/nano_banana/core/images/<name>.py`：class 上挂 `CAPABILITIES`（UI 参数跟 class 走，不要再抄一份大 dict），实现 `set_generation_options` + `generate_image`。
3. 在 [`protocol._registry()`](src/nano_banana/core/images/protocol.py) 注册一行。
4. 旧 `ai_config.yaml` 仍是扁平 key 也能读；新写入会变成嵌套 `image.providers.<id>`。

不要把凭证写进仓库。`src/config/ai_config.yaml` 已被 gitignore。
