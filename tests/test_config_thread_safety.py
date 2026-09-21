import tempfile
import threading
from pathlib import Path

import yaml

from nano_banana.core.config import AIConfigManager


def test_concurrent_config_writes_remain_valid_yaml():
    with tempfile.TemporaryDirectory() as directory:
        manager = AIConfigManager()
        manager.config_path = Path(directory) / "ai_config.yaml"
        errors = []

        def writer(index):
            for iteration in range(30):
                if not manager.save_config(
                    {
                        "model": f"model-{index}-{iteration}",
                        "chat_web_search_mode": (
                            "force" if iteration % 2 else "auto"
                        ),
                    }
                ):
                    errors.append((index, iteration))

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        parsed = yaml.safe_load(manager.config_path.read_text(encoding="utf-8"))
        assert isinstance(parsed, dict)
        assert parsed["chat"]["model"].startswith("model-")
        assert parsed["chat"]["web_search_mode"] in {"auto", "force"}
        assert list(Path(directory).glob("*.tmp")) == []
