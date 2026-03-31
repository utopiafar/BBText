#!/usr/bin/env python3
"""将文本文件按大小切分为多块，每块不超过指定字节数，按段落边界切分。

用法:
    python split_chunks.py <text_file> [max_bytes]

参数:
    text_file   要切分的文本文件路径
    max_bytes   每块最大字节数 (默认 30000)

输出:
    将切分后的块依次写入临时文件，每行打印一个临时文件路径。
    用法示例:
        python split_chunks.py input.txt 30000 | while read chunk; do
            lark-cli docs +update --mode append --doc "$DOC_ID" --markdown "$(<"$chunk")"
        done
"""

import sys
import tempfile
from pathlib import Path


def split_chunks(text: str, max_bytes: int = 30000) -> list[str]:
    """按段落边界将文本切分为多块，每块不超过 max_bytes。

    优先在双换行（段落边界）处切分，如果单段超过限制则在换行处切分。
    """
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        para_bytes = len(para.encode("utf-8"))
        sep_bytes = 2 if current else 0  # \n\n 分隔符
        current_bytes = len(current.encode("utf-8"))

        if current_bytes + sep_bytes + para_bytes <= max_bytes:
            current = current + "\n\n" + para if current else para
        else:
            if current:
                chunks.append(current)
            # 单段超过限制，按行再拆
            if para_bytes > max_bytes:
                lines = para.split("\n")
                current = ""
                for line in lines:
                    line_bytes = len(line.encode("utf-8"))
                    sep = 1 if current else 0
                    if len(current.encode("utf-8")) + sep + line_bytes <= max_bytes:
                        current = current + "\n" + line if current else line
                    else:
                        if current:
                            chunks.append(current)
                        current = line
                # current 保留给下一轮
            else:
                current = para

    if current:
        chunks.append(current)

    return chunks


def main():
    if len(sys.argv) < 2:
        print("用法: python split_chunks.py <text_file> [max_bytes]", file=sys.stderr)
        sys.exit(1)

    text_path = sys.argv[1]
    max_bytes = int(sys.argv[2]) if len(sys.argv) > 2 else 30000
    text = Path(text_path).read_text(encoding="utf-8")

    chunks = split_chunks(text, max_bytes)

    # 写入临时文件，每行输出一个路径
    for i, chunk in enumerate(chunks):
        fd, path = tempfile.mkstemp(suffix=f"_chunk{i}.txt", prefix="bbt_")
        with open(fd, "w", encoding="utf-8") as f:
            f.write(chunk)
        print(path)


if __name__ == "__main__":
    main()
