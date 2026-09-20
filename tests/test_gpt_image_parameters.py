import base64
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from nano_banana.core.images.artifacts import image_from_bytes, image_data_url, reference_bytes
from nano_banana.core.images.gpt_options import capabilities, normalize_options, validate_size, SIZE_MAP
from nano_banana.core.images.openai_images import OpenAIImagesProvider


@pytest.mark.parametrize('size', ['1024x1024', '1536x1024', '2048x1152', '2048x2048', '3840x2160', '2160x3840', '2880x2880', 'auto'])
def test_legal_sizes(size):
    assert validate_size(size) == size


@pytest.mark.parametrize('size', ['3840x3840', '4096x2048', '2049x1152', '1024x256', '512x512', '0x1024', '1024;rm', '3000x1000'])
def test_reject_size_not_round(size):
    with pytest.raises(ValueError):
        validate_size(size)


def test_all_legacy_presets_are_legal():
    for mapping in SIZE_MAP.values():
        for size in mapping.values():
            validate_size(size)


@pytest.mark.parametrize('model', ['gpt-image-2.5-sunburst', 'gpt-image-2.5-flare', 'gpt-image-2.5-flare-2026-09-08'])
def test_gpt25_max_quality_native(model):
    opts = normalize_options({'quality': 'max', 'size': '3840x2160', 'output_format': 'webp', 'output_compression': '0', 'n': '10'}, model)
    assert opts['quality'] == 'max' and opts['n'] == 10 and opts['output_compression'] == 0
    assert 'xhigh' in capabilities(model)['options']['quality']['values']



def test_web_capabilities_keep_native_backend_support_but_hide_compression_control():
    opts = capabilities('gpt-image-2.5-sunburst')['options']
    assert 'output_compression' not in opts
    assert opts['aspect_ratio']['label'] == '宽高比'
    assert opts['image_size']['label'] == '尺寸档位'
    assert opts['size']['label'] == '精确尺寸'
    assert opts['size']['default'] == ''
    assert opts['size']['placeholder'] == '留空 / auto'
    assert opts['quality']['label'] == '生成质量'
    assert opts['output_format']['label'] == '输出格式'
    assert opts['moderation']['label'] == '审核强度'
    assert opts['n']['label'] == '每次生成张数'
    # Direct/API callers remain backward compatible even though the Web no longer exposes this field.
    normalized = normalize_options({'output_format': 'webp', 'output_compression': 77},
                                   'gpt-image-2.5-sunburst')
    assert normalized['output_compression'] == 77

def test_gpt2_does_not_advertise_gpt25_quality():
    assert 'max' not in capabilities('gpt-image-2')['options']['quality']['values']
    with pytest.raises(ValueError):
        normalize_options({'quality':'max'}, 'gpt-image-2')


@pytest.mark.parametrize('opts', [{'n':11}, {'output_compression':101, 'output_format':'webp'}, {'output_compression':80}, {'background':'transparent','output_format':'jpeg'}, {'size':'1920x1080'}, {'n':True}])
def test_validation_before_billing(opts):
    with pytest.raises(ValueError):
        normalize_options(opts, 'gpt-image-2.5-sunburst')


@pytest.mark.parametrize('fmt', ['PNG', 'JPEG', 'WEBP'])
def test_native_bytes_not_transcoded(fmt):
    buf = BytesIO(); Image.new('RGB', (32,32), 'red').save(buf, format=fmt)
    raw = buf.getvalue()
    url = image_data_url(image_from_bytes(raw))
    assert url.startswith('data:image/' + fmt.lower() + ';base64,')
    assert base64.b64decode(url.split(',', 1)[1]) == raw


def test_local_encoding_not_upscaling():
    img = Image.new('RGBA', (64,32), (1,2,3,128))
    url = image_data_url(img, output_format='webp', compression=90)
    decoded = Image.open(BytesIO(base64.b64decode(url.split(',',1)[1])))
    assert decoded.size == (64,32) and decoded.format == 'WEBP'


def test_bmp_reference_conversion_retains_dimensions():
    buf = BytesIO(); Image.new('RGB', (17,23)).save(buf, format='BMP')
    assert image_from_bytes(reference_bytes(buf.getvalue())).size == (17,23)


def test_sdk_compatibility_forwards_unknown_native_fields_once():
    calls=[]
    def old_edit(*, model, image, prompt, extra_body=None):
        calls.append(locals().copy()); return 'ok'
    assert OpenAIImagesProvider._invoke(old_edit, {'model':'gpt-image-2.5-sunburst','image':'stream','prompt':'x', 'moderation':'low', 'quality':'max'}) == 'ok'
    assert len(calls) == 1
    assert calls[0]['extra_body'] == {'moderation':'low', 'quality':'max'}


def test_no_silent_retry_on_type_error():
    provider = object.__new__(OpenAIImagesProvider)
    provider.model='gpt-image-2';provider.options={};calls=[]
    def failing(**kw):
        calls.append(kw);raise TypeError('unsupported')
    provider.client=SimpleNamespace(images=SimpleNamespace(generate=failing))
    with pytest.raises(TypeError):
        provider.generate_image('prompt')
    assert len(calls)==1
