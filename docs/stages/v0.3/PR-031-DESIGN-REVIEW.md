# V0.3 PR-031 — Structured PDF Block Parser 深度审查与验收

基线：PR-030 已合并到 feat/v0.2-pipeline-reliability，PR-031 从该分支继续；
V0.2 已进入 main，但 PR-030/031 不直接修改 main。PR-031 只提供本地、
确定性的 PDF → DocumentIR 解析能力，不改现有 API/Worker/XMind。

## A. 设计审查：已修正的根因

### P0-A：PyMuPDF block 可能横跨左右栏

直接 get_text("blocks") 的输出不保证天然阅读顺序；
sort=True 的 top-left sort 也不能保证阅读者习惯的双栏顺序。
实测同一个 PyMuPDF block 可能包含左/右栏的多个 line，
甚至同一 line 的 spans 跨越页面中央的 gutter。

修复：先从 get_text("dict") 提取 line/span。
仅在相邻 span 的间距超过绝对与页面宽度双阈值、
且跨越页面中心位置时分割。分割后的 span 按原始 block、
左右 lane 与上下邻接重建逻辑文本块。随后判断是否满足
两侧至少两块、明确 gutter 和垂直重叠三个条件；
满足才选 two_column_heuristic，否则 top_left_fallback
并报告 COLUMN_ORDER_UNCERTAIN。跨栏/较大字体标题
作为 spanner 将其余文本划入阅读段。

边界：脚注、表格、倾斜/竖排、三栏、小字号双栏和浮动图
仍可能被误判。布局方法属于启发式，不输出伪精度百分比。
真实论文的独立人工阅读顺序评测属于 PR-032/PR-039。

### P0-B：PDF 源坐标不能直接当作显示坐标

PyMuPDF get_text 通常给出未旋转裁剪页的 top-left 坐标；
Page.rect 是旋转后的显示区域。PR-031 用 Page.rotation_matrix
把每个文本块 bbox 映射到显示页坐标 top_left_pt，
页宽高取 Page.rect；0.25 pt 内的数字误差允许钳位，
超出可见页面的块拒绝导出，记录 BLOCK_OUTSIDE_VIEWPORT，
避免图上显示“可点击到不可见文字”的伪证据。

块级 bbox 只是粗定位，不是字符或字形级高亮；不能替代
后续 EvidenceResolver 的 quote offset 和前端精确选区。

### P0-C：解析文本与原始 PDF 内容不能混淆

text 是按 PyMuPDF span/line 重组的文本；在字体 span 中间
可能增加明确推断的空格，normalized_text 仅进行 NFC + LF。
该字符串不是 PDF 的原始字节，也不保证公式符号完全保真。
版本化 config_sha256 和解析器版本用于保持可追溯性。

### P1-D：PDF 异常和资源限制必须失败可诊断

限制文件大小、页数、总块数和单块字符长度，
不静默截断。加密 PDF 报 PDF_ENCRYPTED，损坏 PDF
报 PDF_PARSE_FAILED，超限独立错误码。无文字页保留
合法 DocumentIR 空 blocks + PAGE_NO_EXTRACTABLE_TEXT；
图片型扫描页报告 POSSIBLE_SCANNED_PAGE，不虚构 OCR 文字。

### P1-E：不能提前发明章节树与结论

本阶段仅为候选 heading/caption 打 kind 标签；
DocumentIR.sections 为空，各 Block.section_id = None。
不能将启发式 heading 标记为经验证的科研结论。
Claim 与 Evidence 模型仅在后续独立模块消费此 IR，
当前解析器不发布支持度判断。

### P1-F：输出必须可复现

PDF 源文件按块 SHA-256，解析配置 + PyMuPDF 版本指纹；
同一 revision_id、源 PDF、parser 版本与配置保证稳定 block ID。
读取前后复算文件指纹，若内容变化拒绝输出；CLI 用临时 JSON
加 os.replace 原子落盘。模型输入与输出不经过网络。

## B. 新增代码与边界

| 文件 | 职责 |
|---|---|
| paper2xmind/parsers/layout.py | line/span 拆分、逻辑块合并、双栏排序 |
| paper2xmind/parsers/pymupdf_blocks.py | 几何坐标归一、DocumentIR、诊断、hash、资源限制 |
| paper2xmind/parsers/__main__.py | 离线解析 CLI 与原子序列化 |
| tests/test_parser_v03.py | PDF 黄金回归与反例 |
| evals/golden/v03_parser_cases.yaml | 覆盖边界与未验证事项 |
| evals/benchmarks/pdf_parser_v031.py | 本地可复现性能采样 |

输入：PDF 路径 + 32 字符十六进制 Revision ID。
输出：ParseResult，内部 DocumentIR schema_version=document_ir/1.0.0；
Page 的宽高采用最终显示坐标，BBox 是 top_left_pt；
reading_order 每页从 0 开始连续；Sections 在本阶段为空；
diagnostics 标明 columns、strategy、raw/emitted 字符和 warnings。

## C. 本地调用

    python -m pip install -e ".[dev]"
    python -m paper2xmind.parsers ./paper.pdf \
      --revision-id 0123456789abcdef0123456789abcdef \
      --output ./output/paper.document-ir.json

独立 Benchmark：

    python evals/benchmarks/pdf_parser_v031.py ./paper.pdf --runs 3

输出的时间只是当前硬件/文件的实际采样，不代表所有论文的延迟目标。

## D. 自动化验收 / 范围

测试覆盖本地合成 PDF（不需要 LLM/API）：
- 标题与正文、IR Schema、版本化 provenance
- 双栏文字交错插入、同一个原生 block 内跨栏 span
- 页面旋转 0/90/180/270，CropBox + 旋转组合
- 小数坐标误差与越界定位拒绝
- 空白页、图片型/扫描候选页面、双页互不混淆
- PDF 加密、损坏、超限、防止静默截断
- stable ID、canonical JSON 与配置哈希

CI 使用 Python 3.10/3.11/3.12，执行根测试、后端回归与前端构建。
真实学术文献的阅读顺序精度、数学式、表格、OCR 完整性并没有
在本 PR 中得到科学级验证，明确留作后续人工标注评测。

## E. 下一批安排

PR-032：DocumentProfiler + ParserRouter + 可选 Docling；
加入真实授权的文献集与章节/表格检测、布局不确定时的升级路径。
PR-033：以 DocumentIR Block + Section 为单元的语义 Chunker。
PR-034/035：Claim extraction 与独立 EvidenceVerifier。
PR-036：带版本的 Artifact 存储及 Worker feature flag。
PR-037～039：PDF/导图引用交互、真实性评估与真实科研黄金集。

## F. 官方技术依据

https://pymupdf.readthedocs.io/en/latest/page.html
https://pymupdf.readthedocs.io/en/latest/app1.html
https://pymupdf.readthedocs.io/en/latest/recipes-images.html
