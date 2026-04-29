---
name: bbt-video
description: "Bilibili 视频转文字全流程编排：下载音频、语音转写、字幕精校、生成概要、生成本地 Markdown 发布稿，并创建飞书文档。当用户提供 Bilibili (B站) 视频链接（含 BV/AV/EP/SS 号、b23.tv 短链接）且需要处理视频内容时触发。包括转译、转文字、总结、精校、下载字幕、概括、整理视频内容等操作。甚至仅提供链接且上下文暗示需要处理视频内容时也应触发。"
---

# Bilibili 视频转文字全流程

收到用户的 B 站视频链接后，完成从下载到精校文字 + 本地 Markdown 发布稿 + 飞书文档的全流程。下载和转写由脚本完成，精校和概要由你直接完成（不需要调用外部 LLM API）。

## 工作流程

### 1. 提取视频 URL

从用户消息中提取 Bilibili URL。常见格式：

- `https://www.bilibili.com/video/BVxxxxxxxxxx`
- `https://www.bilibili.com/video/AVxxxxxxxx`
- `https://www.bilibili.com/bangumi/play/epxxxxx` 或 `ssxxxxx`
- `https://b23.tv/xxxxxxx`（短链接）
- 纯 BV/AV 号：`BVxxxxxxxxxx`、`AVxxxxxxxx`

如果用户没有提供 URL，停下来请用户提供。

### 2. 运行下载+转写脚本

在项目根目录下执行：

```bash
cd <BBText项目根目录> && uv run python skills/bbt-video/scripts/publish.py "<URL>"
```

**执行时间参考**：10 分钟以内的短视频通常 1-2 分钟完成。请在执行前告知用户预计等待时间。

脚本会完成下载和语音转写，最后输出 JSON 汇总（`RESULT_JSON_START` 和 `RESULT_JSON_END` 之间）。JSON 包含 `video_title`、`video_description`、`srt_files`（原始字幕文件路径列表）、`output_dir`。

如果脚本执行失败，参考以下错误处理：
- **网络问题**（B 站 API 请求失败）→ 建议检查网络或配置 cookie
- **账号未登录**（WBI key 获取失败）→ 提示用户在 `config.toml` 中配置 `bilibili.cookie`
- **ffmpeg 未安装** → 提示用户安装 ffmpeg

### 3. 读取原始字幕并识别语言

读取脚本输出的第一个 SRT 文件（`srt_files[0]`）。SRT 文件格式如下：

```
1
00:00:01,000 --> 00:00:03,500
第一句字幕文本

2
00:00:03,500 --> 00:00:06,200
第二句字幕文本
```

**语言检测：** 读取字幕后，根据字幕正文内容判断源语言。SenseVoice 转写引擎支持中/英/日/韩/粤语，字幕可能是任意这些语言。重点关注英文内容——如果大部分字幕文本是英文，则标记为"需要翻译"。这个判断会影响后续精校和概要的处理方式。

### 4. 字幕精校（含翻译）

你直接对原始字幕进行精校。逐条阅读字幕，按以下规则处理：

**精校规则：**

1. **积极分段**（最重要的规则）：在精校后的文本中，用空行标记分段位置。
   - 每个自然段落控制在 1-3 句话（约 30-100 字）
   - 分段时机：话题转换、视角切换、一个完整观点结束开启新论述、说话人停顿或语气转折、举例结束后回归主题
   - 大段密密麻麻的文字非常难以阅读，请务必积极分段
2. 根据视频标题和简介的上下文，修正语音识别中的专业名词、人名、地名等错误
3. 补全缺失的标点符号（逗号、句号、问号等），使语句完整自然
4. 如果连续几条字幕明显是同一句话被语音识别误切开的（例如上一条以"的"结尾、下一条以"程度"开头），应将它们合并为一条

**翻译处理（当源语言不是中文时）：**

如果步骤 3 判定字幕源语言是英文或其他非中文语言，精校时需要同时完成翻译：

- 将非中文内容翻译为自然流畅的中文，不是逐字直译，而是用中文的表达习惯重新组织
- 专有名词（人名、公司名、产品名等）采用中文通用译名，首次出现时可附原文，如"谷歌（Google）"
- 技术术语如果中文语境下更常用英文原文，直接保留英文，如 API、GPU、LLM
- 翻译时注意保持原意准确，不要添加原文没有的内容，也不要遗漏关键信息
- 精校后的最终输出始终是中文

**精校输出格式：** 将精校后的文本保存为纯文本文件（去掉序号和时间戳，保留正文，用空行分段）。保存路径为原 SRT 文件同目录下的 `<视频标题>_refined.txt`。

### 5. 生成概要

基于精校后的文本，生成章节概要。概要始终以中文输出，无论源语言是什么。

**概要要求：**

