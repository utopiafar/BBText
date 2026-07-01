#!/usr/bin/env python3
"""Build the local Markdown file used for Feishu publication."""

from __future__ import annotations

import argparse
from pathlib import Path


def _one_line(text: str) -> str:
    return " ".join(text.strip().split())


def build_doc_markdown(
    summary: str,
    refined_text: str,
    title: str,
    video_url: str,
    doc_title: str | None = None,
) -> str:
    """Return the complete Markdown body for the Feishu document."""
    summary = summary.strip()
    refined_text = refined_text.strip()
    title = _one_line(title)
    doc_title = _one_line(doc_title or title)
    video_url = video_url.strip()

    return (
        f"# {doc_title}\n\n"
        "## 概要\n\n"
        f"{summary}\n\n"
        "---\n\n"
        f"> 原视频链接：[{title}]({video_url})\n\n"
        "---\n\n"
        "## 精校全文\n\n"
        f"{refined_text}\n"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the local Markdown file used for Feishu publication.",
    )
    parser.add_argument("--summary", required=True, help="Path to the summary text/Markdown file.")
    parser.add_argument("--refined", required=True, help="Path to the refined transcript file.")
    parser.add_argument("--title", required=True, help="Video title for the source link.")
    parser.add_argument(
        "--doc-title",
        help="Feishu document title. Defaults to the video title.",
    )
    parser.add_argument("--url", required=True, help="Original Bilibili video URL.")
    parser.add_argument("--output", required=True, help="Output Markdown path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = Path(args.summary).read_text(encoding="utf-8")
    refined_text = Path(args.refined).read_text(encoding="utf-8")
    output_path = Path(args.output)

    doc_markdown = build_doc_markdown(
        summary=summary,
        refined_text=refined_text,
        title=args.title,
        video_url=args.url,
        doc_title=args.doc_title,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(doc_markdown, encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
