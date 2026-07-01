"""Tests for the bbt-video skill Markdown builder."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "bbt-video"
    / "scripts"
    / "build_doc_markdown.py"
)

spec = importlib.util.spec_from_file_location("build_doc_markdown", SCRIPT_PATH)
build_doc_markdown = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(build_doc_markdown)


def test_build_doc_markdown_strips_edges():
    markdown = build_doc_markdown.build_doc_markdown(
        summary="\n### 第一章\n概要内容\n",
        refined_text="\n精校全文\n",
        title="测试标题",
        video_url="https://b23.tv/test",
        doc_title="测试标题 - 转译精校",
    )

    assert markdown == (
        "# 测试标题 - 转译精校\n\n"
        "## 概要\n\n"
        "### 第一章\n概要内容\n\n"
        "---\n\n"
        "> 原视频链接：[测试标题](https://b23.tv/test)\n\n"
        "---\n\n"
        "## 精校全文\n\n"
        "精校全文\n"
    )


def test_main_writes_output(tmp_path, capsys):
    summary = tmp_path / "summary.txt"
    refined = tmp_path / "refined.txt"
    output = tmp_path / "doc.md"

    summary.write_text("### 第一章\n概要内容", encoding="utf-8")
    refined.write_text("精校全文", encoding="utf-8")

    exit_code = build_doc_markdown.main(
        [
            "--summary",
            str(summary),
            "--refined",
            str(refined),
            "--title",
            "测试标题",
            "--doc-title",
            "测试标题 - 转译精校",
            "--url",
            "https://b23.tv/test",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert output.read_text(encoding="utf-8").startswith(
        "# 测试标题 - 转译精校\n\n## 概要\n\n### 第一章"
    )
    assert capsys.readouterr().out.strip() == str(output)


def test_build_doc_markdown_defaults_doc_title_to_video_title():
    markdown = build_doc_markdown.build_doc_markdown(
        summary="概要",
        refined_text="全文",
        title=" 测试\n标题 ",
        video_url="https://b23.tv/test",
    )

    assert markdown.startswith("# 测试 标题\n\n")
