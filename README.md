# BBText - B站视频音频转字幕工具

BBText 是一个 Python 命令行 + GUI 工具，用于自动下载 B 站视频的音频，本地转写成字幕。搭配 Claude Code skill（bbt-video）可直接在对话中完成字幕精校和章节总结，生成本地 Markdown 发布稿，并自动发布到飞书文档。CLI 也支持通过外部 LLM API 做字幕修正和总结。

## 架构

```
URL 输入 → 音频下载 → 本地转写 → 精校修正 → 章节总结 → Markdown 发布稿 → 飞书文档
  ↓          ↓           ↓          ↓          ↓             ↓             ↓
Bilibili   DASH/FLV   SenseVoice  ┌──────────────────┐  本地保存       lark-cli
WBI 签名   纯音频提取  sherpa-onnx  │ bbt-video skill:  │  .md 文件      自动创建
                                  │ Claude 直接精校    │               文档+通知
                                  ├──────────────────┤
                                  │ CLI refine/summarize:
                                  │ 外部 LLM API
                                  └──────────────────┘
```

### 模块说明

| 模块 | 路径 | 说明 |
|------|------|------|
| URL 解析 | `bbt/bilibili/parser.py` | 支持 BV/AV/EP/SS 号及 b23.tv 短链接，BV↔AV 互转 |
| API 客户端 | `bbt/bilibili/api.py` | WBI 签名、DASH 音频流获取、FLV 合流兜底 |
| 下载器 | `bbt/bilibili/downloader.py` | 选最高质量音频流下载，合流格式自动 ffmpeg 提取 |
| 转写引擎 | `bbt/transcriber/whisper_engine.py` | SenseVoice 模型 (sherpa-onnx) + Silero VAD 分段，输出 SRT/TXT |
| LLM 客户端 | `bbt/llm/client.py` | OpenAI 兼容接口，CLI 模式下的字幕修正 + 章节总结 |
| 流程编排 | `bbt/pipeline.py` | 串联下载/转写/修正/总结流程，统一进度回调 |
| CLI | `bbt/cli.py` | typer 命令行，支持逐步或全流程执行 |
| GUI | `bbt/gui.py` | tkinter 界面，后台线程执行任务 |
| Skill | `skills/bbt-video/SKILL.md` | Claude Code skill，直接精校+总结+本地 Markdown+飞书发布 |
| 配置 | `bbt/config.py` | TOML 配置管理 |

### 项目结构

```
BBText/
├── bbt/
│   ├── __init__.py
│   ├── __main__.py          # python -m bbt 入口
│   ├── cli.py               # CLI 命令
│   ├── gui.py               # tkinter GUI
│   ├── config.py            # 配置管理
│   ├── pipeline.py          # 全流程编排
│   ├── bilibili/
│   │   ├── parser.py        # URL 解析、BV/AV 互转
│   │   ├── api.py           # Bilibili API (WBI 签名)
│   │   └── downloader.py   # 音频下载
│   ├── transcriber/
│   │   └── whisper_engine.py  # SenseVoice 转写
│   └── llm/
│       └── client.py        # LLM 客户端（CLI refine/summarize 用）
├── skills/
│   └── bbt-video/
│       ├── SKILL.md         # Claude Code skill 定义
│       └── scripts/         # 辅助脚本（publish、分块等）
├── config.toml.demo         # 配置模板（复制为 config.toml 使用）
├── main.py                  # 入口
├── pyproject.toml
└── tests/
```

## 安装

### 前置依赖

