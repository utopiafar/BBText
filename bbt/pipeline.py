"""Pipeline 编排 - 串联下载、转写、修正、总结"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import AppConfig
from .bilibili.api import BilibiliClient
from .bilibili.downloader import BilibiliDownloader, DownloadResult
from .llm.client import LLMClient
from .transcriber.whisper_engine import transcribe_audio

logger = logging.getLogger("bbt.pipeline")


@dataclass
class PipelineResult:
    """Pipeline 执行结果"""
    audio_files: list[Path] = field(default_factory=list)
    srt_files: list[Path] = field(default_factory=list)
    refined_srt_files: list[Path] = field(default_factory=list)
    summary_files: list[Path] = field(default_factory=list)
    video_title: str = ""
    video_description: str = ""


class Pipeline:
    """全流程编排器"""

    def __init__(self, config: AppConfig):
        self.config = config

    def run(
        self,
        url: str,
        skip_download: bool = False,
        skip_transcribe: bool = False,
        skip_refine: bool = False,
        skip_summarize: bool = False,
        audio_file: str | None = None,
        srt_file: str | None = None,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> PipelineResult:
        result = PipelineResult()
        stages = self._count_stages(skip_download, skip_transcribe, skip_refine, skip_summarize)
        stage_weight = 1.0 / stages if stages > 0 else 1.0
        current_stage = 0

        def stage_progress(msg: str, p: float) -> None:
            if progress_callback:
                overall = (current_stage + p) * stage_weight
                progress_callback(msg, min(overall, 1.0))

        # Stage 1: 下载
        if not skip_download:
            current_stage = 0
            logger.info("=== 阶段 1: 下载音频 ===")
            client = BilibiliClient(cookie=self.config.bilibili.cookie)
            downloader = BilibiliDownloader(client)
            dl_result = downloader.resolve_and_download(
                url, output_dir=self.config.output.dir, progress_callback=stage_progress,
            )
            result.audio_files = dl_result.files
            if not result.audio_files:
                raise RuntimeError("音频下载失败，未获得任何音频文件")
            if dl_result.video_info:
                result.video_title = dl_result.video_info.title
                result.video_description = getattr(dl_result.video_info, 'desc', '')

        elif audio_file:
            result.audio_files = [Path(audio_file)]

        # Stage 2: 转写
        if not skip_transcribe:
            current_stage = 1
            logger.info("=== 阶段 2: 语音转写 ===")
            for audio_path in result.audio_files:
                srt_path = transcribe_audio(
                    audio_path,
                    device=self.config.transcriber.device,
                    num_threads=self.config.transcriber.num_threads,
                    fmt=self.config.output.format,
                    timestamps=self.config.output.timestamps,
                    progress_callback=stage_progress,
                )
                result.srt_files.append(srt_path)

        elif srt_file:
            result.srt_files = [Path(srt_file)]

        # Stage 3: LLM 字幕纠错
        if not skip_refine and self.config.llm.api_key and result.srt_files:
            current_stage = 2
            logger.info("=== 阶段 3: LLM 字幕纠错 ===")
            llm = LLMClient(
                api_key=self.config.llm.api_key,
                base_url=self.config.llm.base_url,
                model=self.config.llm.model,
                provider=self.config.llm.provider,
            )
            for srt_path in result.srt_files:
                refined = llm.refine_srt(
                    srt_path,
                    title=result.video_title,
                    description=result.video_description,
                    progress_callback=stage_progress,
                )
                result.refined_srt_files.append(refined)

        elif not skip_refine and not self.config.llm.api_key:
            logger.warning("未配置 LLM API Key，跳过字幕修正")

        # Stage 4: LLM 章节概要
        if not skip_summarize and self.config.llm.api_key:
            current_stage = 3
            logger.info("=== 阶段 4: LLM 章节概要 ===")
            llm = LLMClient(
                api_key=self.config.llm.api_key,
                base_url=self.config.llm.base_url,
                model=self.config.llm.model,
                provider=self.config.llm.provider,
            )
            srt_for_summary = result.refined_srt_files or result.srt_files
            for srt_path in srt_for_summary:
                summary = llm.summarize(
                    srt_path,
                    title=result.video_title,
                    description=result.video_description,
                    progress_callback=stage_progress,
                )
                result.summary_files.append(summary)

        elif not skip_summarize and not self.config.llm.api_key:
            logger.warning("未配置 LLM API Key，跳过章节概要")

        if progress_callback:
            progress_callback("全部完成!", 1.0)

        return result

    def _count_stages(self, skip_download: bool, skip_transcribe: bool, skip_refine: bool, skip_summarize: bool) -> int:
        count = 0
        if not skip_download:
            count += 1
        if not skip_transcribe:
            count += 1
        if not skip_refine:
            count += 1
        if not skip_summarize:
            count += 1
        return max(count, 1)
