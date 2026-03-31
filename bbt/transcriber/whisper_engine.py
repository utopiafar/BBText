"""SenseVoice (sherpa-onnx) 语音转写引擎 - 输出 SRT 字幕"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Callable

import numpy as np

logger = logging.getLogger("bbt.transcriber")

# 模型下载地址
MODEL_BASE_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models"
MODEL_NAME = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
VAD_MODEL_NAME = "silero_vad.onnx"

# TypeNo 项目使用的 int8 变体模型名
TYPENO_MODEL_NAME = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"

SAMPLE_RATE = 16000


def _get_model_dir() -> Path:
    """获取模型目录，优先使用 TypeNo 已有模型，不存在则自动下载"""
    # 1. 优先检查 BBText 自己的缓存
    bbt_model_dir = Path.home() / ".cache" / "bbt" / MODEL_NAME
    if bbt_model_dir.exists():
        return bbt_model_dir

    # 2. 检查 TypeNo 项目的模型（共享复用）
    typeno_model_dir = Path.home() / ".coli" / "models" / TYPENO_MODEL_NAME
    if typeno_model_dir.exists():
        logger.info("复用 TypeNo 模型: %s", typeno_model_dir)
        return typeno_model_dir

    logger.info("首次使用，下载 SenseVoice 模型...")
    import tarfile
    import urllib.request

    cache_dir = Path.home() / ".cache" / "bbt"
    cache_dir.mkdir(parents=True, exist_ok=True)

    tar_url = f"{MODEL_BASE_URL}/{MODEL_NAME}.tar.bz2"
    tar_path = cache_dir / f"{MODEL_NAME}.tar.bz2"

    logger.info("下载: %s", tar_url)
    urllib.request.urlretrieve(tar_url, str(tar_path))

    logger.info("解压模型...")
    with tarfile.open(tar_path, "r:bz2") as tar:
        tar.extractall(cache_dir)

    tar_path.unlink()
    logger.info("模型下载完成: %s", bbt_model_dir)
    return bbt_model_dir


def _get_vad_model() -> Path:
    """获取 VAD 模型，优先使用 TypeNo 已有模型，不存在则自动下载"""
    # 1. 检查 BBText 缓存
    vad_path = Path.home() / ".cache" / "bbt" / VAD_MODEL_NAME
    if vad_path.exists():
        return vad_path

    # 2. 检查 TypeNo 项目的 VAD 模型
    typeno_vad = Path.home() / ".coli" / "models" / VAD_MODEL_NAME
    if typeno_vad.exists():
        logger.info("复用 TypeNo VAD 模型: %s", typeno_vad)
        return typeno_vad

    import urllib.request

    cache_dir = Path.home() / ".cache" / "bbt"
    cache_dir.mkdir(parents=True, exist_ok=True)

    vad_url = f"{MODEL_BASE_URL}/{VAD_MODEL_NAME}"
    logger.info("下载 VAD 模型: %s", vad_url)
    urllib.request.urlretrieve(vad_url, str(vad_path))
    logger.info("VAD 模型下载完成")
    return vad_path


def format_srt_time(seconds: float) -> str:
    """将秒数格式化为 SRT 时间格式 HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def transcribe_audio(
    audio_path: str | Path,
    output_srt: str | Path | None = None,
    model_name: str = "sense-voice",
    device: str = "cpu",
    compute_type: str = "int8",
    language: str = "zh",
    beam_size: int = 5,
    vad_filter: bool = True,
    progress_callback: Callable[[str, float], None] | None = None,
    fmt: str = "srt",
    timestamps: bool = True,
) -> Path:
    """使用 SenseVoice (sherpa-onnx) 转写音频文件并生成 SRT 字幕

    Args:
        audio_path: 输入音频文件路径
        output_srt: 输出 SRT 文件路径（默认与音频同名）
        progress_callback: 进度回调
        其余参数为兼容接口，暂不使用

    Returns:
        生成的 SRT 文件路径
    """
    import sherpa_onnx

    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")

    if output_srt is None:
        suffix = ".srt" if fmt == "srt" else ".txt"
        output_srt = audio_path.with_suffix(suffix)
    output_srt = Path(output_srt)

    # 下载模型
    if progress_callback:
        progress_callback("准备模型...", 0.0)

    model_dir = _get_model_dir()
    vad_model = _get_vad_model()

    model_file = model_dir / "model.int8.onnx"
    if not model_file.exists():
        model_file = model_dir / "model.onnx"
    tokens_file = model_dir / "tokens.txt"

    # 确定推理 provider
    provider = "coreml" if device != "cpu" else "cpu"
    logger.info("使用推理设备: %s (provider=%s)", device, provider)

    # 创建识别器
    recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(model_file),
        tokens=str(tokens_file),
        num_threads=4,
        use_itn=True,
        provider=provider,
        debug=False,
    )

    # VAD 配置
    vad_config = sherpa_onnx.VadModelConfig()
    vad_config.silero_vad.model = str(vad_model)
    vad_config.silero_vad.threshold = 0.2
    vad_config.silero_vad.min_silence_duration = 0.5
    vad_config.silero_vad.min_speech_duration = 0.25
    vad_config.silero_vad.max_speech_duration = 60.0  # SenseVoice 支持长段
    vad_config.sample_rate = SAMPLE_RATE
    window_size = vad_config.silero_vad.window_size

    # 用 ffmpeg 管道读音频
    if progress_callback:
        progress_callback("转写中...", 0.05)

    logger.info("开始转写: %s (SenseVoice)", audio_path.name)

    ffmpeg_cmd = [
        "ffmpeg", "-i", str(audio_path),
        "-f", "s16le", "-acodec", "pcm_s16le",
        "-ac", "1", "-ar", str(SAMPLE_RATE),
        "-",
    ]
    process = subprocess.Popen(
        ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )

    frames_per_read = SAMPLE_RATE * 100  # 100 秒一读
    vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=300)

    segments = []
    buffer: list[np.ndarray] = []
    num_processed = 0

    while True:
        data = process.stdout.read(frames_per_read * 2)  # int16 = 2 bytes
        if not data:
            vad.flush()
            break

        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768
        num_processed += len(samples)
        buffer.append(samples)
        buf = np.concatenate(buffer)
        buffer.clear()

        while len(buf) > window_size:
            vad.accept_waveform(buf[:window_size])
            buf = buf[window_size:]

        # 处理 VAD 检测到的语音段
        if not vad.empty():
            _process_vad_segments(vad, recognizer, segments)

        # 留下未处理的
        if len(buf) > 0:
            buffer.append(buf)

        if progress_callback:
            total_duration = num_processed / SAMPLE_RATE
            progress_callback(f"转写中... ({total_duration:.0f}s)", 0.1)

    # 处理 buffer 中剩余
    if buffer:
        buf = np.concatenate(buffer)
        if len(buf) > 0:
            vad.accept_waveform(buf)
        vad.flush()

    _process_vad_segments(vad, recognizer, segments)

    process.stdout.close()
    process.wait()

    # 写入输出文件
    _write_output(segments, output_srt, fmt=fmt, timestamps=timestamps)

    if progress_callback:
        progress_callback("转写完成", 1.0)

    logger.info("字幕已保存: %s (%d 条)", output_srt, len(segments))
    return output_srt


