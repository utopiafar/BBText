"""测试 Whisper 引擎工具函数"""

from bbt.transcriber.whisper_engine import format_srt_time


class TestFormatSrtTime:
    """SRT 时间格式化测试"""

    def test_zero(self):
        assert format_srt_time(0) == "00:00:00,000"

    def test_simple_seconds(self):
        assert format_srt_time(5.5) == "00:00:05,500"

    def test_minutes(self):
        assert format_srt_time(125.123) == "00:02:05,123"

    def test_hours(self):
        assert format_srt_time(3661.0) == "01:01:01,000"

    def test_milliseconds(self):
        assert format_srt_time(0.001) == "00:00:00,001"
