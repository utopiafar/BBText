"""LLM 客户端 - 字幕纠错与章节概要 (OpenAI / Anthropic 兼容接口)"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable

import requests
from openai import OpenAI

logger = logging.getLogger("bbt.llm")

# ========== SRT 解析/写入工具 ==========

def parse_srt(srt_path: Path) -> list[tuple[int, str, str, str]]:
    """解析 SRT 文件，返回 [(序号, 开始时间, 结束时间, 文本), ...]"""
    content = Path(srt_path).read_text(encoding="utf-8")
    blocks = re.split(r"\n\n+", content.strip())
    entries = []
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        try:
            index = int(lines[0].strip())
            time_line = lines[1].strip()
            parts = time_line.split(" --> ")
            start_time = parts[0].strip()
            end_time = parts[1].strip()
            text = "\n".join(lines[2:]).strip()
            entries.append((index, start_time, end_time, text))
        except (ValueError, IndexError):
            continue
    return entries


def write_srt(
    entries: list[tuple[int, str, str, str]],
    output_path: Path,
    paragraph_markers: set[int] | None = None,
) -> None:
    """将字幕条目写入 SRT 文件

    Args:
        entries: [(序号, 开始时间, 结束时间, 文本), ...]
        output_path: 输出文件路径
        paragraph_markers: 需要在其后额外加空行的条目序号集合（1-based）
    """
    with open(output_path, "w", encoding="utf-8") as f:
        for i, (_, start, end, text) in enumerate(entries, 1):
            f.write(f"{i}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{text}\n")
            if paragraph_markers and i in paragraph_markers:
                f.write("\n\n")  # 段落分隔：额外空行
            else:
                f.write("\n")


# ========== Prompt 模板 ==========

REFINE_SYSTEM_PROMPT = """你是一个专业的字幕校对员。你会收到一段视频的上下文信息和一段从语音识别得到的原始字幕。
你的任务是完整地重新转写这段字幕，使其准确、通顺、符合语义，并合理分段。

规则：
1. 积极分段（最重要的规则）：在修正后的文本中，用 || 标记分段位置。|| 可以出现在文本的任何位置，不限于末尾。
   - 每个自然段落控制在1-3句话（约30-100字）
   - 分段时机：话题转换、视角切换、一个完整观点结束开启新论述、说话人停顿或语气转折、举例结束后回归主题
   - 大段密密麻麻的文字非常难以阅读，请务必积极分段
2. 根据视频标题和简介的上下文，修正语音识别中的专业名词、人名、地名等错误
3. 补全缺失的标点符号（逗号、句号、问号等），使语句完整自然
4. 如果连续几条字幕明显是同一句话被语音识别误切开的（例如上一条以"的"结尾、下一条以"程度"开头），应将它们合并为一条
5. 严格按以下格式输出，不要输出任何其他内容：
   - 单条：序号|修正后文本
   - 合并多条：起始序号-结束序号|合并后文本
   - 分段用 || 标记，如：序号|第一句。第二句。||第三句。第四句。||第五句。

示例：
输入：
1|尊敬的各位领导大家上午好
2|感谢大会的邀请很高兴有这个机会
3|2013年也是在上海我来到了陆家嘴金融峰会
4|发表了一通关于互联网金融的异想天开的观点

输出（合并了1-2和3-4，并在合适位置分段）：
1-2|尊敬的各位领导，大家上午好。感谢大会的邀请，很高兴有这个机会。||2013年也是在上海，我来到了陆家嘴金融峰会，发表了一通关于互联网金融的异想天开的观点。
3-4|七年过去了，今天我自己作为一个非官方的非专业人士，又来到了外滩金融论坛。||希望有一些观点供大家思考。"""

REFINE_USER_TEMPLATE = """## 视频信息
标题：{title}
{desc_line}

## 原始字幕（共 {count} 条）
{subtitle_block}

请逐条输出全部 {count} 条字幕的修正结果：
- 单条：序号|修正后文本
- 需要合并的连续条目：起始序号-结束序号|合并后文本
- 分段用 || 标记：序号|第一段。||第二段。||第三段。
- 请务必积极分段，避免输出大段密密麻麻的文字
不要输出任何其他内容。"""

CHAPTER_SYSTEM_PROMPT = """你是一个专业的内容分析师。你会收到一份完整的视频字幕文本。
请根据内容生成一份精炼的章节概要。

要求：
1. 将内容划分为 3-8 个章节，每个章节给出一个简洁的标题
2. 每个章节用 1-2 句话概括核心内容
3. 如果有重要结论或观点，单独列出
4. 语言精炼，直接给结论

输出格式：
## 章节概要
### 第一章：章节标题
章节概要内容...

### 第二章：章节标题
章节概要内容...

## 关键结论
- 结论1
- 结论2"""

CHAPTER_USER_TEMPLATE = """## 视频信息
标题：{title}
{desc_line}

## 完整字幕内容
{subtitle_text}

