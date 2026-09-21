"""Chromium UI smoke tests. All model endpoints use fixtures; no paid calls."""
import base64
import json
import os
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from PIL import Image
from playwright.sync_api import sync_playwright
from nano_banana.core.schema import get_schema
from nano_banana.core.images.gpt_options import capabilities, GPT_IMAGE_MODELS
from nano_banana.core.images.codex_images import capabilities as codex_capabilities


def main():
    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/':
                self.path = '/static/index.html'
            super().do_GET()
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(ROOT / 'src/web')))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'
    config = {'image_provider': 'openai_images', 'openai_image_model': 'gpt-image-2.5-sunburst',
              'base_url': 'https://unused.invalid/v1', 'model': 'unused', 'has_api_key': True,
              'chat_engine': 'api', 'chat_web_search_mode': 'auto'}
    providers = {
        'openai_images': {'label': 'OpenAI Images', 'models': GPT_IMAGE_MODELS,
            'configured_model': 'gpt-image-2.5-sunburst', 'default_model': 'gpt-image-2',
            'model_config_key': 'openai_image_model', 'is_configured': True,
            'capabilities': {m: capabilities(m) for m in GPT_IMAGE_MODELS}},
        'codex_images': {'label': 'Codex Image', 'models': ['gpt-image-2'],
            'configured_model': 'gpt-image-2', 'default_model': 'gpt-image-2',
            'model_config_key': 'codex_image_model', 'is_configured': True,
            'capabilities': {'gpt-image-2': codex_capabilities()}},
    }
    for key in ('gemini', 'qwen_image', 'doubao_image'):
        providers[key] = {'label': key, 'models': [key], 'configured_model': key,
            'default_model': key, 'model_config_key': key + '_model', 'is_configured': True,
            'capabilities': {key: {'options': {}}}}
    image = BytesIO()
    Image.new('RGB', (64, 64), 'white').save(image, 'WEBP')
    image_url = 'data:image/webp;base64,' + base64.b64encode(image.getvalue()).decode()
    jobs, cancelled, errors = {}, [], []
    codex_logged_in = {'value': True}
    def api(route):
        path = route.request.url.split(origin, 1)[-1]
        method = route.request.method
        body = route.request.post_data_json if route.request.post_data else {}
        data, status = {}, 200
        if path == '/api/schema':
            data = get_schema().to_public_dict()
        elif path == '/api/config':
            if method == 'POST':
                config.update(body)
                data = {'success': True}
            else:
                data = config
        elif path == '/api/image-providers':
            data = providers
        elif path == '/api/codex/status':
            data = {'logged_in': codex_logged_in['value'],
                    'error': None if codex_logged_in['value'] else 'fixture not logged in',
                    'image_available': True,
                    'prompt_workers': 4, 'image_workers': 4,
                    'models': [
                        {'model': 'gpt-6-astra', 'displayName': 'GPT-6-Astra', 'isDefault': True,
                         'defaultReasoningEffort': 'high', 'inputModalities': ['text', 'image'],
                         'supportedReasoningEfforts': [
                             {'reasoningEffort': 'low'}, {'reasoningEffort': 'medium'},
                             {'reasoningEffort': 'high'}, {'reasoningEffort': 'xhigh'},
                             {'reasoningEffort': 'max'}]},
                        {'model': 'gpt-5.6-sol', 'displayName': 'GPT-5.6-Sol', 'isDefault': False,
                         'defaultReasoningEffort': 'medium', 'inputModalities': ['text', 'image'],
                         'supportedReasoningEfforts': [
                             {'reasoningEffort': 'none'}, {'reasoningEffort': 'low'},
                             {'reasoningEffort': 'medium'}, {'reasoningEffort': 'high'},
                             {'reasoningEffort': 'xhigh'}, {'reasoningEffort': 'max'}]},
                    ]}
        elif path == '/api/image-generation-settings':
            data = {'success': True}
        elif path == '/api/generate-image':
            task = str(len(jobs) + 1)
            jobs[task] = {'body': body, 'polls': 0}
            data, status = {'task_id': task, 'status': 'queued'}, 202
        elif path.startswith('/api/generate-image/status/'):
            job = jobs[path.rsplit('/', 1)[-1]]
            job['polls'] += 1
            data = {'status': 'processing'} if job['polls'] < 2 or 'CANCEL_TEST' in job['body']['prompt'] else {
                'status': 'completed', 'image': image_url, 'images': [image_url],
                'metadata': {'actual_sizes': ['64x64'], 'output_mime': 'image/webp', 'billing': 'api'}}
        elif path.startswith('/api/generate-image/cancel/'):
            cancelled.append(path.rsplit('/', 1)[-1])
            data = {'status': 'cancelled'}
        elif path in ('/api/generate', '/api/modify'):
            output = json.dumps({'风格模式': '摄影', '场景': {'主体': {'整体描述': '一只猫'}}}, ensure_ascii=False)
            events = [{'status': 'started'}, {'codex_preview': '临时预览'}, {'codex_preview': ''}, {'content': output}]
            stream = ''.join('data: ' + json.dumps(e, ensure_ascii=False) + '\n\n' for e in events) + 'data: [DONE]\n\n'
            route.fulfill(status=200, content_type='text/event-stream', body=stream)
            return
        elif path.startswith('/api/options'):
            data = {} if path == '/api/options' else []
        elif 'preset' in path:
            data = []
        elif path == '/api/line-art-prompt':
            data = {'prompt': ''}
        route.fulfill(status=status, content_type='application/json', body=json.dumps(data))
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=os.environ.get('CHROMIUM_PATH'))
            ctx = browser.new_context(viewport={'width': 1600, 'height': 1100})
            ctx.route(origin + '/api/**', api)
            def page():
                tab = ctx.new_page()
                tab.on('pageerror', lambda error: errors.append(str(error)))
                tab.goto(origin)
                tab.wait_for_selector('#image-option-quality')
                return tab
            a = page()
            assert a.locator('#imageProviderSelect option').count() == 5
            a.locator('#configBtn').click()
            a.locator('#configChatEngine').select_option('codex')
            assert a.locator('#configApiKey').is_hidden()
            a.locator('#refreshCodexStatus').click()
            a.wait_for_function("document.getElementById('codexStatus').textContent === 'ChatGPT 已登录'")
            assert a.locator('#codexStatus').evaluate("el => el.classList.contains('is-success')")
            assert 'Prompt' not in a.locator('#codexStatus').inner_text()
            assert a.locator('#configOpenAIImageModel').get_attribute('list') is None
            assert a.locator('#openaiImageModelToggle').count() == 1
            a.locator('#openaiImageModelToggle').click()
            a.wait_for_selector('#openaiImageModelOptions:not([hidden])')
            assert a.locator('.openai-image-model-option[data-model-id="gpt-image-2.5-sunburst"]').count() == 1
            a.locator('#openaiImageModelToggle').click()
            codex_logged_in['value'] = False
            a.locator('#refreshCodexStatus').click()
            a.wait_for_function("document.getElementById('codexStatus').textContent === 'ChatGPT 未登录'")
            assert a.locator('#codexStatus').evaluate("el => el.classList.contains('is-error')")
            codex_logged_in['value'] = True
            a.locator('#refreshCodexStatus').click()
            a.wait_for_function("document.getElementById('codexStatus').textContent === 'ChatGPT 已登录'")
            a.locator('#configCodexModelButton').click()
            a.wait_for_selector('#codexModelOptions:not([hidden])')
            astra = a.locator('.codex-model-option[data-model-id="gpt-6-astra"]')
            assert astra.locator('strong').inner_text() == '6 Astra'
            assert astra.locator('span').inner_text().startswith('gpt-6-astra')
            astra.click()
            assert a.locator('#configCodexModel').input_value() == 'gpt-6-astra'
            efforts = a.locator('#configCodexEffort').locator('option').all_text_contents()
            assert 'max' in efforts and 'minimal' not in efforts
            a.locator('#configCodexEffort').select_option('max')
            a.locator('#saveConfigBtn').click()
            a.wait_for_function("!document.getElementById('configModal').classList.contains('active')")
            assert a.locator('#image-option-output_compression').count() == 0
            assert a.locator('label[for="image-option-size"]').inner_text() == '精确尺寸'
            assert a.locator('#image-option-size').input_value() == ''
            assert a.locator('#image-option-size').get_attribute('placeholder') == '默认留空 / 16x'
            assert a.locator('#image-option-size').evaluate("el => el.classList.contains('select-arrow-input')")
            assert '655360' not in a.locator('#imageProviderOptions').inner_text()
            assert '每边≤3840' not in a.locator('#imageProviderOptions').inner_text()
            assert a.locator('label[for="image-option-aspect_ratio"]').inner_text() == '宽高比'
            assert a.locator('label[for="image-option-image_size"]').inner_text() == '尺寸档位'
            assert a.locator('label[for="image-option-quality"]').inner_text() == '生成质量'
            assert a.locator('label[for="image-option-output_format"]').inner_text() == '输出格式'
            assert a.locator('label[for="image-option-moderation"]').inner_text() == '审核强度'
            assert a.locator('label[for="image-option-n"]').inner_text() == '每次生成张数'
            a.locator('#image-option-quality').select_option('max')
            a.locator('#image-option-size').fill('2048x1152')
            a.locator('#image-option-output_format').select_option('webp')
            a.locator('#generateImageBtn').click()
            a.wait_for_selector('.generated-img')
            assert jobs['1']['body']['options']['quality'] == 'max'
            assert jobs['1']['body']['options']['size'] == '2048x1152'
            assert a.locator('.generated-img').get_attribute('src').startswith('data:image/webp;')
            a.locator('#image-option-size').fill('')
            a.locator('#image-option-image_size').select_option('4K')
            a.locator('#image-option-aspect_ratio').select_option('21:9')
            a.wait_for_function("document.getElementById('imageParameterHint').textContent === '3840x1648 · 实验性尺寸'")
            assert a.locator('#imageParameterHint').evaluate("el => el.classList.contains('is-experimental')")
            assert a.locator('#imageParameterHint strong').inner_text() == '实验性尺寸'
            a.locator('#image-option-size').fill('3840x3840')
            a.locator('#generateImageBtn').click()
            a.wait_for_timeout(100)
            assert len(jobs) == 1, 'invalid size was submitted'
            assert a.locator('#imageProviderSelect option[value="codex_images"]').inner_text() == 'Codex Image'
            a.locator('#imageProviderSelect').select_option('codex_images')
            assert 'xhigh' not in a.locator('#image-option-quality').inner_text()
            assert a.locator('#image-option-output_compression').count() == 0
            assert '2.5' not in a.locator('#imageModelSelect').inner_text()
            assert a.locator('label[for="image-option-size"]').inner_text() == '期望像素尺寸'
            assert '（' not in a.locator('#imageProviderOptions').inner_text()
            a.locator('#aiGenerateOpenBtn').click()
            a.wait_for_selector('#aiPromptEngineSelect')
            a.wait_for_function("document.getElementById('aiPromptEngineSelect').value === 'codex'")
            a.wait_for_function("document.getElementById('aiPromptBackendMeta').textContent.includes('ChatGPT 已登录')")
            assert 'Codex' in a.locator('#aiPromptBackendTitle').inner_text()
            a.locator('#aiPromptEngineSelect').select_option('api')
            a.wait_for_function("document.getElementById('aiPromptBackendTitle').textContent.includes('原有 API')")
            a.locator('#aiPromptEngineSelect').select_option('codex')
            a.wait_for_function("document.getElementById('aiPromptBackendMeta').textContent.includes('ChatGPT 已登录')")
            a.locator('#aiPromptInput').fill('一只猫')
            a.locator('#aiModalExecuteBtn').click()
            a.wait_for_function("document.getElementById('aiModalApplyBtn').style.display !== 'none'")
            assert '临时预览' not in a.locator('#aiResponsePreview').input_value()
            a.locator('#aiModalApplyBtn').click()
            tabs = [page() for _ in range(4)]
            for i, tab in enumerate(tabs):
                tab.evaluate('(i)=>{elements.jsonPreviewText.value=JSON.stringify({tab:i})}', i)
                tab.locator('#generateImageBtn').click()
            for tab in tabs:
                tab.wait_for_selector('.generated-img')
            assert len(jobs) == 5
            assert len({j['body']['prompt'] for j in list(jobs.values())[1:]}) == 4
            a.locator('#imageProviderSelect').select_option('openai_images')
            a.locator('#image-option-size').fill('1024x1024')
            a.evaluate("elements.jsonPreviewText.value=JSON.stringify({note:'CANCEL_TEST'})")
            a.locator('#generateImageBtn').click()
            a.wait_for_function('Boolean(state.currentImageTaskId)')
            a.locator('#generateImageBtn').click()
            a.wait_for_timeout(200)
            assert cancelled, 'stop did not reach cancellation API'
            assert not errors, errors
            browser.close()
            print('Browser smoke: controls / soft capabilities / JSON preview / four tabs / cancellation PASS')
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
