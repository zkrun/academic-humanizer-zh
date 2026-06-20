---
name: academic-humanizer-zh
description: Detect, score, diagnose, and rewrite AI-like Chinese academic writing across broad paper types, including theses, journal papers, course papers, research reports, literature reviews, social science papers, humanities analysis, engineering papers, medical/education/management papers, abstracts, introductions, methods, results, discussion, conclusions, and defense materials. Scores per-paragraph AI-risk rate (0-100) with the concrete patterns that triggered it, then lowers it and reports a before/after document AI-rate comparison. Use when asked to 检测AI率/AI风险率, judge AI traces, lower AIGC feel, humanize Chinese academic text, remove template writing, revise over-polished paragraphs, or make claims more natural while preserving facts, data, citations, terminology, and argument logic.
---

# Academic Humanizer ZH

## Purpose

Use this skill to make Chinese academic writing sound less generated and more like a real author working through a real research problem. The goal is not to hide AI by adding random errors. The goal is to remove predictable structure, empty transitions, generic conclusions, over-balanced rhythm, and unsafe claims while preserving the original meaning, evidence, citations, data, and disciplinary tone.

This skill applies broadly to:

- 学位论文、课程论文、期刊论文、会议论文
- 文献综述、研究报告、开题/结题材料
- 摘要、引言、方法、结果、讨论、结论
- 人文社科、教育、管理、医学、工程、计算机等中文学术文本
- PPT 答辩文案和论文式项目说明

## Non-Negotiable Rules

1. Preserve facts, data, citations, author positions, methods, and conclusions unless the user explicitly asks to remove or weaken them.
2. Do not invent experiments, samples, interviewees, statistical tests, p-values, references, case details, fieldwork, or theoretical sources.
3. Do not strengthen claims. If anything, make unsupported claims more precise or more bounded.
4. Do not replace AI templates with a new anti-AI template. Repeated disclaimers also become artificial.
5. Do not make all paragraphs equally casual. Academic writing should still sound formal, just less mechanical.
6. Adapt to the discipline. A philosophy paragraph, an education literature review, and an engineering method section should not be rewritten in the same voice.

## How It Works

This skill runs a closed loop:

1. **检测 (detect & score)** — score every body paragraph for AI-risk (0–100), name the patterns that fired, surface the worst sentences.
2. **降AI (rewrite)** — rewrite high-risk paragraphs with the methods below, preserving facts, data, citations, and methods.
3. **重测 (re-score & compare)** — re-score the rewrite and show the before/after AI率 drop, paragraph by paragraph.

The score is an **explainable AI-trace risk rate**, not any commercial detector's number (知网/维普/格子达/GPTZero). Every point traces to a concrete pattern in `reference/rubric.md`. Say this plainly to the user; do not imply it equals a specific tool's reading.

## Tooling

