# V0.3 PR-030 · 深度设计审查与实现记录

基线：feat/v0.2-pipeline-reliability（PR #1 尚未合并）
当前分支：feat/v0.3-pr030-domain-contract
目标：冻结 Evidence V1 领域契约，保证 V0.2 的 Web、任务和 XMind 行为不变。

## 已确认并修复的设计缺陷

### P0-1：候选引用不能冒充有效出处

旧设计把模型产出的引文候选与已验证 EvidenceRef 混用，
容易让模型生成的页码或引用状态被下游当成客观事实。
新设计分成 EvidenceCandidate（未经信任）、
EvidenceRef（包含确切起止坐标与哈希）、
ResolvedAnchor（经 DocumentIR 的确定性验证）。
验证得到 valid 仅说明引文的字符串、页码和 hash 匹配。
不表示 Claim 的科学含义已经成立。语义判定由后续独立评测负责。

### P0-2：跨实体约束不能只靠字段类型

DocumentIR 增加实际的文档级校验：PDF 页索引连续、
Block ID 唯一、reading_order 唯一、BBox 未越页、
Section 的父子关系和 block 成员一致。
另外 validate_knowledge_references 对 Node、Claim、Evidence 的
所有外键、重复引用和虚假 verified 状态进行检查。

### P0-3：旧树升级绝不制造证据

adapt_legacy_tree 兼容 V0.2 AI JSON 或 XMind 归一树。
所有旧节点明确标记 legacy_unverified，丢弃输入中声称的
verified/claim_ids/evidence 等不可信字段，保留名字、描述及子树顺序。
同名兄弟节点通过稳定路径区分 ID。

### P1-1：字符偏移与版本一致性

采用 nfc_lf_v1：保留空格与段落，仅做 Unicode NFC 与换行统一。
Evidence offset 是 Unicode code point，不是 UTF-8 byte，也不是
Web JS 的 UTF-16 code unit。emoji、组合音符、CRLF 均需黄金用例。
修改规范化策略需要新版本、新偏移和新 hash。

### P1-2：PDF 坐标约定

DocumentPage 仅接受 top_left_pt，Block bbox 必须属于该页尺寸。
解析适配器负责把 Docling、PyMuPDF 的坐标转换到这个标准；
当前 PR 只定义契约，不假装已经修复双栏、旋转 CropBox 的来源变换。
具体阅读顺序与版面性能属于 PR-031/032。

## 本次交付模块

- paper2xmind/domain/document_ir.py：DocumentIR、Page、Block、Section、Source/Parser provenance。
- paper2xmind/domain/evidence.py：未信任候选、精确引用、重复 quote 歧义和 Unicode 区间验证。
- paper2xmind/domain/claims.py：Claim、外部审核记录、MindNode。
- paper2xmind/domain/validation.py：跨实体外键、状态门禁、确定性 UTF-8 JSON。
- paper2xmind/domain/legacy_adapter.py：旧节点到 legacy_unverified 的兼容转换。
- paper2xmind/domain/export_schema.py：Pydantic JSON Schema 生成。
- tests/test_domain_v03.py：本模块的合成黄金测试。
- .github/workflows/v03-domain-ci.yml：Python 3.10/3.11/3.12 + V0.2 核心/后端回归 + Web 构建。

## 兼容、边界与后续 PR

本次没有把新领域模型接线到 Worker，也没有改变现有 API、数据库或
V0.2 XMind 文件格式。只有后续 PR-031（PDF Block Parser）和 PR-034/035
（Claim extraction/Verification）通过质量评测后，才能逐步启用证据分析。

注意 SupportAssessment 字段记录谁做了判定，但不能防止恶意调用者伪造评测者；
上层服务必须只允许独立评测流程写入 supported 状态，
并配置用户授权与不可篡改审计。此项属于后续服务层工作。

在根目录执行：
    pip install -e ".[dev]"
    python -m pytest tests/test_domain_v03.py -q
    python -m paper2xmind.domain.export_schema schemas/generated/v0.3

评测不变量：DocumentIR 版本严格受控；非法引用不得被登记为 valid；
老数据不能默认受信；不允许以引用存在取代科学语义审查。

下一模块：PR-031 PyMuPDF Block Parser，包括可复核页码与 bbox、旋转/CropBox
标准化、文本阅读顺序与合成 PDF 黄金测试。
