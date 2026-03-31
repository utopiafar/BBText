"""B站 URL 解析与视频 ID 转换"""

from __future__ import annotations

import re
from dataclasses import dataclass

# BV/AV 转换常量 (参考 BBDown 的 BilibiliBvConverter)
XOR_CODE = 23442827791579
MASK_CODE = (1 << 51) - 1
MAX_AID = MASK_CODE + 1
BASE = 58
ALPHABET = "FcwAPNKTMug3GV5Lj7EJnHpWsx4tb8haYeviqBz6rkCy12mUSDQX9RdoZf"

# URL 匹配正则
RE_AV = re.compile(r"av(\d+)", re.IGNORECASE)
RE_BV = re.compile(r"[Bb][Vv]1(\w+)")
RE_EP = re.compile(r"/ep(\d+)")
RE_SS = re.compile(r"/ss(\d+)")
RE_MD = re.compile(r"md(\d+)")


@dataclass
class VideoID:
    """解析后的视频 ID"""
    type: str  # "av", "ep", "bv", "md", "ss"
    id: str


def decode_bv(bvid: str) -> int:
    """BV 号转 AV 号"""
    bvid = bvid.removeprefix("BV1")
    chars = list(bvid)
    # 位置交换
    chars[0], chars[6] = chars[6], chars[0]
    chars[1], chars[4] = chars[4], chars[1]
    avid = 0
    for c in chars:
        avid = avid * BASE + ALPHABET.index(c)
    return (avid & MASK_CODE) ^ XOR_CODE


def encode_av(avid: int) -> str:
    """AV 号转 BV 号"""
    bvid = [ALPHABET[0]] * 9
    tmp = (MAX_AID | avid) ^ XOR_CODE
    for i in range(8, -1, -1):
        if tmp == 0:
            break
        bvid[i] = ALPHABET[tmp % BASE]
        tmp //= BASE
    bvid[0], bvid[6] = bvid[6], bvid[0]
    bvid[1], bvid[4] = bvid[4], bvid[1]
    return "BV1" + "".join(bvid)


def parse_url(url: str) -> VideoID | None:
    """解析各种 B 站 URL 格式，返回 VideoID"""
    # AV 号
    m = RE_AV.search(url)
    if m and "video" in url:
        return VideoID(type="av", id=m.group(1))

    # BV 号
    m = RE_BV.search(url)
    if m:
        avid = decode_bv(m.group(1))
        return VideoID(type="av", id=str(avid))

    # EP 号 (番剧)
    m = RE_EP.search(url)
    if m:
        return VideoID(type="ep", id=m.group(1))

    # SS 号 (番剧系列)
    m = RE_SS.search(url)
    if m:
        return VideoID(type="ss", id=m.group(1))

    # MD 号 (番剧媒体)
    m = RE_MD.search(url)
    if m:
        return VideoID(type="md", id=m.group(1))

    return None


def extract_key_from_url(url: str) -> str:
    """从 WBI 图片 URL 中提取 key (去掉路径和扩展名)"""
    start = url.rfind("/") + 1
    end = url.rfind(".")
    return url[start:end]
