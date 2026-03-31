"""tkinter GUI 界面"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from pathlib import Path
from typing import Any

from .config import load_config, AppConfig
from .pipeline import Pipeline


class BBTextGUI:
    """BBText 主窗口"""

    def __init__(self, config_path: str | None = None):
        self.config = load_config(config_path)
        self.config_path = config_path
        self.msg_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.running = False

        self.root = tk.Tk()
        self.root.title("BBText - B站视频转字幕工具")
        self.root.geometry("640x520")
        self.root.resizable(True, True)
        self.root.minsize(500, 400)

        self._build_ui()
        self._poll_queue()

    def _build_ui(self) -> None:
        # URL 输入
        url_frame = ttk.LabelFrame(self.root, text="B站视频 URL", padding=8)
        url_frame.pack(fill="x", padx=10, pady=(10, 5))

        self.url_var = tk.StringVar()
        ttk.Entry(url_frame, textvariable=self.url_var, font=("Arial", 11)).pack(fill="x")

        # 步骤选择
        step_frame = ttk.LabelFrame(self.root, text="处理步骤", padding=8)
        step_frame.pack(fill="x", padx=10, pady=5)

        self.var_download = tk.BooleanVar(value=True)
        self.var_transcribe = tk.BooleanVar(value=True)
        self.var_refine = tk.BooleanVar(value=True)
        self.var_summarize = tk.BooleanVar(value=True)

        checks_frame = ttk.Frame(step_frame)
        checks_frame.pack(fill="x")
        ttk.Checkbutton(checks_frame, text="下载音频", variable=self.var_download, command=self._on_step_change).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(checks_frame, text="转写字幕", variable=self.var_transcribe).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(checks_frame, text="LLM 修正", variable=self.var_refine).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(checks_frame, text="生成总结", variable=self.var_summarize).pack(side="left")

        # 参数配置
        param_frame = ttk.LabelFrame(self.root, text="参数配置", padding=8)
        param_frame.pack(fill="x", padx=10, pady=5)

        # 设备选择
        row1 = ttk.Frame(param_frame)
        row1.pack(fill="x", pady=2)
        ttk.Label(row1, text="推理设备:", width=12, anchor="w").pack(side="left")
        self.device_var = tk.StringVar(value=self.config.transcriber.device)
        ttk.Combobox(row1, textvariable=self.device_var, values=["coreml", "cuda", "cpu"], state="readonly", width=15).pack(side="left")

        # LLM 模型
        row2 = ttk.Frame(param_frame)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="LLM 模型:", width=12, anchor="w").pack(side="left")
        self.llm_model_var = tk.StringVar(value=self.config.llm.model)
        ttk.Entry(row2, textvariable=self.llm_model_var, width=30).pack(side="left")

        # 按钮
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=8)

        self.btn_start = ttk.Button(btn_frame, text="开始处理", command=self._on_start)
        self.btn_start.pack(side="left", padx=(0, 10))

        self.btn_stop = ttk.Button(btn_frame, text="停止", command=self._on_stop, state="disabled")
        self.btn_stop.pack(side="left")

        # 进度
        progress_frame = ttk.Frame(self.root)
        progress_frame.pack(fill="x", padx=10, pady=(0, 5))

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x")

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(progress_frame, textvariable=self.status_var).pack(anchor="w", pady=(2, 0))

        # 日志
        log_frame = ttk.LabelFrame(self.root, text="日志", padding=4)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, font=("Menlo", 9), state="disabled")
        self.log_text.pack(fill="both", expand=True)

    def _on_step_change(self) -> None:
        """下载取消勾选时自动取消转写"""
        if not self.var_download.get():
            self.var_transcribe.set(False)

    def _on_start(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("提示", "请输入 B 站视频 URL")
            return

        # 更新配置
        self.config.transcriber.device = self.device_var.get()
        self.config.llm.model = self.llm_model_var.get()

        self.running = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.progress_var.set(0)
        self._clear_log()

        thread = threading.Thread(target=self._run_pipeline, args=(url,), daemon=True)
        thread.start()

    def _on_stop(self) -> None:
        self.running = False
        self.status_var.set("已停止")
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")

    def _run_pipeline(self, url: str) -> None:
        try:
            pipe = Pipeline(self.config)
            pipe.run(
                url,
                skip_download=not self.var_download.get(),
                skip_transcribe=not self.var_transcribe.get(),
                skip_refine=not self.var_refine.get(),
                skip_summarize=not self.var_summarize.get(),
                progress_callback=self._on_progress,
            )
            self.msg_queue.put(("done", None))
        except Exception as e:
            self.msg_queue.put(("error", str(e)))

    def _on_progress(self, msg: str, p: float) -> None:
        self.msg_queue.put(("progress", (msg, p)))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, data = self.msg_queue.get_nowait()
                if kind == "progress":
                    msg, p = data
                    self.progress_var.set(p * 100)
                    self.status_var.set(msg)
                    self._append_log(f"[INFO] {msg} ({p * 100:.0f}%)")
                elif kind == "done":
                    self.progress_var.set(100)
                    self.status_var.set("全部完成!")
                    self._append_log("[完成] 全流程处理完成")
                    self.btn_start.config(state="normal")
                    self.btn_stop.config(state="disabled")
                    self.running = False
                elif kind == "error":
                    self.status_var.set(f"错误: {data}")
                    self._append_log(f"[错误] {data}")
                    self.btn_start.config(state="normal")
                    self.btn_stop.config(state="disabled")
                    self.running = False
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _clear_log(self) -> None:
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _append_log(self, msg: str) -> None:
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def run(self) -> None:
        self.root.mainloop()


def run_gui(config_path: str | None = None) -> None:
    gui = BBTextGUI(config_path)
    gui.run()
