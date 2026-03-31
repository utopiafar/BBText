#!/usr/bin/env python3
"""SRT 字幕文件转纯文本 - 去除序号和时间戳，保留正文"""

import re
import sys
from pathlib import Path


def srt_to_text(srt_path: str) -> str:
    """读取 SRT 文件，提取纯文本内容。

    - 去除序号行和时间戳行
    - 将 || 段落分隔标记转为空行
    - 合并连续空行
    """
    content = Path(srt_path).read_text(encoding="utf-8")
    blocks = re.split(r"\n\n+", content.strip())

    text_parts = []
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue

        # 跳过序号行（第1行）和时间戳行（第2行），取正文
        text_lines = lines[2:]
        text = "\n".join(text_lines).strip()

        # 将 || 段落分隔标记转为换行
        text = text.replace("||", "\n\n")
        text_parts.append(text)

    # 合并所有段落，清理多余空行
    full_text = "\n".join(text_parts)
    full_text = re.sub(r"\n{3,}", "\n\n", full_text)
    return full_text.strip()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python srt_to_text.py <srt_file_path>", file=sys.stderr)
        sys.exit(1)

    result = srt_to_text(sys.argv[1])
    print(result)
