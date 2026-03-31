"""B站音频下载器"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from .api import AudioTrack, BilibiliClient, PageInfo, VideoID, VideoInfo
from .parser import parse_url

logger = logging.getLogger("bbt.bilibili")


def sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符"""
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


@dataclass
class DownloadResult:
    """下载结果"""
    files: list[Path]
    video_info: VideoInfo | None = None


class BilibiliDownloader:
    """B站音频下载器"""

    def __init__(self, client: BilibiliClient):
        self.client = client

    def resolve_and_download(
        self,
        url: str,
        output_dir: str = "output",
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> DownloadResult:
        """解析 URL 并下载所有分 P 的音频

        Args:
            url: B站视频 URL
            output_dir: 输出目录
            progress_callback: 进度回调 (stage, progress)

        Returns:
            DownloadResult
        """
        # 处理 b23.tv 短链接
        if "b23.tv" in url:
            url = self._resolve_short_url(url)

        # 解析视频 ID
        video_id = parse_url(url)
        if video_id is None:
            raise ValueError(f"无法解析 URL: {url}")

        logger.info("解析到视频 ID: %s=%s", video_id.type, video_id.id)

        # 获取视频信息
        if progress_callback:
            progress_callback("获取视频信息...", 0.0)

        info = self.client.get_video_info(video_id)
        logger.info("视频标题: %s, 分P数: %d", info.title, len(info.pages))

        # 确定番剧 ep_id
        ep_id = video_id.id if video_id.type == "ep" else ""

        # 创建输出目录
        safe_title = sanitize_filename(info.title)
        video_dir = Path(output_dir) / safe_title
        video_dir.mkdir(parents=True, exist_ok=True)

        # 下载每个分 P
        downloaded: list[Path] = []
        total_pages = len(info.pages)

        for i, page in enumerate(info.pages):
            page_progress_base = i / total_pages
            page_progress_scale = 1.0 / total_pages

            if progress_callback:
                progress_callback(
                    f"处理 P{page.page}/{total_pages}: {page.title}",
                    page_progress_base,
                )

            # 获取音频流
            tracks = self.client.get_audio_tracks(info.aid, str(page.cid), ep_id=ep_id)
            best = self.client.select_best_audio(tracks)

            if best is None:
                logger.warning("P%d 没有可用的音频流，跳过", page.page)
                continue

            logger.info(
                "P%d: 选中音频 %s (%s, %dkbps)",
                page.page, best.quality, best.codec, best.bandwidth,
            )

            # 确定文件名和扩展名
            is_muxed = best.id == "durl"  # 合流格式
            ext = "mp4" if is_muxed else "m4a"
            if best.codec == "FLAC":
                ext = "flac"
            elif best.codec == "E-AC-3":
                ext = "ec3"

            if total_pages == 1:
                filename = f"{safe_title}.{ext}"
            else:
                filename = f"{safe_title}_P{page.page}_{sanitize_filename(page.title)}.{ext}"

            output_path = video_dir / filename

            # 下载
            self._download_file(
                best.url,
                output_path,
                progress_callback=lambda stage, p: progress_callback(
                    stage, page_progress_base + p * page_progress_scale
                ) if progress_callback else None,
            )

            # 如果是合流格式（FLV/MP4），用 ffmpeg 提取纯音频
            if is_muxed:
                audio_only_path = output_path.with_suffix(".m4a")
                cmd = [
                    "ffmpeg", "-y", "-i", str(output_path),
                    "-vn", "-acodec", "aac", "-ar", "44100",
                    str(audio_only_path),
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    output_path.unlink()
                    output_path = audio_only_path
                    logger.info("P%d 已提取音频: %s", page.page, audio_only_path)
                else:
                    logger.warning("ffmpeg 提取音频失败: %s", result.stderr[:200])

            downloaded.append(output_path)
            logger.info("P%d 下载完成: %s", page.page, output_path)

        return DownloadResult(files=downloaded, video_info=info)

    def _resolve_short_url(self, url: str) -> str:
        """解析 b23.tv 短链接"""
        try:
            resp = requests.head(url, allow_redirects=True, timeout=10)
            resolved = resp.url
            logger.info("短链接解析: %s -> %s", url, resolved)
            return resolved
        except Exception as e:
            raise ValueError(f"短链接解析失败: {e}") from e

    def _download_file(
        self,
        url: str,
        output_path: Path,
        progress_callback: Callable[[str, float], None] | None = None,
        chunk_size: int = 8192,
    ) -> None:
        """流式下载文件"""
        headers = {
            "Referer": "https://www.bilibili.com/",
        }

        resp = self.client.session.get(url, headers=headers, stream=True)
        resp.raise_for_status()

        total = int(resp.headers.get("content-length", 0))
        downloaded = 0

        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0 and progress_callback:
                        progress_callback("下载中...", downloaded / total)

        if progress_callback:
            progress_callback("下载完成", 1.0)
