"""测试配置加载"""

import tempfile
from pathlib import Path

from bbt.config import load_config, AppConfig


class TestConfig:
    def test_default_config(self):
        cfg = load_config("/nonexistent/path")
        assert isinstance(cfg, AppConfig)
        assert cfg.transcriber.device == "coreml"

    def test_custom_config(self):
        toml = """
[transcriber]
device = "cuda"

[llm]
api_key = "test-key"
base_url = "https://example.com/v1"
model = "gpt-4"
"""
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False)
        f.write(toml)
        f.close()

        cfg = load_config(f.name)
        assert cfg.transcriber.device == "cuda"
        assert cfg.llm.api_key == "test-key"
        assert cfg.llm.base_url == "https://example.com/v1"
        assert cfg.llm.model == "gpt-4"

        Path(f.name).unlink()

    def test_legacy_whisper_config(self):
        """兼容旧的 [whisper] 配置节"""
        toml = """
[whisper]
device = "cpu"
"""
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False)
        f.write(toml)
        f.close()

        cfg = load_config(f.name)
        assert cfg.transcriber.device == "cpu"

        Path(f.name).unlink()
