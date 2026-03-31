"""Bilibili API 客户端 - WBI 签名、视频信息获取、播放地址解析"""

from __future__ import annotations

import hashlib
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlencode

import requests

from .parser import VideoID, decode_bv, extract_key_from_url

logger = logging.getLogger("bbt.bilibili")

# WBI 混淆表
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
]

AUDIO_QUALITY_PRIORITY = ["30251", "30250", "30232", "30280", "30216"]

AUDIO_QUALITY_NAMES = {
    "30216": "64K M4A",
    "30232": "132K M4A",
    "30250": "192K M4A",
    "30251": "Hi-Res FLAC",
    "30280": "杜比全景声",
}

CODEC_MAP = {
    "mp4a.40.2": "M4A",
    "mp4a.40.5": "M4A",
    "ec-3": "E-AC-3",
    "fLaC": "FLAC",
}


@dataclass
class AudioTrack:
    """音频流信息"""
    id: str
    quality: str
    bandwidth: int  # kbps
    codec: str
    duration: int  # seconds
    url: str


@dataclass
class PageInfo:
    """视频分 P 信息"""
    page: int
    cid: int
    title: str
    duration: int  # seconds


@dataclass
class VideoInfo:
    """视频元信息"""
    aid: str
    bvid: str
    title: str
    owner: str
    pages: list[PageInfo] = field(default_factory=list)


def _get_mixin_key(orig: str) -> str:
    """生成 32 字符 WBI mixin key"""
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB)


def _wbi_sign(params_str: str, wbi_key: str) -> str:
    """对请求参数进行 WBI 签名"""
    sign = hashlib.md5((params_str + wbi_key).encode()).hexdigest()
    return f"{params_str}&w_rid={sign}"


def _random_ua() -> str:
    """生成随机 User-Agent"""
    chrome_ver = random.randint(100, 131)
    return (
        f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome_ver}.0.0.0 Safari/537.36"
    )


