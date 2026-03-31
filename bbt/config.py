"""配置管理模块"""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    pass
else:
    try:
        import tomllib  # type: ignore[no-redef]
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]


@dataclass
class BilibiliConfig:
    cookie: str = ""


@dataclass
class TranscriberConfig:
    device: str = "coreml"  # "coreml" (Apple Silicon), "cuda" (NVIDIA GPU), "cpu"


@dataclass
class LLMConfig:
    api_key: str = ""
    base_url: str = "https://api.moonshot.ai/v1"
    model: str = "kimi-k2.5"
    provider: str = "openai"  # "openai" 或 "anthropic"


@dataclass
class OutputConfig:
    dir: str = "output"
    format: str = "srt"  # "srt" 或 "txt"
    timestamps: bool = True  # 是否带时间戳


@dataclass
class FeishuConfig:
    folder_token: str = ""  # 飞书云空间文件夹 token，用于保存文档
    user_id: str = ""       # 飞书用户 open_id，用于发送通知


@dataclass
class AppConfig:
    bilibili: BilibiliConfig = field(default_factory=BilibiliConfig)
    transcriber: TranscriberConfig = field(default_factory=TranscriberConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    feishu: FeishuConfig = field(default_factory=FeishuConfig)


def find_config_path() -> Path:
    """查找配置文件路径，优先级：当前目录 > 包目录"""
    candidates = [
        Path.cwd() / "config.toml",
        Path(__file__).parent.parent / "config.toml",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """加载配置文件"""
    if config_path is None:
        config_path = find_config_path()
    else:
        config_path = Path(config_path)

    cfg = AppConfig()

    if not config_path.exists():
        return cfg

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    if "bilibili" in raw:
        b = raw["bilibili"]
        cfg.bilibili.cookie = b.get("cookie", cfg.bilibili.cookie)

    if "transcriber" in raw:
        t = raw["transcriber"]
        cfg.transcriber.device = t.get("device", cfg.transcriber.device)
    elif "whisper" in raw:  # 兼容旧配置
        w = raw["whisper"]
        cfg.transcriber.device = w.get("device", cfg.transcriber.device)

    if "llm" in raw:
        l = raw["llm"]
        cfg.llm.api_key = l.get("api_key", cfg.llm.api_key)
        cfg.llm.base_url = l.get("base_url", cfg.llm.base_url)
        cfg.llm.model = l.get("model", cfg.llm.model)
        cfg.llm.provider = l.get("provider", cfg.llm.provider)

    if "output" in raw:
        o = raw["output"]
        cfg.output.dir = o.get("dir", cfg.output.dir)
        cfg.output.format = o.get("format", cfg.output.format)
        cfg.output.timestamps = o.get("timestamps", cfg.output.timestamps)

    if "feishu" in raw:
        f = raw["feishu"]
        cfg.feishu.folder_token = f.get("folder_token", cfg.feishu.folder_token)
        cfg.feishu.user_id = f.get("user_id", cfg.feishu.user_id)

    # 环境变量覆盖
    env_key = os.environ.get("BBT_LLM_API_KEY")
    if env_key:
        cfg.llm.api_key = env_key

    return cfg