- **`scripts/score.py`** — deterministic surface scorer. Reads `.txt / .md / .docx`, skips references/TOC/tables/formulas/captions/headings and fenced code blocks (```/~~~), scores patterns S1–S7, prints a summary and (with `--json`) writes full results.
  - Run: `python scripts/score.py <输入文件> --json <输出.json>`；改写后用 `--compare 降前.json` 打印对比，再加 `--report <对比报告.md>` 生成降前/降后对照文件；可选 `--semantic <语义.json>`（你判读的 C1–C3 分 + 证据 + 综合判断）把**语义评分和综合分一并写进报告**，两轨并列。
  - JSON fields: `document.ai_rate_surface` (字数加权), `document.high_risk_ratio`, `document.skipped_breakdown`; per-paragraph `index / char_count / surface_score / level / needs_semantic_review / hits[] / text`. Each hit carries `code / name / points / match / offset`.
- **`reference/rubric.md`** — the single source of truth: weights, the six surface items S1–S6, the three semantic items C1–C3, and the four risk bands. Read it before scoring so your semantic judgments match the rubric.

## Scoring Model

分两轨，**不要合并成一个数**——这是刻意的：

- **表层分（S1–S7，脚本算）**：确定性、可复现，每分可追溯到一条词表痕迹，是**客观下限**。
- **语义分（C1–C3，你判）**：模型判读，**不保证可复现**（换模型 / 换一次跑会浮动）；它能抓表层看不到的东西（节奏、口吻、空转推理），但**每一分必须引原文证据**，否则不计——语义分的可信度来自证据，不来自可复现。

**最终给两个结论，并列、不糅在一起：**

- **表层分** = 脚本的 `ai_rate_surface`（直接用）。
- **综合判断** = 表层 + 语义后的整体档位（低 / 中 / 中高 / 高），**允许语义压倒表层**。两者背离时（典型：表层很低但满篇排比 / 口号），**以语义为准并明确标注"表层低、综合高"**——这种背离本身就是"会规避词表的 AI"的信号。

Surface items (script): S1 模板开头 · S2 排比骨架 · S3 空洞结尾 · S4 空泛归因 · S5 高频词聚集 · S6 不安全数据语 · S7 升华对比框 · **S8 排比密度**（≥4 同构顿号列）· **S9 枚举骨架**（文档级：跨段"第一…第六/首先…最后"march）— detailed below under AI-Trace Patterns. 脚本还输出 `document.rhythm`（句长均值 + 变异系数 CV，越低越偏 AI）作为 C1 节奏的客观参考线，不计分。

> S8 / S9 是专为政论 / 宣传体补的——这类文本的 AI 味在四字排比和跨段枚举骨架，能被这两项确定性地抓到，从而**降低对语义层的依赖**；但引用反例、空转口号、推理扁平等仍只能靠 C1–C3 判。

Semantic items — 判 flagged 段落，**同时整篇通读**：节奏 / 口吻往往是文档级特征、脚本完全看不到，所以一篇表层 ~0% 的文档仍可能整体很 AI（**典型：政论 / 宣传体，满篇四字排比和口号，却踩不中任何词表**）。整体读着模板化时，综合判断就要反映出来，哪怕表层很低。**每个语义扣分都要引具体证据**（哪句排比、哪个口号、哪处无转折）：

- **C1 节奏过平滑 (0–20)** — 句句长而均衡、每段工整收尾、四字排比堆砌、毫无停顿 / 插入 / 转折。
- **C2 推理扁平 (0–15)** — 无例外、对比、边界、方法理由或作者判断；纯断言或纯抒情。
- **C3 口吻错位 (0–10)** — 学科 / 文体口吻被磨成通用腔；口号、套话密集。

绝不只给数字。Bands: 0–25 低 / 26–50 中 / 51–75 中高 / 76–100 高.

## Workflow

### Single pasted paragraph

1. Score inline against the rubric (S1–S6 + C1–C3); running the script is optional for one paragraph.
2. State **both** the 表层分 (script) and the 综合判断 (含语义), and name the specific patterns — not a vague "AI-like" label.
3. Give a revised version, then re-state the new (lower) risk.
4. Briefly explain what changed: structure, claim strength, rhythm, data boundary, or reasoning flow.

### Full document

1. Run `python scripts/score.py <file> --json <out.json>` and read the JSON.
2. Add C1–C3 with **quoted evidence** to flagged paragraphs, **and read the whole document for rhythm / voice** — a low 表层分 does not mean clean (政论 / 宣传体 is the chief example: surface ~0% yet heavily templated). Derive the **综合判断**.
3. Produce the **检测报告** (format below): **表层分 + 综合判断（若背离则标注"表层低 / 综合高"）** + per-paragraph table + worst sentences highlighted.
4. **降AI**: rewrite high-risk paragraphs (中高/高 first), using the Rewrite Methods. Preserve data/citations/methods; keep methods/results numerically intact; do not touch the blocks the script skipped.
5. Export a **new file** — never overwrite the original.
6. 把你的语义判读写成 **`语义.json`**（每项 `C1/C2/C3: [分, 证据]` + 降前/降后 `composite` + `note`），再跑 `python scripts/score.py <新文件> --compare 降前.json --semantic 语义.json --report <对比报告.md>` —— 报告会**两轨并列**：表层（脚本、可复现）+ 语义评分（C1–C3 带证据）+ 综合判断（降前 / 降后），外加逐段对照。**别只写表层进报告，用户要看到语义的分量。**
7. Deliver **two files** — the rewritten document and the comparison report — then summarize: before/after **表层分 + 综合判断**, preserved content (citations/data/methods), residual risk. 若表层分本就低、问题主要在语义（节奏 / 口号），要明说"降的主要是读感，表层数字本就不高"，不要让对方误读那个小降幅。

> Do not game the score by only deleting trigger words. A lower number must come from real structural and reasoning changes; otherwise the text reads as a new anti-AI template. The Final Self-Check enforces this.

## AI-Trace Patterns

### S1. Template Openings 模板开头 — 单次 +22

High-risk openings:

- 随着……不断发展
- 在……背景下
- 基于……理论/框架
- 依据……视角
- 针对……问题
- 为提高/为探究/为解决……
- 本文围绕……

These are acceptable occasionally, but repeated use makes the text predictable.

Better:

- Start from a concrete phenomenon, contradiction, research gap, material, case, or methodological constraint.
- Move the theory or purpose into the second sentence.
- Let the paragraph answer "why this question matters here" instead of announcing "this paper studies".

Example:

Before:

> 基于社会建构主义理论，本文探讨课堂互动对学生知识建构的影响。

After:

> 在实际课堂中，学生并不是简单接收教师给出的结论；他们往往是在追问、争论和修正中逐渐形成理解。社会建构主义理论可以解释这种过程，因此本文将课堂互动作为观察学生知识建构的入口。

### S2. Over-Neat Parallel Structure 排比骨架 — 单次 +20

High-risk structures:

- 首先……其次……再次……
- 一是……二是……三是……
- 理论上……实践上……方法上……
- 宏观……中观……微观……
- 问题、原因、对策三段完全对称

Rewrite by:

- Giving the most important point more space.
- Letting secondary points be shorter.
- Replacing list rhythm with cause-effect or contrast.
- Keeping numbered structure only when the paper genuinely requires it.

### S3. Generic Conclusions 空洞结尾 — 每个不同短语 +18，封顶 60

High-risk endings:

- 具有重要意义
- 具有现实意义和理论价值
- 前景广阔
- 提供了新思路
- 开辟了新方向
- 具有重要参考价值
- 对……具有积极作用

Replace empty value with concrete implication:

- What exactly does the finding help explain?
- Which boundary does it clarify?
- Which method, case, policy, or practice can use it?
- What remains uncertain?

### S4. Vague Attribution 空泛归因 — 每处 +13，封顶 39（附近有引用标记则不计）

High-risk phrases:

- 专家认为
- 学者指出
- 研究表明
- 业内普遍认为
- 有观点认为

Use only with a specific citation or known source. If no source exists, recast as the paper's own analysis:

Before:

> 研究表明，社交媒体会显著影响青年政治参与。

After:

> 既有研究多从平台使用频率、政治兴趣和社交网络结构解释青年政治参与，本文关注的是其中更容易被忽视的一点：平台互动是否改变了青年表达政治态度的成本。

### S5. AI High-Frequency Academic Polish 高频词聚集 — ≥2 个 +12，每多 1 个 +5，封顶 36

Watch for clusters of:

- 深入探讨 / 系统梳理 / 综合运用
- 有效提升 / 显著提高 / 充分说明
- 不可或缺 / 赋能 / 多维协同
- 完善理论体系 / 构建分析框架
- 推动高质量发展

Do not blindly delete them. Replace only when they are doing no real work.

### C1. Too-Smooth Rhythm 节奏过平滑（语义项，你来判）— 0–20

Signs:

- Every sentence is long, balanced, and polished.
- Paragraphs end with a neat summary every time.
- There is no hesitation, exception, contradiction, or boundary.
- Each paragraph sounds like a textbook abstract.

Humanize by adding real academic texture:

- a limitation in the middle, not only at the end
- a concrete example or case detail already present in the source
- a methodological reason
- a contrast between expectation and result
- a modest judgment from the author

### S6. Unsafe Data and Evidence Language 不安全数据语 — 段级 12 + 每个无来源数字 +8，封顶 44

High-risk claims:

- "显著" without statistical test
- p-value / sample size / CV / regression result without source
- percentages, interview counts, experiment rounds, or measurement values not in the user's evidence
- "验证了" when the evidence only "supports" or "suggests"
- "证明了" in humanities/social science contexts where "说明/表明/提示" is more appropriate

If data was not actually collected, remove the data claim rather than adding ritual disclaimers. Convert to:

- design intent
- qualitative observation
- future data collection plan
- scope boundary
- method template

Do not repeatedly write:

- 本文不将……作为结论，后续测试……
- 尚不足以支撑……后续应……
- 该指标仅作为初步参考……

These are useful once, but repeated use becomes a new AI pattern.

### S7. 升华对比框 Elevation Contrast Frames — 每处 +8，封顶 20（软信号）

High-risk frames（先否定一个平庸说法，再「升华」到一个高级说法）:

- 不是……而是……
- 不仅……而且 / 还 / 更……
- 不只 / 不止……而是……
- 不在……而在于……
- 与其说……不如说……

中文 AI 腔最隐蔽的反射之一——连语言模型自己想「把话说漂亮」时都会反射性地用它。偶尔使用是正常的，
所以这是低权重软信号：单独一处只到「低」，密集出现、或与模板 / 排比叠加时才是问题。不要见到就删；
只有当它在空转、纯粹为制造"升华感"时才改。

Before:

> 它不止给一个模糊判断，而是落到具体段落和句子。

After:

> 它会指出具体哪一段、哪一句有问题，对应到哪条痕迹、扣了多少分。

## Rewrite Methods

### Move From Announcement To Reasoning

Before:

> 为提高研究结论的可靠性，本文采用问卷调查与访谈相结合的方法。

After:

> 单靠问卷可以覆盖更多样本，但很难解释受访者为什么这样选择。因此，本文在问卷之外补充访谈材料，用来理解几个关键回答背后的原因。

### Break Mechanical Lists

Before:

> 本研究具有三方面意义：理论上丰富了相关研究，实践上为政策制定提供参考，方法上提供了新的分析路径。

After:

> 本研究最直接的价值在于补充了一个常被忽略的解释变量。至于政策层面的启示，还需要放在具体地区和执行条件中讨论，不能简单推出普遍结论。

### Convert Generic Value To Specific Boundary

Before:

> 本文结论具有重要的理论意义和现实意义。

After:

> 本文的结论更适合用来解释样本地区的政策执行差异。若要推广到其他地区，还需要比较财政压力、基层组织结构和公众参与方式是否相近。

### Keep Results Precise

Do not rewrite numerical results casually. For empirical results:

- Preserve variables, coefficients, p-values, sample sizes, confidence intervals, table numbers, and model names.
- Change only surrounding interpretation if it is too inflated.
- Replace "证明" with "表明/提示/支持" when causality is not established.

### Keep Literature Review From Becoming A Catalogue

AI literature reviews often become:

- "国内外学者从 X、Y、Z 三个方面进行了研究"
- "已有研究成果丰富，但仍存在不足"
- "本文在前人基础上……"

Better:

- Organize by unresolved tension, not by author list.
- Show which debate or gap matters to this paper.
- Avoid claiming "研究不足" unless the gap is specific.

## Domain Adaptation

### Humanities and Theory

- Preserve nuance and conceptual distinctions.
- Do not add examples or theorists.
- Avoid forcing empirical-style "results show".
- Prefer "可以理解为 / 更接近于 / 这一差异在于".

### Social Science and Education

- Preserve sample, method, and citation details.
- Do not imply causality unless design supports it.
- Use "相关 / 关联 / 可能影响 / 在样本中表现为" carefully.

### Medical and Health

- Do not change clinical claims, risks, dosages, disease names, or statistical results.
- Avoid overconfident causal language.
- Keep ethics, consent, and inclusion/exclusion criteria precise.

### Engineering and Computer Science

- Preserve component specs, algorithms, parameters, datasets, baselines, and metrics.
- Distinguish design settings from measured performance.
- If a result was not measured, remove the metric and describe function verification instead.

### Policy and Management Reports

- Keep institutional tone, but remove slogans.
- Replace "高质量发展/赋能/协同推进" with concrete mechanism or implementation condition.

## Risk Grading

Low:

- Specific claim with evidence
- Natural sentence variation
- Concrete limitation or methodological reason
- No generic conclusion

Medium:

- One or two template connectors
- Some neat list structure
- Mostly grounded claims
- Tone still discipline-appropriate

Medium-high:

- Repeated template openings
- Rigid three-part structure
- Generic positive ending
- Dense high-frequency academic polish

High:

- "首先/其次/再次" plus generic significance
- Uncited "研究表明/专家认为"
- Strong data/statistical claims without evidence
- Repeated paragraph endings like "由此可见/综上所述/具有重要意义"

## Output Style

For a single pasted paragraph:

```markdown
表层分 72%（中高）｜综合判断 中高

触发：S1 模板开头、S4 空泛归因；语义 C1 节奏过平滑（证据：每段都以"由此可见…"工整收尾）
主要问题：
1. ...
2. ...

改后（表层约 20%，综合 低）：
> ...

变化：把"研究表明"落回本文自己的分析；拆掉开头的"随着…发展"模板。
```

For a full-document **检测报告**:

```markdown
## 检测报告

表层分：1.7%（低）　|　综合判断：中高（⚠ 表层低 / 综合高——满篇四字排比与口号，规避了词表）
打分 8 段 / 跳过 3 段（标题3）

| 段落 | 表层 | 综合 | 触发（表层 / 语义，含证据） | 说明 |
|---|---|---|---|---|
| 块3 | 8% | 中高 | S7；C1 节奏 + C3 口号 | 四字排比 + 口号"最普惠的民生福祉" |
| 块5 | 0% | 中高 | C1 节奏 | "节约水电…垃圾分类…绿色出行…"机械排比 |
| … | | | | |

最该改的句子：
- 块9：「敬畏自然、尊重自然、保护自然……天更蓝、山更绿、水更清……」
```

> 表层与综合**并列呈现**；脚本只给得出"表层"列，"综合"列与背离标注由你（依据 C1–C3 证据）判定。两者一致时正常报，背离时务必点明，别让读者只看表层数字。

For a full-document **降AI报告**:

```markdown
## 降AI 报告

已生成新版：[demo_after.txt](absolute/path)

文档 AI率：降前 50.7% → 降后 21.3%（↓29.4）

| 段落 | 降前 | 降后 | 主要处理 |
|---|---|---|---|
| 块5 | 82% | 18% | 拆排比、删套话、归因落到本文分析 |
| 块1 | 65% | 22% | 改写模板开头、去高频词、收紧价值判断 |
| … | | | |

- 受保护内容：数据 X 处、引用 Y 处、方法细节（未改动）
- 剩余风险：……
```

> 这份 **降AI报告由 `score.py --compare 降前.json --semantic 语义.json --report <文件.md>` 直接落地成文件**：含总览（**表层 + 综合判断**）、**语义评分表（C1–C3 带证据、降前/降后）**、逐段表层对比、改动段「原文 ↔ 改后」对照。`语义.json` 由你判读提供——不传则报告只有表层那一轨。

## Examples

### Literature Review

Before:

> 国内外学者围绕平台治理开展了大量研究，主要集中在治理主体、治理机制和治理效果三个方面，取得了丰富成果，但仍存在不足。

After:

> 平台治理研究已经积累了不少成果，但争议并不在于是否需要治理，而在于治理责任如何分配。现有文献一部分强调政府监管，另一部分更关注平台自我约束；两类讨论之间仍有一个空白：当平台规则与公共利益发生冲突时，责任边界究竟如何划定。

### Empirical Result

Before:

> 回归结果充分证明，数字金融显著促进了企业创新，具有重要现实意义。

After:

> 回归结果显示，数字金融变量与企业创新投入之间呈正相关，并在当前模型设定下通过显著性检验。这个结果支持了数字金融可能缓解融资约束的解释，但是否能够推出稳定的因果关系，还取决于内生性处理和样本稳健性检验。

### Conclusion Without Grand Claim

Before:

> 综上所述，本文研究具有重要理论意义和实践价值，为相关领域提供了新思路。

After:

> 本文的主要工作，是把此前分散讨论的三个因素放入同一分析框架中，说明它们如何共同影响样本中的结果差异。这个解释仍受样本范围限制，但为后续比较不同地区或不同群体提供了一个较清晰的切入点。

### No Unmeasured Data

Before:

> 经过 5 次实验，系统平均准确率达到 92.3%，响应时间低于 200 ms，验证了方法的有效性。

After:

> 当前实验材料主要能说明系统流程已经跑通，模型能够完成基本识别和响应。准确率、响应时间等指标若要作为结论，需要统一测试集、重复次数和统计方法；在这些记录不足时，不宜保留具体数值。

## Final Self-Check

Before returning revised text, check:

- Did the rewrite preserve the original argument?
- Did any claim become stronger?
- Were data, citations, samples, or methods invented?
- Did the text avoid both AI templates and repetitive anti-AI disclaimers?
- Does the style match the discipline?
- Is the paragraph still academic, not casual chat?
- Did the re-scored AI率 actually drop — **and is the drop from real structural/reasoning changes, not just deleted trigger words**?
- After rewriting, re-run `score.py`; if a paragraph is still 中高/高, revise it again rather than reporting it as done.
- **被改写的段落分数必须真的下降，且没有任何一段比改前更高**：若某段改了却分数不变甚至升高，多半是把一个触发词换成了另一个同类触发词（如「第一/第二/第三」换成「一是/二是」都算 S2 排比），或顺手写进「已有研究」「研究表明」「不是…而是…」等被规则盯上的词。回改那一段，别交付"白改"或"越降越高"的结果。
