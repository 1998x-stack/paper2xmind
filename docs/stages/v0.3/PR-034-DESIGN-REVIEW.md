# V0.3 PR-034 — Evidence-grounded Claim Extraction

> 代码审查、工程设计、实现契约与验收
>
> 基线：PR-033（feat/v0.3-pr033-source-aware-chunking）。本 PR 仅新增
> paper2xmind/extraction、独立评测与测试，不改变当前 V0.2 Worker、
> 数据库、HTTP API、XMind 文件、React 页面。与 main 的合并严格按
> PR-030 → PR-031 → PR-032 → PR-033 → PR-034 的依赖顺序处理。

## 1. 目标与非目标

目标不是让 LLM 直接宣布“论文结论是真的”。目标是将未受信任的
LLM 输出，转换为可独立核查的 ClaimCandidate + EvidenceRef 集合。

- 有明确 DocIR 原文、ChunkManifest、页码、Block、偏移和 Quote。
- 允许模型弃答，允许报告单个无效候选，不允许发布虚假来源。
- Overlap 的 Context 只能帮助理解；至少一条引用涉及 Primary。
- 只用**精确证据集合**去重，不把相似但来源不同的实验结论合并。
- 每个候选的 status 只能是 candidate；不得直接 supported/verified。
- 独立评测使用人审黄金集；绝不从当前模型输出自动生成黄金标签。

不在本阶段：无授权论文下载、OCR、表格单元格准确率断言、科学语义支持
判定、人工审核 UI、Agent 对话、持久化 migrations、生产级限流、
自动异步恢复、费用统计以及真实大模型的质量宣称。

## 2. Review 发现与工程修复

### P0-1：LLM 不能生成“受信证据”对象

现有 ClaimCandidate / EvidenceCandidate 是未受信类型，但 PR-033
输出是可追溯的 ChunkManifest，尚没有能将候选限定到*本次 Chunk*
的强制程序。直接执行 resolve_evidence_candidate 只检查 quote 出现
在本 PDF 的某个 Block，不检查该引用是否出现在模型实际看到的 Chunk。

**修复：** RawEvidenceProposal 只允许 block_id、start_cp、end_cp、quote。
模型不能供应 revision_id、page、source hash、claim_id、status、assessment。
服务端自行绑定当前 DocumentIR 的 revision_id。
首先 resolve_evidence_candidate 校验规范化原文，再通过
_allowed_in_chunk 检查这些起止位置是否形成当前 Chunk 内连续的
Primary/Context 来源区间。任何越界、错偏移、虚构 Block、错误 Quote
都会拒绝，不能替换成模型自称的“引用已验证”。

### P0-2：重叠 Context 可能重复产生研究主张

PR-033 的 Context 复制了已经以 Primary 发布的字符。如果让模型
对任意 Context 引用创建新 Claim，边界附近的结果会重复。

**修复：** 每条候选 Claim 的证据集合必须至少包含一个在
当前 Chunk 的 Primary 来源区间内有非空交集的已解析引用，
否则 CONTEXT_ONLY_CLAIM。精准去重键为：

    (kind, origin_type, NFC + collapse whitespace + casefold(assertion),
     sorted(exact evidence_ids))

保留 ClaimOccurrence，用 chunk_id + proposal_index 映射回原输出。
两处不同实验有相同语言、但是不同原文区间时，不会被错误合并。
这是保守去重，不是语义聚类，语义合并属于后续人工审核。

### P0-3：模型不能把 Claim 直接升级为 supported

RawClaimProposal 额外字段禁止传入 support_status、assessment、
validated 等。GroundedClaimExtractor 只能通过
promote_claim_candidate 产生 candidate。独立 Validator 将任何
最终审核态直接报 LEDGER_TRUST_ESCALATION。
原文位置正确不代表数值归属、实验条件、引用前人工作是否正确；
PR-035 的独立科研语义验证才能允许状态升级。

### P0-4：必须在发起模型调用之前校验全部来源

进入 GroundedClaimExtractor.extract 时，首先完整运行
validate_chunk_manifest(document, manifest)，核查 PDF SHA、Revision、
Parser/Chunker 设置、Budget Counter、主文本覆盖、重叠来源和哈希。
任何异常均在第一笔外部调用之前失败，避免模型收到伪造或污染的
ChunkManifest。对于 tiktoken 计数生成的清单，调用方必须注入
相同 tokenizer 计数器，不能冒充默认 UTF-8 byte 预算。

### P1-5：结构化输出仍是不可信网络数据

只接受一个 JSON 对象，拒绝 Markdown 包裹、重复 JSON 键、
NaN/Infinity、模型声称审核通过的额外字段、缺少必需字段、
过长输出和超过候选数上限。Provider 响应不完整、网络调用异常等
导致整批执行失败，不能把故障伪装为“没有论文结论”。
单个错来源候选有两种显式策略：
- reject_candidate（默认）：剔除该候选，记录机器码，整体状态 review_required；
- fail_chunk：整批报错，禁止发布部分 Ledger。

