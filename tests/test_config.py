"""测试配置加载"""

import tempfile
from pathlib import Path

from bbt.config import load_config, AppConfig


class TestConfig:
    def test_default_config(self):
        cfg = load_config("/nonexistent/path")
        assert isinstance(cfg, AppConfig)
        assert cfg.whisper.model == "large-v3"
        assert cfg.whisper.language == "zh"

    def test_custom_config(self):
        toml = """
[whisper]
model = "tiny"
language = "en"

[llm]
api_key = "test-key"
base_url = "https://example.com/v1"
model = "gpt-4"
"""
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False)
        f.write(toml)
        f.close()

        cfg = load_config(f.name)
        assert cfg.whisper.model == "tiny"
        assert cfg.whisper.language == "en"
        assert cfg.llm.api_key == "test-key"
        assert cfg.llm.base_url == "https://example.com/v1"
        assert cfg.llm.model == "gpt-4"

        Path(f.name).unlink()