1. 将内容划分为 3-8 个章节，每个章节给出一个简洁的标题
2. 每个章节用 1-2 句话概括核心内容
3. 如果有重要结论或观点，单独列出
4. 语言精炼，直接给结论

**概要输出格式：**

```markdown
## 章节概要

### 第一章：章节标题
章节概要内容...

### 第二章：章节标题
章节概要内容...

## 关键结论
- 结论1
- 结论2
```

将概要保存为原 SRT 文件同目录下的 `<视频标题>_summary.txt`。

### 6. 生成本地 Markdown 发布稿

将准备写入飞书文档的完整内容先保存为本地 Markdown 文件。保存路径为原 SRT 文件同目录下的 `<视频标题>_doc.md`。

这份 Markdown 是飞书文档的本地镜像，内容必须与准备发布到飞书的完整正文一致，不要因为飞书分块而拆散或省略内容。即使飞书配置为空或飞书创建失败，也要保留这个本地 Markdown 文件。

`<翻译标注>` 的含义：如果源语言是中文则为空（即标题为"视频标题 - 转译精校"），如果是英文翻译来的则填"（英译中）"（即"视频标题 - 转译精校（英译中）"），其他语言类推。

推荐使用脚本生成，避免手工拼接遗漏：

```bash
DOC_MD="<原 SRT 同目录>/<视频标题>_doc.md"
SUMMARY_FILE="<原 SRT 同目录>/<视频标题>_summary.txt"
REFINED_FILE="<原 SRT 同目录>/<视频标题>_refined.txt"

uv run python skills/bbt-video/scripts/build_doc_markdown.py \
  --summary "$SUMMARY_FILE" \
  --refined "$REFINED_FILE" \
  --title "<视频标题>" \
  --url "<视频URL>" \
  --output "$DOC_MD"
```

Markdown 内容结构：

```markdown
## 概要

<步骤 5 生成的概要内容>

---

> 原视频链接：[<视频标题>](<视频URL>)

---

## 精校全文

<步骤 4 精校后的纯文本内容>
```

### 7. 创建飞书文档

使用 lark-cli 创建飞书文档，将步骤 6 生成的本地 Markdown 发布稿写入文档。

**先读取配置**：从项目根目录的 `config.toml` 中读取飞书配置（`[feishu]` 下的 `folder_token` 和 `user_id`）。如果配置为空，跳过飞书相关步骤并提示用户配置，但不要删除本地 Markdown 发布稿。

```bash
DOC_MD="<原 SRT 同目录>/<视频标题>_doc.md"

# 创建文档（folder_token 从 config.toml [feishu] 读取）
lark-cli docs +create --title "<视频标题> - 转译精校<翻译标注>" --folder-token <folder_token> --markdown "$(<"$DOC_MD")"
```

如果本地 Markdown 发布稿超过 30000 字节（约 10000 中文字），需要分块创建并追加：

```bash
DOC_MD="<原 SRT 同目录>/<视频标题>_doc.md"

# 先将本地 Markdown 发布稿分块
uv run python skills/bbt-video/scripts/split_chunks.py "$DOC_MD" 30000
# 记录输出的每一行路径，第一行用于创建文档，后续行用于追加

# 用第一块创建文档（folder_token 从 config.toml 读取）
FIRST_CHUNK="<第一块路径>"
lark-cli docs +create --title "<视频标题> - 转译精校<翻译标注>" --folder-token <folder_token> --markdown "$(<"$FIRST_CHUNK")"

# 提取 document_id 后，追加剩余块
NEXT_CHUNK="<下一块路径>"
lark-cli docs +update --mode append --doc "<doc_id>" --markdown "$(<"$NEXT_CHUNK")"
```

从 `lark-cli docs +create` 的输出中提取 `document_id`，拼接为 `https://feishu.cn/docx/<document_id>` 得到文档链接。

### 8. 发送飞书通知

从 `config.toml` 的 `[feishu]` 读取 `user_id`。如果配置为空则跳过此步骤。

```bash
lark-cli im +messages-send --as bot --user-id <user_id> --text "视频「<视频标题>」已转译精校完成，文档已保存。\n飞书文档：<文档链接>"
```

### 9. 向用户汇报

向用户汇报：
- 视频标题
- 本地文件保存位置（精校文本、概要、本地 Markdown 发布稿）
- 飞书文档链接

## 处理多个视频

如果用户一次提供了多个视频链接，按顺序逐个处理，每完成一个汇报一次进度。不要并行处理，避免资源冲突。

## 部分流程支持

如果用户只需要部分操作（例如只要字幕不要概要、只要下载不要转写），可以使用单独的 CLI 命令：

- 只下载音频：`uv run python main.py download "<URL>"`
- 只转写：`uv run python main.py transcribe "<audio_file>"`
- 只精校/概要：你自己直接完成（不需要 API 调用）

根据用户的具体需求选择合适的命令组合，后续的飞书文档创建步骤视情况调整。
