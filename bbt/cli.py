"""CLI 命令行接口"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from .config import load_config, AppConfig
from .pipeline import Pipeline

app = typer.Typer(
    name="bbt",
    help="BBText - B站视频音频转字幕工具",
    no_args_is_help=True,
)
console = Console()


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_time=False, show_path=False)],
    )


def _load(config_path: str | None, verbose: bool) -> AppConfig:
    setup_logging(verbose)
    cfg = load_config(config_path)
    return cfg


def _progress_callback(task_id, progress_obj) -> tuple:
    """创建进度回调闭包"""
    def callback(msg: str, p: float) -> None:
        progress_obj.update(task_id, description=msg, completed=int(p * 100))
    return callback


@app.command()
def download(
    url: str = typer.Argument(..., help="B站视频 URL"),
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="配置文件路径"),
    output_dir: Optional[str] = typer.Option(None, "--output-dir", "-o", help="输出目录"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细日志"),
) -> None:
    """下载B站视频音频"""
    cfg = _load(config_path, verbose)
    if output_dir:
        cfg.output.dir = output_dir

    from .bilibili.api import BilibiliClient
    from .bilibili.downloader import BilibiliDownloader

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("下载中...", total=100)

        client = BilibiliClient(cookie=cfg.bilibili.cookie)
        downloader = BilibiliDownloader(client)
        dl_result = downloader.resolve_and_download(
            url, output_dir=cfg.output.dir,
            progress_callback=lambda msg, p: progress.update(task, description=msg, completed=int(p * 100)),
        )
        files = dl_result.files

    console.print("\n[green]下载完成![/green]")
    for f in files:
        console.print(f"  {f}")


@app.command()
def transcribe(
    audio_file: str = typer.Argument(..., help="音频文件路径"),
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="配置文件路径"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出 SRT 路径"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细日志"),
) -> None:
    """转写音频文件为 SRT 字幕（SenseVoice 引擎）"""
    cfg = _load(config_path, verbose)

    from .transcriber.whisper_engine import transcribe_audio

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("转写中...", total=100)
        srt_path = transcribe_audio(
            audio_file, output_srt=output,
            device=cfg.transcriber.device,
            fmt=cfg.output.format,
            timestamps=cfg.output.timestamps,
            progress_callback=lambda msg, p: progress.update(task, description=msg, completed=int(p * 100)),
        )

    console.print(f"\n[green]转写完成![/green] {srt_path}")


@app.command()
def refine(
    srt_file: str = typer.Argument(..., help="SRT 字幕文件路径"),
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="配置文件路径"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出路径"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细日志"),
) -> None:
    """使用 LLM 修正字幕"""
    cfg = _load(config_path, verbose)

    if not cfg.llm.api_key:
        console.print("[red]错误: 未配置 LLM API Key，请在 config.toml 中设置 llm.api_key[/red]")
        raise typer.Exit(1)

    from .llm.client import LLMClient

    llm = LLMClient(api_key=cfg.llm.api_key, base_url=cfg.llm.base_url, model=cfg.llm.model, provider=cfg.llm.provider)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("修正中...", total=100)
        result = llm.refine_srt(
            srt_file, output_path=output,
            progress_callback=lambda msg, p: progress.update(task, description=msg, completed=int(p * 100)),
        )

    console.print(f"\n[green]修正完成![/green] {result}")


@app.command()
def summarize(
    srt_file: str = typer.Argument(..., help="SRT 字幕文件路径"),
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="配置文件路径"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出路径"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细日志"),
) -> None:
    """使用 LLM 生成内容总结"""
    cfg = _load(config_path, verbose)

    if not cfg.llm.api_key:
        console.print("[red]错误: 未配置 LLM API Key，请在 config.toml 中设置 llm.api_key[/red]")
        raise typer.Exit(1)

    from .llm.client import LLMClient

    llm = LLMClient(api_key=cfg.llm.api_key, base_url=cfg.llm.base_url, model=cfg.llm.model, provider=cfg.llm.provider)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("总结中...", total=100)
        result = llm.summarize(
            srt_file, output_path=output,
            progress_callback=lambda msg, p: progress.update(task, description=msg, completed=int(p * 100)),
        )

    console.print(f"\n[green]总结完成![/green] {result}")
    console.print(Path(result).read_text(encoding="utf-8"))


@app.command()
def pipeline(
    url: str = typer.Argument(..., help="B站视频 URL"),
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="配置文件路径"),
    output_dir: Optional[str] = typer.Option(None, "--output-dir", "-o", help="输出目录"),
    skip_refine: bool = typer.Option(False, "--skip-refine", help="跳过 LLM 修正"),
    skip_summarize: bool = typer.Option(False, "--skip-summarize", help="跳过 LLM 总结"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细日志"),
) -> None:
    """全流程: 下载 → 转写 → 修正 → 总结"""
    cfg = _load(config_path, verbose)
    if output_dir:
        cfg.output.dir = output_dir

    pipe = Pipeline(cfg)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("处理中...", total=100)
        result = pipe.run(
            url,
            skip_refine=skip_refine,
            skip_summarize=skip_summarize,
            progress_callback=lambda msg, p: progress.update(task, description=msg, completed=int(p * 100)),
        )

    console.print("\n[green]全流程完成![/green]")
    if result.audio_files:
        console.print(f"\n[bold]音频文件:[/bold]")
        for f in result.audio_files:
            console.print(f"  {f}")
    if result.srt_files:
        console.print(f"\n[bold]字幕文件:[/bold]")
        for f in result.srt_files:
            console.print(f"  {f}")
    if result.refined_srt_files:
        console.print(f"\n[bold]修正后字幕:[/bold]")
        for f in result.refined_srt_files:
            console.print(f"  {f}")
    if result.summary_files:
        console.print(f"\n[bold]内容总结:[/bold]")
        for f in result.summary_files:
            console.print(f"  {f}")


@app.command()
def gui(
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="配置文件路径"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细日志"),
) -> None:
    """启动 GUI 界面"""
    _load(config_path, verbose)

    from .gui import run_gui
    run_gui(config_path)


@app.command(name="config")
def show_config(
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="配置文件路径"),
) -> None:
    """显示当前配置"""
    cfg = load_config(config_path)
    console.print("[bold]当前配置:[/bold]\n")
    console.print(f"  bilibili.cookie: {'***' if cfg.bilibili.cookie else '(未设置)'}")
    console.print(f"  transcriber.device: {cfg.transcriber.device}")
    console.print(f"  llm.api_key: {'***' if cfg.llm.api_key else '(未设置)'}")
    console.print(f"  llm.base_url: {cfg.llm.base_url}")
    console.print(f"  llm.model: {cfg.llm.model}")
    console.print(f"  output.dir: {cfg.output.dir}")