def _process_vad_segments(
    vad: "sherpa_onnx.VoiceActivityDetector",
    recognizer: "sherpa_onnx.OfflineRecognizer",
    segments: list[tuple[float, float, str]],
) -> None:
    """处理 VAD 检测到的语音段，识别后加入 segments"""
    while not vad.empty():
        chunk = vad.front
        start = chunk.start / SAMPLE_RATE
        duration = len(chunk.samples) / SAMPLE_RATE
        text = ""

        stream = recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, chunk.samples)
        recognizer.decode_stream(stream)
        text = stream.result.text.strip()

        if text and text != ".":
            segments.append((start, duration, text))

        vad.pop()


def _write_output(
    segments: list[tuple[float, float, str]],
    output_path: Path,
    fmt: str = "srt",
    timestamps: bool = True,
) -> None:
    """将 segments 写入字幕文件"""
    with open(output_path, "w", encoding="utf-8") as f:
        for i, (start, duration, text) in enumerate(segments, 1):
            end = start + duration
            if not timestamps:
                # 无时间戳：只写纯文本
                f.write(f"{text}\n\n")
            elif fmt == "srt":
                # SRT 格式
                f.write(f"{i}\n")
                f.write(f"{format_srt_time(start)} --> {format_srt_time(end)}\n")
                f.write(f"{text}\n\n")

