#!/usr/bin/env python3
"""BBT Video 准备脚本 — 下载音频 + 语音转写

一条命令完成 pipeline 的前两个阶段（下载+转写），
精校和概要由 Claude 在 skill 环境中直接完成。

用法:
    uv run python skills/bbt-video/scripts/publish.py "<B站视频URL>"

输出:
    全程打印日志，最后输出 JSON 汇总结果
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

sys.path.insert(0, str(PROJECT_ROOT))

from bbt.config import load_config
from bbt.pipeline import Pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bbt.publish")


def main():
    if len(sys.argv) < 2:
        print("用法: uv run python skills/bbt-video/scripts/publish.py '<B站视频URL>'")
        sys.exit(1)

    video_url = sys.argv[1]
    start_time = time.time()

    result_data = {
        "ok": False,
        "video_url": video_url,
        "video_title": "",
        "video_description": "",
        "output_dir": "",
        "srt_files": [],
        "error": "",
    }

    try:
        logger.info("=== 阶段 1/2: 运行 BBText Pipeline (下载+转写) ===")
        config = load_config()
        pipeline = Pipeline(config)

        def progress(msg: str, pct: float) -> None:
            logger.info("[Pipeline %.0f%%] %s", pct * 100, msg)

        pipeline_result = pipeline.run(
            video_url,
            skip_refine=True,
            skip_summarize=True,
            progress_callback=progress,
        )

        video_title = pipeline_result.video_title or "未知标题"
        video_description = pipeline_result.video_description or ""
        output_dir = str(Path(config.output.dir) / video_title)

        srt_files = [str(p) for p in pipeline_result.srt_files]

        result_data["video_title"] = video_title
        result_data["video_description"] = video_description
        result_data["output_dir"] = output_dir
        result_data["srt_files"] = srt_files

        logger.info("Pipeline 完成: %s", video_title)
        logger.info("  音频文件: %d 个", len(pipeline_result.audio_files))
        logger.info("  字幕文件: %d 个", len(pipeline_result.srt_files))

        result_data["ok"] = True
        elapsed = time.time() - start_time
        logger.info("准备阶段完成! 耗时 %.1f 秒", elapsed)

    except Exception as e:
        result_data["error"] = str(e)
        logger.error("流程失败: %s", e, exc_info=True)

    # 最终输出 JSON 汇总
    print("\n" + "=" * 60)
    print("RESULT_JSON_START")
    print(json.dumps(result_data, ensure_ascii=False, indent=2))
    print("RESULT_JSON_END")


if __name__ == "__main__":
    main()