class BilibiliClient:
    """B站 API 客户端"""

    def __init__(self, cookie: str = ""):
        self.cookie = cookie
        self.wbi_key: str | None = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": _random_ua(),
            "Referer": "https://www.bilibili.com/",
            "Accept-Encoding": "gzip, deflate",
        })
        if cookie:
            self.session.headers["Cookie"] = cookie

    def _ensure_wbi(self) -> None:
        """确保 WBI key 已初始化"""
        if self.wbi_key is not None:
            return

        resp = self.session.get("https://api.bilibili.com/x/web-interface/nav")
        resp.raise_for_status()
        data = resp.json()

        if data["code"] != 0:
            logger.warning("WBI key 获取失败，部分请求可能不受影响: %s", data.get("message"))
            return

        wbi_img = data["data"]["wbi_img"]
        img_key = extract_key_from_url(wbi_img["img_url"])
        sub_key = extract_key_from_url(wbi_img["sub_url"])
        self.wbi_key = _get_mixin_key(img_key + sub_key)
        logger.debug("WBI key 初始化成功")

    def get_video_info(self, video_id: VideoID) -> VideoInfo:
        """获取视频元信息"""
        self._ensure_wbi()

        if video_id.type == "av":
            return self._get_video_info_by_aid(video_id.id)
        elif video_id.type == "ep":
            return self._get_video_info_by_ep(video_id.id)
        elif video_id.type == "ss":
            return self._get_video_info_by_ss(video_id.id)
        elif video_id.type == "md":
            return self._get_video_info_by_md(video_id.id)
        else:
            raise ValueError(f"不支持的视频 ID 类型: {video_id.type}")

    def _get_video_info_by_aid(self, aid: str) -> VideoInfo:
        """通过 AV 号获取视频信息"""
        resp = self.session.get(
            "https://api.bilibili.com/x/web-interface/view",
            params={"aid": aid},
        )
        resp.raise_for_status()
        data = resp.json()["data"]

        pages = [
            PageInfo(
                page=p["page"],
                cid=p["cid"],
                title=p["part"],
                duration=p["duration"],
            )
            for p in data.get("pages", [])
        ]

        return VideoInfo(
            aid=str(data["aid"]),
            bvid=data["bvid"],
            title=data["title"],
            owner=data["owner"]["name"],
            pages=pages,
        )

    def _get_video_info_by_ep(self, ep_id: str) -> VideoInfo:
        """通过 EP 号获取番剧视频信息"""
        resp = self.session.get(
            "https://api.bilibili.com/pgc/view/web/season",
            params={"ep_id": ep_id},
        )
        resp.raise_for_status()
        result = resp.json()["result"]

        # 找到对应的 episode
        target_ep = None
        for ep in result.get("episodes", []):
            if str(ep["id"]) == ep_id:
                target_ep = ep
                break

        if target_ep is None and result.get("episodes"):
            target_ep = result["episodes"][0]

        if target_ep is None:
            raise ValueError(f"未找到 ep_id={ep_id} 对应的剧集")

        aid = str(target_ep["aid"])
        cid = str(target_ep["cid"])
        title = target_ep.get("long_title") or target_ep.get("index_title") or target_ep.get("index", "")
        ep_index = target_ep.get("index", "1")

        pages = [PageInfo(page=1, cid=int(cid), title=title, duration=target_ep.get("duration", 0) // 1000)]

        return VideoInfo(
            aid=aid,
            bvid=target_ep.get("bvid", ""),
            title=f"{result.get('title', '')} - 第{ep_index}话 {title}",
            owner=result.get("jp_title", result.get("title", "")),
            pages=pages,
        )

    def _get_video_info_by_ss(self, ss_id: str) -> VideoInfo:
        """通过 SS 号获取番剧信息，默认取第一集"""
        resp = self.session.get(
            "https://api.bilibili.com/pgc/view/web/season",
            params={"season_id": ss_id},
        )
        resp.raise_for_status()
        result = resp.json()["result"]

        episodes = result.get("episodes", [])
        if not episodes:
            raise ValueError(f"番剧 ss{ss_id} 没有可用剧集")

        ep = episodes[0]
        return VideoInfo(
            aid=str(ep["aid"]),
            bvid=ep.get("bvid", ""),
            title=f"{result['title']} - 第{ep.get('index', '1')}话",
            owner=result.get("title", ""),
            pages=[PageInfo(page=1, cid=ep["cid"], title=ep.get("long_title", ""), duration=ep.get("duration", 0) // 1000)],
        )

    def _get_video_info_by_md(self, md_id: str) -> VideoInfo:
        """通过 MD 号获取番剧信息"""
        resp = self.session.get(
            "https://api.bilibili.com/pgc/review/user",
            params={"media_id": md_id},
        )
        resp.raise_for_status()
        result = resp.json()["result"]
        ep_id = result["media"]["new_ep"]["id"]
        return self._get_video_info_by_ep(str(ep_id))

    def get_audio_tracks(self, aid: str, cid: str, ep_id: str = "") -> list[AudioTrack]:
        """获取音频流列表"""
        self._ensure_wbi()

        bangumi = bool(ep_id)
        if bangumi:
            url = "https://api.bilibili.com/pgc/player/web/v2/playurl"
        else:
            url = "https://api.bilibili.com/x/player/wbi/playurl"

        # 构建参数
        params = (
            f"support_multi_audio=true&from_client=BROWSER"
            f"&avid={aid}&cid={cid}&fnval=4048&fnver=0&fourk=1"
            f"&otype=json&qn=0"
        )

        if bangumi:
            params += f"&module=bangumi&ep_id={ep_id}&session="

        if not self.cookie:
            params += "&try_look=1"

        params += f"&wts={int(time.time())}"

        if not bangumi and self.wbi_key:
            signed = _wbi_sign(params, self.wbi_key)
            resp = self.session.get(f"{url}?{signed}")
        else:
            resp = self.session.get(f"{url}?{params}")

        resp.raise_for_status()
        json_data = resp.json()

        return self._parse_audio_tracks(json_data)

    def _parse_audio_tracks(self, json_data: dict) -> list[AudioTrack]:
        """从播放地址响应中解析音频流"""
        tracks: list[AudioTrack] = []

        data = json_data.get("data") or json_data.get("result", {})
        dash = data.get("dash") or data.get("video_info", {}).get("dash", {})

        if not dash:
            # 回退：FLV/MP4 合流格式，取第一个 durl
            durl = data.get("durl", [])
            if durl:
                url = durl[0].get("url", "")
                duration = data.get("timelength", 0) // 1000
                if url:
                    logger.info("使用 FLV/MP4 合流格式，后续将通过 ffmpeg 提取音频")
                    tracks.append(AudioTrack(
                        id="durl",
                        quality="合流音频",
                        bandwidth=0,
                        codec="MP4",
                        duration=duration,
                        url=url,
                    ))
            else:
                logger.warning("未找到任何可用的音视频流")
            return tracks

        duration = dash.get("duration", 0)

        # 普通音频流
        for node in dash.get("audio", []):
            tracks.append(self._make_track(node, duration))

        # 杜比音频
        dolby = dash.get("dolby", {})
        if dolby and dolby.get("audio"):
            for node in dolby["audio"]:
                tracks.append(self._make_track(node, duration))

        # Hi-Res 无损
        flac = dash.get("flac", {})
        if flac and flac.get("audio"):
            tracks.append(self._make_track(flac["audio"], duration))

        return tracks

    def _make_track(self, node: dict, duration: int) -> AudioTrack:
        """从 JSON 节点创建 AudioTrack"""
        audio_id = str(node["id"])
        codecs = CODEC_MAP.get(node.get("codecs", ""), node.get("codecs", ""))

        # 选择最优 URL（跳过 PCDN 带端口地址）
        urls = [node["base_url"]] + node.get("backup_url", [])
        best_url = node["base_url"]
        for u in urls:
            if u and ":" not in u.split("//")[1].split("/")[0]:
                best_url = u
                break

        return AudioTrack(
            id=audio_id,
            quality=AUDIO_QUALITY_NAMES.get(audio_id, audio_id),
            bandwidth=node.get("bandwidth", 0) // 1000,
            codec=codecs,
            duration=duration,
            url=best_url,
        )

    def select_best_audio(self, tracks: list[AudioTrack]) -> AudioTrack | None:
        """按优先级选择最优音频流"""
        if not tracks:
            return None

        # 按预设优先级排序
        for preferred_id in AUDIO_QUALITY_PRIORITY:
            for t in tracks:
                if t.id == preferred_id:
                    return t

        # 回退：按带宽排序
        return max(tracks, key=lambda t: t.bandwidth)