分块个数、每块最大候选、最大响应字节和输入字符都有上限。
拒绝记录不原样持久化模型任意文本，降低日志污染风险。

### P1-6：Hash-only 配置追踪不足

进一步审查发现仅存 extraction_config_sha256 而不保存配置，
事后无法独立复算指纹。

**修复：** 结果清单同时保存 ExtractionConfig 和其指纹，
并将 model_id + prompt hash 纳入指纹计算；
validate_extraction_ledger 重新计算该值并检查每块候选数量。
require_primary_evidence 限制为 Literal[True]，防止调用方绕过核心
来源约束。

### P1-7：Prompt Injection 的安全边界

Prompt 明确告知模型论文文本是 UNTRUSTED SOURCE DATA。
上下文用结构化 JSON 描述 Chunk 与每个 Primary/Context Span，
可供模型复制 block_id 和 Unicode 半开字符区间。

**关键事实**：提示词本身并不能阻止 Prompt Injection。
真正的防线是运行时的字段白名单、独立引用检查、
不允许审核状态升级、显式在线许可和不将模型内容执行为代码。
当前不提供对服务器文件系统、密钥、工具或者外部网络的 Agent
执行权限。

## 3. 模块图

    DocumentIR + ChunkManifest (source-trusted after independent validation)
          ↓ validate_chunk_manifest (before any network request)
    ModelRequest (versioned system prompt + per-chunk JSON source spans)
          ↓ ClaimModel protocol
      ├─ FixtureClaimModel (default, offline/no tokens)
      └─ OpenAIClaimModel (explicit opt-in, can point to local vLLM)
          ↓ raw JSON (UNTRUSTED)
    RawExtractionResponse + RawClaimProposal
          ↓ JSON size / duplicate key / strict Pydantic Schema
    EvidenceCandidate (server-bound revision ID)
          ↓ resolve_evidence_candidate / exact source quote & hash
          ↓ _allowed_in_chunk / actual presented chunk span
          ↓ Primary citation required
    ClaimCandidate → Claim(status="candidate")
          ↓ same proposition + identical anchors dedup (conservative)
    ClaimExtractionLedger
          ↓ validate_extraction_ledger (independent import-side audit)
    Ready for PR-035 independent scientific support evaluation

### 文件

| 路径 | 职责 |
|---|---|
| extraction/contracts.py | 严格 Raw JSON、候选、拒绝、Ledger 和策略 |
| extraction/prompts.py | Prompt v1、稳定 SHA、来源片段构造 |
| extraction/providers.py | Fixture / 显式 OpenAI-compatible 接口 |
| extraction/pipeline.py | 候选解析、引用定位、Chunk 限制、保守去重 |
| extraction/validation.py | Ledger 外键、独立来源核查、候选状态与配置 hash |
| extraction/export_schema.py | 版本化 JSON Schema 产物 |
| extraction/__main__.py | 离线及显式在线 CLI，原子 JSON 发布 |
| evals/benchmarks/claim_groundtruth_v034.py | 独立人审黄金集评测 |
| tests/test_extraction_v03.py | 模型契约、攻击与工程不变量 |
| tests/test_extraction_eval_v03.py | 人审数据格式与指标回归 |

## 4. JSON 输入输出

模型 JSON:
{
  "schema_version": "claim_candidates/1.0.0",
  "claims": [{
    "kind": "numeric_result",
    "assertion": "F1 improves from 0.72 to 0.76",
    "origin_type": "author_result",
    "core_claim": true,
    "evidence": [{
      "block_id": "blk_sample",
      "start_cp": 18,
      "end_cp": 40,
      "quote": "F1 from 0.72 to 0.76"
    }]
  }],
  "abstain_reason": null
}

上面是**格式示意**，不是来自真实论文的实测数值或引用。
Span 的数字必须针对实际 DocumentIR 重新计算，不能照抄示例。

ClaimExtractionLedger schema_version=claim_extraction/1.0.0 保存：
revision_id、pdf_sha256、chunk_config_sha256、
extraction_config、extraction_config_sha256、
model_id、prompt_version、prompt_sha256；
claims、evidence、occurrences、rejected、per_chunk 和 status。

- 状态 candidate_only：有合规候选、无拒绝。
- review_required：含单项无效来源候选，绝不自动发布为 verified。
- abstained：模型明确弃答或没有 Chunk，不能解释为“论文无价值”。

## 5. 执行与权限

默认无网络：需要先有合法的 PR-033 DocumentIR + ChunkManifest，
再提供每个 chunk_id 对应的一份 RawExtractionResponse：

    pip install -e ".[dev]"
    python -m paper2xmind.extraction \
      --document output/paper.document-ir.json \
      --chunks output/paper.chunks.json \
      --responses output/mock-model-responses.json \
      --output output/paper.claim-candidates.json

