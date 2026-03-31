"""测试 SRT 解析和生成"""

import tempfile
from pathlib import Path

from bbt.llm.client import parse_srt, write_srt


class TestSrtParsing:
    """SRT 文件解析测试"""

    def _write_srt(self, content: str) -> Path:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False, encoding="utf-8")
        f.write(content)
        f.close()
        return Path(f.name)

    def test_basic_parse(self):
        srt = """1
00:00:01,000 --> 00:00:03,000
你好世界

2
00:00:04,000 --> 00:00:06,000
这是一个测试

"""
        path = self._write_srt(srt)
        entries = parse_srt(path)
        assert len(entries) == 2
        assert entries[0][3] == "你好世界"
        assert entries[1][3] == "这是一个测试"
        path.unlink()

    def test_roundtrip(self):
        entries = [
            (1, "00:00:01,000", "00:00:03,000", "第一句"),
            (2, "00:00:04,000", "00:00:06,500", "第二句"),
            (3, "00:00:07,000", "00:00:10,000", "第三句"),
        ]
        f = tempfile.NamedTemporaryFile(suffix=".srt", delete=False)
        f.close()
        path = Path(f.name)

        write_srt(entries, path)
        parsed = parse_srt(path)

        assert len(parsed) == 3
        for i, (idx, start, end, text) in enumerate(parsed):
            assert text == entries[i][3]
            assert start == entries[i][1]
            assert end == entries[i][2]

        path.unlink()
