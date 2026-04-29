"""Tests for transcriber provider selection."""

from bbt.transcriber.whisper_engine import _select_provider


def test_select_provider_cpu():
    assert _select_provider("cpu", ["CPUExecutionProvider"]) == "cpu"


def test_select_provider_coreml_when_available():
    assert _select_provider("coreml", ["CoreMLExecutionProvider", "CPUExecutionProvider"]) == "coreml"


def test_select_provider_coreml_falls_back_to_cpu():
    assert _select_provider("coreml", ["CPUExecutionProvider"]) == "cpu"


def test_select_provider_cuda_when_available():
    assert _select_provider("cuda", ["CUDAExecutionProvider", "CPUExecutionProvider"]) == "cuda"


def test_select_provider_cuda_falls_back_to_cpu():
    assert _select_provider("cuda", ["CoreMLExecutionProvider", "CPUExecutionProvider"]) == "cpu"


def test_select_provider_auto_prefers_cuda():
    assert _select_provider("auto", ["CUDAExecutionProvider", "CoreMLExecutionProvider", "CPUExecutionProvider"]) == "cuda"


def test_select_provider_auto_uses_coreml_before_cpu():
    assert _select_provider("auto", ["CoreMLExecutionProvider", "CPUExecutionProvider"]) == "coreml"


def test_select_provider_unknown_falls_back_to_cpu():
    assert _select_provider("metal", ["CoreMLExecutionProvider", "CPUExecutionProvider"]) == "cpu"
