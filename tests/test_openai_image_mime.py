from types import SimpleNamespace

from PIL import Image

from nano_banana.core.images.openai_images import OpenAIImagesProvider


class FakeImagesApi:
    def __init__(self):
        self.call = None
        self.magic = None

    def edit(self, **kwargs):
        self.call = kwargs
        upload = kwargs["image"]
        name, file_obj, mime_type = upload
        self.magic = file_obj.read(12)
        file_obj.seek(0)
        return SimpleNamespace(data=[])


def test_webp_with_unknown_filename_gets_explicit_mime(tmp_path):
    path = tmp_path / "reference.bin"
    Image.new("RGB", (8, 8), "red").save(path, format="WEBP")

    provider = object.__new__(OpenAIImagesProvider)
    provider.client = SimpleNamespace(images=FakeImagesApi())
    provider._edit_image(
        [str(path)],
        {"model": "gpt-image-2", "prompt": "test", "size": "1024x1024"},
    )

    upload_name, _, mime_type = provider.client.images.call["image"]
    assert upload_name.endswith(".webp")
    assert mime_type == "image/webp"
    assert provider.client.images.magic.startswith(b"RIFF")


def test_supported_mime_is_detected_from_content_not_suffix(tmp_path):
    cases = [
        ("JPEG", "image/jpeg", ".jpg"),
        ("PNG", "image/png", ".png"),
        ("WEBP", "image/webp", ".webp"),
    ]
    for image_format, expected_mime, expected_suffix in cases:
        path = tmp_path / f"{image_format.lower()}.data"
        Image.new("RGB", (8, 8), "blue").save(path, format=image_format)
        mime_type, upload_name = OpenAIImagesProvider._detect_openai_input_mime(
            str(path)
        )
        assert mime_type == expected_mime
        assert upload_name.endswith(expected_suffix)
