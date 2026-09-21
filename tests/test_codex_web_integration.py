import base64
import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PIL import Image

from nano_banana.core.config import AIConfigManager, flatten_legacy_or_nested, nest_config
from nano_banana.core.codex_schema import prompt_output_schema
from nano_banana.core.images.codex_images import CodexImageProvider, capabilities
from nano_banana.web.app import app
from nano_banana.web.blueprints import chat, images


def test_config_engine_roundtrip_without_api_key(tmp_path):
    manager=AIConfigManager();manager.config_path=tmp_path/'ai_config.yaml'
    assert manager.save_config({'chat_engine':'codex','codex_model':'example-model','codex_effort':'low','chat_web_search_mode':'force'})
    config=manager.get_chat_config()
    assert config['engine']=='codex' and config['api_key']==''
    assert config['codex_model']=='example-model'
    assert manager.set_active_image_selection('codex_images','gpt-image-2')
    assert manager.save_image_generation_options('codex_images','gpt-image-2', {'size':'2048x1152'})
    assert manager.get_image_provider()=='codex_images'
    assert manager.get_image_generation_options('codex_images','gpt-image-2')['size']=='2048x1152'
    with pytest.raises(ValueError):manager.set_active_image_selection('codex_images','gpt-image-2.5-flare')


def test_output_schema_derived_from_real_fields():
    from nano_banana.core.schema import get_schema
    schema=prompt_output_schema({'custom':{'count':3},'角色线稿生成':{'启用':True,'提示词':'outline'}})
    for field in get_schema().iter_fields():
        node=schema
        for key in field.path:node=node['properties'][key]
        assert 'type' in node
    assert schema['properties']['custom']['properties']['count']['type']=='integer'
    assert schema['additionalProperties'] is False


def test_codex_prompt_no_api_config_and_no_api_fallback():
    client=app.test_client()
    cfg={'engine':'codex','api_key':'','base_url':'','model':'','codex_model':'','codex_effort':'auto','web_search_mode':'auto'}
    def stream(*args):
        yield 'data: {"error":"no Codex login"}\n\n'
    with patch.object(chat.config_manager,'get_chat_config',return_value=cfg), patch.object(chat,'iter_prompt_sse',side_effect=stream), patch.object(chat,'create_chat_client') as paid:
        response=client.post('/api/generate',json={'prompt':'cat'})
        assert response.status_code==200
        assert b'no Codex login' in response.data
        paid.assert_not_called()


def test_codex_image_capabilities_are_honest():
    caps=capabilities()
    assert caps['parameter_control']=='prompt_hints'
    assert 'max' not in caps['options']['quality']['values']
    assert 'n' not in caps['options']
    with pytest.raises(ValueError):CodexImageProvider(model='gpt-image-2.5-sunburst')
    with pytest.raises(ValueError):CodexImageProvider().set_generation_options({'quality':'max'})


def test_codex_image_actual_dimensions_not_upscaled():
    buf=BytesIO();Image.new('RGB',(32,64)).save(buf,format='PNG')
    url='data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()
    class FakeBridge:
        def iter_job(self,payload,cancelled):
            assert payload['kind']=='image'
            assert '$imagegen' in payload['messages'][0]['content'][-1]['text']
            yield {'status':'completed','result':{'images':[url],'metadata':{'billing':'codex_subscription'}}}
        def close(self):pass
    with patch('nano_banana.core.images.codex_images.CodexBridge', FakeBridge):
        provider=CodexImageProvider()
        provider.set_generation_options({'size':'2048x1152','quality':'high','output_format':'webp'})
        image=provider.generate_image('cat')
    assert image.size==(32,64)
    assert provider.result_metadata['actual_sizes']==['32x64']
    assert any('未裁切' in warning for warning in provider.result_metadata['warnings'])


@pytest.mark.parametrize('fmt',['JPEG','WEBP','PNG'])
def test_web_result_preserves_native_bytes_for_all_formats(fmt):
    from nano_banana.core.images.artifacts import image_from_bytes
    buf=BytesIO();Image.new('RGB',(32,16)).save(buf,format=fmt)
    native=buf.getvalue()
    generated=image_from_bytes(native)
    class Provider:
        generated_images=[generated,generated]
        result_metadata={}
        def set_generation_options(self,options):pass
        def generate_image(self,**kwargs):return generated
    with patch.object(images,'create_image_provider_from_credentials',return_value=Provider()):
        result=images._run_image_generation(prompt='cat',images=[],provider='openai_images',credentials={'base_url':'x','api_key':'y'},model='gpt-image-2',options={})
    assert len(result['images'])==2
    assert base64.b64decode(result['image'].split(',',1)[1])==native
    assert result['metadata']['output_mime']=='image/'+fmt.lower()


def test_invalid_api_size_not_queued_or_billed():
    with patch.object(images.config_manager,'get_image_provider_config',return_value={'base_url':'x','api_key':'y','model':'gpt-image-2.5-flare'}), patch.object(images.image_task_manager,'submit') as submit:
        response=app.test_client().post('/api/generate-image',json={'provider':'openai_images','prompt':'cat','options':{'size':'3840x3840'}})
    assert response.status_code==400
    submit.assert_not_called()