- **Python >= 3.12**（推荐使用 [uv](https://docs.astral.sh/uv/) 管理依赖）
- **ffmpeg**（音频处理）
- **lark-cli**（飞书文档创建和通知，使用 bbt-video skill 时需要）

### 1. 安装 BBText

```bash
# 克隆项目
git clone <repo-url>
cd BBText

# 安装依赖
uv sync

# 确保系统已安装 ffmpeg
brew install ffmpeg  # macOS
# 或 apt install ffmpeg  # Linux
```

> **macOS 用户注意**：如果运行时遇到 `Library not loaded: @rpath/libonnxruntime.x.x.x.dylib` 错误，请执行以下命令修复动态库：
> ```bash
> # 查找 onnxruntime 动态库位置
> find .venv -name "libonnxruntime*.dylib" 2>/dev/null
>
> # 复制/链接到 sherpa_onnx 目录（将 x.x.x 替换为实际版本号）
> cp .venv/lib/python3.12/site-packages/onnxruntime/capi/libonnxruntime.x.x.x.dylib \
>    .venv/lib/python3.12/site-packages/sherpa_onnx/lib/libonnxruntime.x.x.x.dylib
> ```

### 2. 安装 lark-cli（使用 bbt-video skill 时需要）

[**lark-cli**](https://github.com/larksuite/cli) 是飞书官方 CLI 工具，bbt-video skill 通过它创建飞书文档和发送通知。

```bash
# 安装 lark-cli
npm install -g @larksuite/cli

# 安装 lark-cli 的 Claude Code skills
npx skills add larksuite/cli -y -g

# 配置飞书应用凭证（交互式引导，需要浏览器操作）
lark-cli config init

# 登录授权
lark-cli auth login --recommend
```

> **注意**：`lark-cli config init` 会在浏览器中引导你创建飞书开放平台应用并配置凭证。完成登录后，lark-cli 会获得创建文档、发送消息等权限。`bbt-video` skill 创建文档时会显式使用 `--as user`，确保新文档 owner 是当前登录用户本人。详细说明参见 [lark-cli 文档](https://github.com/larksuite/cli)。

### 3. 配置 BBText

复制配置模板并编辑：

```bash
cp config.toml.demo config.toml
```

编辑 `config.toml` 填入你的配置：

```toml
[bilibili]
cookie = ""          # 可选，登录后可获取更高质量音频

[transcriber]
device = "coreml"    # "auto" 自动选择；Apple Silicon 用 "coreml"，NVIDIA GPU 用 "cuda"，CPU 用 "cpu"
num_threads = 4      # CPU/CoreML 调度线程数；CPU 模式可按机器适当调大

[llm]
provider = "openai"
api_key = "your-api-key"  # 也可通过环境变量 BBT_LLM_API_KEY 设置
base_url = "https://openrouter.ai/api/v1"
model = "deepseek/deepseek-v3.2"

[output]
dir = "output"

[feishu]
folder_token = ""    # 可选：飞书云空间文件夹 token；留空时 bbt-video skill 创建到用户个人空间
user_id = ""         # 可选：飞书用户 open_id，仅用于发送完成通知，不影响文档 owner
```

> **安全提示**：`config.toml` 已被 `.gitignore` 排除，不会被提交到 Git。API Key 也可以通过环境变量 `BBT_LLM_API_KEY` 设置，避免写入配置文件。

SenseVoice 模型首次使用时会自动下载到 `~/.cache/bbt/` 目录。

**飞书配置说明**（使用 bbt-video skill 自动发布到飞书时需要）：

1. 确保 lark-cli 已安装并完成用户身份登录（见上方步骤 2）
2. 可选：从飞书云空间地址栏获取 `folder_token`（`https://xxx.feishu.cn/drive/folder/xxx` 中的最后一段）。留空时，skill 会把文档创建到用户个人空间
3. 使用 lark-cli 获取你的 `user_id`：
   ```bash
   lark-cli contact +get-user
   ```
4. 填入 `config.toml` 的 `[feishu]` 部分。`user_id` 只用于发送完成通知，不影响文档 owner

### 4. 安装 bbt-video Skill（可选）

项目包含 `bbt-video` skill，可在 Claude Code 对话中直接处理 B 站视频：

```bash
# 将 skill 链接到 Claude Code skills 目录
ln -s /path/to/BBText/skills/bbt-video ~/.claude/skills/bbt-video
```

配置完成后，在 Claude Code 中直接提供 B 站视频链接即可触发全自动流程（下载 → 转写 → 精校 → 总结 → 本地 Markdown → 飞书文档）。

## 使用方法

### CLI

```bash
# 全流程：下载 → 转写 → 修正 → 总结
uv run python main.py pipeline "https://www.bilibili.com/video/BV1xx411c7mD"

# 只下载音频
uv run python main.py download "https://www.bilibili.com/video/BV1xx411c7mD"

# 只转写已有音频
uv run python main.py transcribe output/xxx.m4a

# 只做 LLM 修正
uv run python main.py refine output/xxx.srt

# 只做章节总结
uv run python main.py summarize output/xxx.srt

# 跳过某些步骤
uv run python main.py pipeline "<url>" --skip-refine
uv run python main.py pipeline "<url>" --skip-summarize

# 查看当前配置
uv run python main.py config

# 启动 GUI
uv run python main.py gui
```

### 输出文件

全流程会在 `output/<视频标题>/` 目录下生成：

- `<标题>.m4a` — 提取的音频
- `<标题>.srt` — 原始转写字幕
- `<标题>_refined.srt` — LLM 修正后的字幕
- `<标题>_summary.txt` — 章节总结
- `<标题>_doc.md` — 与飞书文档内容一致的本地 Markdown 发布稿

### LLM 功能

**字幕修正**：修正专业名词、补充标点、还原语义，保持时间戳不变。长字幕自动分段处理。

**章节总结**：将视频内容分为 3-8 个章节，每个章节包含标题和简要描述。

## 关于 GPU 加速

SenseVoice 通过 sherpa-onnx 使用 ONNX Runtime 进行推理，支持多种硬件加速。

### Apple Silicon (M1/M2/M3/M4) — CoreML

macOS 上 sherpa-onnx 依赖的 onnxruntime 默认已包含 `CoreMLExecutionProvider`，无需额外安装。只需将 `config.toml` 中 `device` 设为 `"coreml"`，也可以设为 `"auto"` 让程序自动选择可用硬件 provider：

```toml
[transcriber]
device = "coreml"
num_threads = 4
```

CoreML 可以利用 Apple GPU / Neural Engine 加速推理，但实际速度取决于模型形态和音频切分方式。SenseVoice int8 小模型在部分 M 系列机器上可能 CPU 更快，建议用同一段音频分别测试 `--device coreml` 和 `--device cpu` 后选择。

验证 CoreML 是否可用：

```bash
uv run python -c "import onnxruntime; print(onnxruntime.get_available_providers())"
# 输出中包含 CoreMLExecutionProvider 即表示可用
```

### NVIDIA GPU — CUDA

Linux/Windows 上如有 NVIDIA GPU，需要安装 onnxruntime-gpu 替代默认的 onnxruntime：

```bash
# 卸载 CPU 版本，安装 GPU 版本
uv pip uninstall onnxruntime
uv pip install onnxruntime-gpu
```

然后在 `config.toml` 中设置：

```toml
[transcriber]
device = "cuda"
num_threads = 4
```

需要系统已安装 CUDA Toolkit 和 cuDNN。验证 CUDA 是否可用：

```bash
uv run python -c "import onnxruntime; print(onnxruntime.get_available_providers())"
# 输出中包含 CUDAExecutionProvider 即表示可用
```

### CPU 回退

如果 GPU 不可用或遇到兼容问题，可回退到 CPU 模式：

```toml
[transcriber]
device = "cpu"
num_threads = 4
```

CLI 也支持临时覆盖设备和线程数，无需修改配置文件：

```bash
uv run python main.py transcribe output/xxx.m4a --device cpu --num-threads 8
uv run python main.py pipeline "<url>" --device coreml --num-threads 4
```

## 技术细节

- **B站下载**：纯 Python 实现，参考 BBDown 的 WBI 签名算法，支持 DASH 和 FLV 合流两种格式
- **语音转写**：使用 SenseVoice 模型（阿里达摩院），通过 sherpa-onnx 本地推理，Silero VAD 做语音分段
- **精校总结（bbt-video skill）**：由 Claude 直接完成字幕精校和章节总结，无需额外 LLM API
- **精校总结（CLI）**：通过 OpenAI 兼容 API 调用外部 LLM，支持 OpenRouter 等任意兼容服务

## License

MIT