请生成章节概要。"""


def _get_http_status(exc: Exception) -> int | None:
    """从异常中提取 HTTP 状态码"""
    if hasattr(exc, "status_code"):
        return exc.status_code
    if hasattr(exc, "response") and hasattr(exc.response, "status_code"):
        return exc.response.status_code
    return None


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数（中文约 1.5 字符/token）"""
    return int(len(text) / 1.5)


def _split_entries(
    entries: list[tuple[int, str, str, str]],
    max_chars: int = 25000,
) -> list[list[tuple[int, str, str, str]]]:
    """将字幕条目按字符数分成多段，确保每段不超过 max_chars"""
    if not entries:
        return []

    segments: list[list[tuple[int, str, str, str]]] = []
    current: list[tuple[int, str, str, str]] = []
    current_len = 0

    for entry in entries:
        entry_len = len(entry[3]) + 20  # 序号+时间戳大约 20 字符
        if current and current_len + entry_len > max_chars:
            segments.append(current)
            current = []
            current_len = 0
        current.append(entry)
        current_len += entry_len

    if current:
        segments.append(current)

    return segments


# ========== LLM 客户端 ==========

class LLMClient:
    """LLM 客户端：字幕纠错 + 章节概要"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.moonshot.ai/v1",
        model: str = "kimi-k2.5",
        provider: str = "openai",
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.provider = provider

        if provider == "openai":
            self._openai_client = OpenAI(api_key=api_key, base_url=base_url)

    def _chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 16384,
    ) -> str:
        """统一的聊天接口，支持 OpenAI 和 Anthropic 兼容 API，带重试"""
        import time

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                return self._chat_once(messages, temperature, max_tokens)
            except Exception as e:
                # 4xx 客户端错误不重试
                status = _get_http_status(e)
                if status and 400 <= status < 500:
                    raise
                if attempt < max_retries:
                    wait = 2 ** attempt  # 1s, 2s
                    logger.warning(
                        "LLM 请求失败 (第 %d 次，%ds 后重试): %s",
                        attempt + 1, wait, e,
                    )
                    time.sleep(wait)
                else:
                    raise

    def _chat_once(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """单次聊天请求"""
        if self.provider == "openai":
            response = self._openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
            )
            return response.choices[0].message.content.strip()

        # Anthropic 兼容 API (纯 HTTP 调用)
        system = ""
        api_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                api_messages.append(msg)

        url = f"{self.base_url.rstrip('/')}/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": api_messages,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system

        resp = requests.post(url, headers=headers, json=payload, timeout=180)
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"].strip()

    def refine_srt(
        self,
        srt_path: str | Path,
        title: str = "",
        description: str = "",
        output_path: str | Path | None = None,
        max_chars_per_segment: int = 25000,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> Path:
        """使用 LLM 纠正字幕

        Args:
            srt_path: 原始 SRT 文件路径
            title: 视频标题（提供上下文给大模型）
            description: 视频简介（提供上下文给大模型）
            output_path: 输出路径，默认 _refined.srt
            max_chars_per_segment: 每段最大字符数（防止超 token 限制）
            progress_callback: 进度回调

        Returns:
            纠正后的 SRT 文件路径
        """
        srt_path = Path(srt_path)
        if output_path is None:
            output_path = srt_path.with_name(srt_path.stem + "_refined.srt")
        output_path = Path(output_path)

        entries = parse_srt(srt_path)
        if not entries:
            logger.warning("SRT 文件为空，跳过修正")
            return srt_path

        desc_line = f"\n简介：{description}" if description else ""

        # 分段处理
        segments = _split_entries(entries, max_chars_per_segment)
        logger.info("字幕纠错: %d 条，分 %d 段处理", len(entries), len(segments))

        all_refined: list[tuple[int, str, str, str]] = []
        para_markers: set[int] = set()  # 记录段落结尾的条目序号

        for seg_idx, seg_entries in enumerate(segments):
            if progress_callback:
                progress_callback(
                    f"纠正字幕 (段 {seg_idx + 1}/{len(segments)})...",
                    seg_idx / len(segments),
                )

            # 构建原始字幕块
            block_lines = [f"{idx}|{text}" for idx, _, _, text in seg_entries]
            block_text = "\n".join(block_lines)

            messages = [
                {"role": "system", "content": REFINE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": REFINE_USER_TEMPLATE.format(
                        title=title,
                        desc_line=desc_line,
                        count=len(seg_entries),
                        subtitle_block=block_text,
                    ),
                },
            ]

            try:
                result = self._chat(messages, temperature=0.3, max_tokens=16384)
            except Exception as e:
                logger.error("LLM 纠正失败 (段 %d): %s", seg_idx, e)
                all_refined.extend(seg_entries)
                continue

            # 解析结果，支持合并
            refined_groups = _parse_indexed_result(result)

            # 建立 序号→分组索引 的映射
            idx_to_group: dict[int, int] = {}
            for gi, (indices, _, _) in enumerate(refined_groups):
                for idx in indices:
                    idx_to_group[idx] = gi

            # 遍历原始条目，按分组输出（合并的条目只输出一次）
            emitted_groups: set[int] = set()
            for i, (_, start_time, end_time, orig_text) in enumerate(seg_entries):
                entry_idx = i + 1  # 1-based

                group_id = idx_to_group.get(entry_idx)
                if group_id is None:
                    # LLM 未返回该条目，保留原文
                    all_refined.append(
                        (len(all_refined) + 1, start_time, end_time, orig_text)
                    )
                    continue

                if group_id in emitted_groups:
                    # 已作为合并条目的一部分输出，跳过
                    continue
                emitted_groups.add(group_id)

                indices, text, is_para_end = refined_groups[group_id]

                # 合并范围：取最早 start 和最晚 end
                if len(indices) > 1:
                    merged_start = seg_entries[indices[0] - 1][1]
                    merged_end = seg_entries[indices[-1] - 1][2]
                else:
                    merged_start = start_time
                    merged_end = end_time

                new_idx = len(all_refined) + 1
                all_refined.append(
                    (new_idx, merged_start, merged_end, text)
                )
                if is_para_end:
                    para_markers.add(new_idx)

            if progress_callback:
                progress_callback(
                    f"纠正字幕...", (seg_idx + 1) / len(segments)
                )

        write_srt(all_refined, output_path, paragraph_markers=para_markers)

        if progress_callback:
            progress_callback("字幕纠正完成", 1.0)

        logger.info("纠正后字幕已保存: %s (%d 条)", output_path, len(all_refined))
        return output_path

    def summarize(
        self,
        srt_path: str | Path,
        title: str = "",
        description: str = "",
        output_path: str | Path | None = None,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> Path:
        """使用 LLM 生成章节概要

        Args:
            srt_path: SRT 文件路径（优先用纠正后的）
            title: 视频标题
            description: 视频简介
            output_path: 输出路径，默认 _summary.txt
            progress_callback: 进度回调

        Returns:
            概要文件路径
        """
        srt_path = Path(srt_path)
        if output_path is None:
            stem = srt_path.stem.replace("_refined", "")
            output_path = srt_path.with_name(stem + "_summary.txt")
        output_path = Path(output_path)

        if progress_callback:
            progress_callback("生成章节概要...", 0.0)

        entries = parse_srt(srt_path)
        subtitle_text = "\n".join(text for _, _, _, text in entries)

        if not subtitle_text.strip():
            logger.warning("字幕内容为空，跳过总结")
            output_path.write_text("（字幕内容为空）", encoding="utf-8")
            return output_path

        desc_line = f"\n简介：{description}" if description else ""

        # 如果过长，截断
        max_chars = 40000
        if len(subtitle_text) > max_chars:
            logger.warning("字幕过长 (%d 字符)，截断到 %d", len(subtitle_text), max_chars)
            subtitle_text = subtitle_text[:max_chars] + "\n... (已截断)"

        try:
            summary = self._chat(
                messages=[
                    {"role": "system", "content": CHAPTER_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": CHAPTER_USER_TEMPLATE.format(
                            title=title, desc_line=desc_line, subtitle_text=subtitle_text
                        ),
                    },
                ],
                temperature=0.5,
                max_tokens=4096,
            )
        except Exception as e:
            logger.error("LLM 章节概要失败: %s", e)
            summary = f"（章节概要生成失败: {e}）"

        output_path.write_text(summary, encoding="utf-8")

        if progress_callback:
            progress_callback("章节概要完成", 1.0)

        logger.info("章节概要已保存: %s", output_path)
        return output_path


def _parse_indexed_result(result: str) -> list[tuple[list[int], str, bool]]:
    """解析 LLM 返回的 "序号|文本" 或 "起始-结束|文本" 格式

    Returns:
        [([涉及的序号列表], 文本, 是否段落结尾), ...]
        合并范围如 9-10 会返回 ([9, 10], text, False)
    """
    groups: list[tuple[list[int], str, bool]] = []
    for line in result.strip().split("\n"):
        line = line.strip()
        if not line or "|" not in line:
            continue

        # 剥离末尾的 || 段落标记
        is_paragraph_end = line.rstrip().endswith("||")
        line = line.rstrip()
        if is_paragraph_end:
            line = line[:-2].rstrip()

        parts = line.split("|", 1)
        if len(parts) < 2:
            continue

        index_part = parts[0].strip()
        text = parts[1].strip()

        if not text:
            continue

        # 支持范围格式：9-10 表示合并第 9 和 10 条
        if "-" in index_part:
            range_parts = index_part.split("-", 1)
            try:
                start_idx = int(range_parts[0].strip())
                end_idx = int(range_parts[1].strip())
                indices = list(range(start_idx, end_idx + 1))
            except ValueError:
                continue
        else:
            try:
                indices = [int(index_part)]
            except ValueError:
                continue

        groups.append((indices, text, is_paragraph_end))

    return groups