显式选择 OpenAI-compatible 模型（发送 Chunk 中的原文）：

    python -m paper2xmind.extraction \
      --document output/paper.document-ir.json \
      --chunks output/paper.chunks.json \
      --provider openai --allow-online \
      --model-id <chosen-model-id> \
      --base-url <authorized-endpoint-url> \
      --output output/paper.claim-candidates.json

安全注意：只有确认模型服务和用户对文献上传的授权后才能启动在线模式。
OpenAI-compatible API 兼容性取决于目标实现；默认 CI 不发送任何论文文本。
CLI 没有缓存 API 密钥或在日志打印论文全文。客户端需配置超时/失败重试，
调用方还需根据服务条款与资源限制设置 token/cost 预算。

JSON Schema：

    python -m paper2xmind.extraction.export_schema \
      schemas/generated/v0.3/claims

## 6. 独立黄金评测

脚本 evals/benchmarks/claim_groundtruth_v034.py 接受包含以下信息的
本地 JSON Manifest：
- corpus_name 和唯一 case.id；
- DocumentIR、ChunkManifest、模型 Fixture 响应三个本地文件的相对路径，
  及各自 SHA-256；
- 每个 case 的 license_note；
- 独立标注人员提供的 gold_claims：主张、类别、来源归属和精确证据区间。

比较使用模型**未参与生成的**标注数据，指标：
- exact_surface_precision：经程序接受的 Claim 中，断言规范化及
  精确证据集合同时匹配人工黄金的比例；
- exact_surface_recall：黄金 Claim 中被上述规则匹配的比例；
- accepted_occurrences、deduplicated_occurrences、rejected_proposals；
- 提取异常必须标记 status=failed，不得作为完美分数或弃答处理。

它评估精确表达与证据位置的匹配，并不自动判断“科学上是否成立”。
人审标签质量本身仍需要独立抽检。真实授权标注论文尚未提供，因此
当前只能完成合成黄金集的工程验证，不能宣称真实论文准确率。

## 7. CI 验收矩阵

- Python 3.10 / 3.11 / 3.12；原有 Core、Backend、Frontend 回归。
- 不受信 JSON 的 duplicate key、schema、响应大小、候选数限制。
- 模型自称 supported/assessment 不通过 Schema。
- Quote 错配、Block 错配、错偏移、Chunk 外引用被拒绝。
- Context-only 不得产生独立科研候选，Context+Primary 连续 Quote 可以。
- 真实来源重复的 exact Claim 做去重；不同来源相似措辞不误合并。
- No-model/no-chunk、明确 abstain、外部 SDK/网络故障不假装成功。
- 外部篡改 Ledger 的 Claim、Occurrence、Hash 被独立审计器发现。
- 在线模式需 --provider openai 和 --allow-online 两重显式许可。
- 离线 CLI JSON 文件原子生成、失败不发布未验证半成品。
- 合成黄金评测证实：即使一个主张有真实 Quote，但断言内容错误，
  人审标注仍会将它记为 False Positive。

## 8. 剩余风险与下一阶段

- 当前模型只提取**候选**，引用“确实存在”不代表“能支持断言”。
- 标题、表格行、实验条件、负对照、引用前人工作可能仍需跨 Chunk 推理。
- 当前只保守去重 exact assertion + exact evidence set，语义同义句
  可能保留为两个未核验候选，这是刻意规避误合并。
- Prompt 只做约束，不能百分之百阻止模型生成误解或指令跟随；
  验证器会阻止伪引用或伪审核身份。
- 未实现连接线上 SQLite Revision/Job 及人工审核页面。
- 当前在线 Adapter 只按 JSON Mode 调用 OpenAI-compatible chat API，
  对特定 vLLM/Qwen 接口和模型质量未做真实端到端验收。
- 本阶段未对真实授权论文测量 Precision/Recall、延迟与成本。

**PR-035 — Evidence Verification & Claim Reconciliation**：
独立评估 Claim 的原文语义蕴含、数字/单位、实验条件、作者归属、
引用前人工作、矛盾与审核签名；只有在可信审核者授权与记录下，
才允许从 candidate 向 supported/unsupported/contradicted 等状态过渡。


### P1-8：请求级指纹与在线适配器合约

每条 ChunkExtractionRecord 还保存 request_sha256，内容来自实际 ModelRequest.user_prompt。独立 validator 用相同 ChunkManifest、固定 prompt version 和 model_id 重新生成请求并复算哈希，拒绝篡改输入记录。response_sha256 记录原始回复字节摘要；仅凭哈希无法恢复回复本身。在线适配器通过模拟 SDK 的无网络测试验证 JSON Mode、temperature=0、max_tokens 和参数传递；不声称真实模型兼容性或语义准确度已验证。
