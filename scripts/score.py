#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
academic-humanizer-zh / score.py

确定性的「AI 表层痕迹」打分器。
读取 .txt / .md / .docx，分段、跳过非正文块（参考文献/目录/表格/公式/图表标题/标题），
对每个正文段落按 reference/rubric.md 的权重表打表层分（S1-S6），输出 JSON + 可读摘要。

语义层（C1-C3：节奏/推理/口吻）由 Claude 在 skill 流程里补判，本脚本只负责可复现的表层分。
分数是「AI 痕迹风险分」，不等同任何商用检测器读数。

用法:
    python score.py 论文.docx --json 结果.json
    python score.py 论文.txt                 # 只打印摘要
    python score.py 论文.md --json 结果.json --quiet
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ==========================================================================
# 词表与权重（与 reference/rubric.md 保持一致；改这里要同步改 rubric.md）
# ==========================================================================

# S1 模板开头（段首匹配），单次 +22
S1_POINTS = 22
S1_PATTERNS = [re.compile(p) for p in [
    r"随着[^。！？]{0,30}?(不断|日益|快速|迅速|持续)?(发展|提升|进步|普及|推进|增长)",
    r"在[^。！？]{0,25}?背景下",
    r"基于[^。！？]{0,20}?(理论|框架|视角|模型|方法)",
    r"依据[^。！？]{0,20}?视角",
    r"针对[^。！？]{0,20}?(问题|现象|需求|挑战|不足)",
    r"为(了)?[^。！？]{0,20}?(提高|提升|探究|探讨|研究|解决|实现|满足|应对)",
    r"本文(围绕|针对|基于|旨在|聚焦|拟)",
]]

# S2 排比骨架（成套出现才算），单次 +20
S2_POINTS = 20
S2_SETS = [
    ["首先", "其次"],
    ["一是", "二是"],
    ["理论上", "实践上"],
    ["宏观", "中观"],
    ["第一", "第二", "第三"],
    ["一方面", "另一方面"],
]

# S3 空洞结尾 / 综述套话，每个不同短语 +18，封顶 60
S3_PER, S3_CAP = 18, 60
S3_PATTERNS = [re.compile(p) for p in [
    r"具有[^。！？]{0,2}(重要|现实|理论|参考|深远|积极|广泛)[^。！？]{0,8}(意义|价值|作用)",
    r"前景[^。！？]{0,4}广阔",
    r"提供了?[^。！？]{0,6}(新的)?(思路|借鉴|参考|方向|启示)",
    r"开辟[^。！？]{0,8}方向",
    r"综上所述",
    r"由此可见",
    r"总而言之",
    r"不言而喻",
    r"取得了?[^。！？]{0,6}(丰富|丰硕|大量|长足)?[^。！？]{0,2}(成果|进展)",
    r"但仍?存在[^。！？]{0,6}(不足|问题|空白|局限)",
    r"在前人[^。！？]{0,4}基础上",
]]

# S4 空泛归因，每处 +13，封顶 39（±30 字内有引用标记则不计）
S4_PER, S4_CAP = 13, 39
S4_PATTERNS = [re.compile(p) for p in [
    r"专家认为",
    r"学者(普遍|纷纷)?(认为|指出)",
    r"研究(表明|显示|发现|证明)",
    r"业内普遍认为",
    r"有(观点|学者|研究)认为",
    r"大量研究(表明|证明|显示)",
    r"国内外(众多|许多|不少)?学者",
    r"(已有|现有)研究",
]]
CITATION_MARK = re.compile(
    r"[\[［]\s*\d+\s*[\]］]|[（(][^（）()]{0,30}(19|20)\d{2}[^（）()]{0,10}[）)]"
    r"|等[\[［]?\s*\d|参见|详见"
)

# S5 高频润色词，≥2 个 +12，每多 1 个 +5，封顶 36
S5_BASE, S5_STEP, S5_CAP = 12, 5, 36
S5_PATTERNS = [re.compile(p) for p in [
    r"深入(探讨|分析|研究|剖析)",
    r"系统(梳理|阐述|总结)",
    r"综合运用",
    r"有效(提升|促进|推动)",
    r"显著(提高|改善)",
    r"充分(说明|体现|发挥)",
    r"不可或缺",
    r"赋能",
    r"多维(协同|联动|融合)",
    r"完善[^。！？]{0,6}体系",
    r"构建[^。！？]{0,6}框架",
    r"推动[^。！？]{0,8}高质量发展",
    r"提供[^。！？]{0,6}新动能",
    r"保驾护航",
    r"重要抓手",
]]

# S6 不安全数据语（段级），12 + 8×数字个数，封顶 44
S6_BASE, S6_STEP, S6_CAP = 12, 8, 44
S6_PATTERNS = [re.compile(p) for p in [
    r"验证了",
    r"证明了",
    r"充分证明",
    r"完全证明",
    r"显著(提高|提升|改善|促进|增强|增加|降低|减少|下降)",
]]
NUMBER_NEAR = re.compile(
    r"\d+(\.\d+)?\s*%|\d+\.\d+|\d+\s*(次|例|人|组|轮|份|项|个百分点|倍|毫秒|秒|分钟|ms|km|cm|mm|kg|MB|GB)")
SOURCE_MARK = re.compile(
    r"表\s*\d|图\s*\d|见\s*[表图]|[pP]\s*[<>=]|[Nn]\s*=|样本量|置信区间"
    r"|显著性检验|[tF]\s*检验|卡方|回归(系数|结果)"
)

# S7 升华对比框（软信号），每处 +8，封顶 20
# 「先否定一个平庸说法、再升华到高级说法」的固定句式。偶尔也是正常表达，故低权重，叠加/成簇才显著。
S7_PER, S7_CAP = 8, 20
S7_PATTERNS = [re.compile(p) for p in [
    r"不是[^。！？\n]{1,30}?而是",
    r"不仅[^。！？\n]{1,30}?(而且|还|也|更)",
    r"不[只止][^。！？\n]{1,30}?(而是|还|更|也)",
    r"不在[^。！？\n]{1,25}?而在",
    r"与其说[^。！？\n]{1,30}?不如说",
    r"与其[^。！？\n]{1,25}?不如",
]]


# ==========================================================================
# 文档读取
# ==========================================================================

# 已知的二进制/非纯文本格式：明确拒绝，避免被当文本硬读成乱码、给出无意义的分数
BINARY_EXT = {
    ".doc": "旧版 Word（.doc）", ".pdf": "PDF", ".rtf": "RTF", ".wps": "WPS（.wps）",
    ".ppt": "PowerPoint", ".pptx": "PowerPoint", ".xls": "Excel", ".xlsx": "Excel",
    ".odt": "OpenDocument（.odt）",
}


def read_blocks(path: Path):
    """返回 [{'text':..., 'style':...}]，按文档顺序。"""
    ext = path.suffix.lower()
    if ext == ".docx":
        return _read_docx(path)
    if ext in BINARY_EXT:
        sys.exit(f"不支持 {BINARY_EXT[ext]} 格式：请在 Word/WPS 里「另存为」.docx，或导出为 .txt 后再运行。")
    return _read_text(path)


def _read_docx(path: Path):
    try:
        import docx
    except ImportError:
        sys.exit("缺少 python-docx：请先运行  python -m pip install python-docx")
    doc = docx.Document(str(path))
    blocks = []
    for p in doc.paragraphs:
        t = p.text.strip()
        if t:
            style = (p.style.name if p.style else "") or ""
            blocks.append({"text": t, "style": style})
    return blocks


def _read_text(path: Path):
    """按 Markdown 结构分段：识别 ``` / ~~~ 代码围栏（整体作为一个"代码块"，后续会被跳过），
    其余按空行分段；围栏边界同时切断段落，避免示例与紧邻的说明文字粘连。"""
    data = path.read_bytes()
    if b"\x00" in data[:8192]:            # 出现 NUL 字节，几乎可断定是二进制文件
        sys.exit(f"“{path.name}” 看起来是二进制文件、不是纯文本；若是 Word/PDF，请先另存为 .docx 或导出为 .txt。")
    raw = None
    for enc in ("utf-8-sig", "gb18030"):  # 先 UTF-8，再 GBK/国标（中文 .txt 常见编码）
        try:
            raw = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if raw is None:
        raw = data.decode("utf-8", errors="replace")
    blocks = []
    prose = []
    code = []
    in_fence = False
    fence_re = re.compile(r"^\s*(```|~~~)")

    def flush_prose():
        nonlocal prose
        if prose:
            t = re.sub(r"\s*\n\s*", "", "\n".join(prose)).strip()  # 段内换行合并（中文不加空格）
            if t:
                blocks.append({"text": t, "style": ""})
            prose = []

    for line in raw.split("\n"):
        if fence_re.match(line):
            if not in_fence:                       # 围栏开始：先收尾正文
                flush_prose()
                in_fence, code = True, [line]
            else:                                  # 围栏结束：整块存为代码
                code.append(line)
                blocks.append({"text": "\n".join(code), "style": "代码块"})
                in_fence, code = False, []
            continue
        if in_fence:
            code.append(line)
        elif line.strip() == "":
            flush_prose()
        else:
            prose.append(line)

    if code:                                       # 未闭合的围栏
        blocks.append({"text": "\n".join(code), "style": "代码块"})
    flush_prose()
    return blocks


# ==========================================================================
# 跳过规则
# ==========================================================================

REF_HEADING = re.compile(r"^(参考文献|references|致\s*谢|附\s*录|acknowledge?ments?)", re.I)


def is_reference_heading(text):
    t = re.sub(r"^[#＃\s\d.、]+", "", text).strip()
    return bool(REF_HEADING.match(t)) and len(t) < 14


def skip_reason(text, style, min_len):
    if style == "代码块":
        return "代码块"
    t = text.strip()
    if is_caption(t):
        return "图表标题"
    if is_toc(t):
        return "目录"
    if is_table_row(t):
        return "表格"
    if is_formula(t):
        return "公式"
    if is_heading(t, style):
        return "标题"
    if len(t) < min_len:
        return "过短"
    return None


def is_caption(t):
    return bool(re.match(r"^(图|表|Figure|Table|Fig\.?)\s*[\d一二三四五六七八九十]", t, re.I)) and len(t) < 45


def is_toc(t):
    return bool(re.search(r"(\.{3,}|…{2,}|·{3,})\s*\d+\s*$", t))


def is_table_row(t):
    if "\t" in t and len(t) < 90:
        return True
    if t.count("|") >= 2:
        return True
    stripped = re.sub(r"[\d\s.,%±\-—~()（）/:：、|]+", "", t)
    return bool(t) and len(stripped) / max(1, len(t)) < 0.30 and len(t) < 90


def is_formula(t):
    if t.startswith("$") or any(s in t for s in ("\\frac", "\\sum", "\\int", "\\sqrt")):
        return True
    core = re.sub(r"[*_`#>~]", "", t).strip()        # 去掉 Markdown 强调/标记符号
    if not core or len(core) > 50:                    # 公式通常很短
        return False
    math = len(re.findall(r"[=+\-*/^∑∫√≤≥±×÷∈∝≈]", core))
    words = len(re.findall(r"[A-Za-z一-鿿]", core))
    return math >= 3 and words <= 4                   # 符号多、自然语言字符极少，才算公式


def is_heading(t, style):
    if style and style.lower().startswith(("heading", "title", "标题")):
        return True
    if t.startswith("#"):
        return True
    if re.match(r"^第[一二三四五六七八九十百零\d]+[章节篇部分讲]", t):
        return True
    if re.match(r"^\d+(\.\d+)*[\s、.．]", t) and len(t) <= 30 and not re.search(r"[。！？.!?；;]$", t):
        return True
    if len(t) <= 18 and not re.search(r"[。！？.!?；;，,、]", t):  # 短行、无标点 -> 标题
        return True
    return False


# ==========================================================================
# 打分
# ==========================================================================

def _hit(code, name, points, match, offset):
    return {"code": code, "name": name, "points": points, "match": match, "offset": offset}


def _scan(patterns, text):
    """收集所有命中，按位置去重叠，返回 [(offset, fragment)]。"""
    found = []
    for pat in patterns:
        for m in pat.finditer(text):
            found.append((m.start(), m.group(0)))
    found.sort()
    out, last_end = [], -1
    for off, frag in found:
        if off >= last_end:
            out.append((off, frag))
            last_end = off + len(frag)
    return out


def score_paragraph(text):
    hits = []
    has_source = bool(SOURCE_MARK.search(text))

    # S1 模板开头（段首，单次）
    head = re.sub(r"^[\s　>\"'《「『（(\[【“‘]+", "", text)
    lead = len(text) - len(head)
    for pat in S1_PATTERNS:
        m = pat.match(head)
        if m:
            hits.append(_hit("S1", "模板开头", S1_POINTS, m.group(0), lead))
            break

    # S2 排比骨架（成套出现，单次）
    for members in S2_SETS:
        if all(x in text for x in members):
            off = min(text.find(x) for x in members)
            hits.append(_hit("S2", "排比骨架", S2_POINTS, "+".join(members), off))
            break

    # S3 空洞结尾 / 综述套话（累加，封顶）
    s3 = 0
    for off, frag in _scan(S3_PATTERNS, text):
        if s3 >= S3_CAP:
            break
        add = min(S3_PER, S3_CAP - s3)
        hits.append(_hit("S3", "空洞结尾", add, frag, off))
        s3 += add

    # S4 空泛归因（累加，封顶；附近有引用标记则不计）
    s4 = 0
    for off, frag in _scan(S4_PATTERNS, text):
        lo, hi = max(0, off - 30), off + len(frag) + 30
        if CITATION_MARK.search(text[lo:hi]):
            continue
        if s4 >= S4_CAP:
            break
        add = min(S4_PER, S4_CAP - s4)
        hits.append(_hit("S4", "空泛归因", add, frag, off))
        s4 += add

    # S5 高频润色词聚集
    s5 = _scan(S5_PATTERNS, text)
    if len(s5) >= 2:
        pts = min(S5_CAP, S5_BASE + S5_STEP * (len(s5) - 2))
        hits.append(_hit("S5", "高频词聚集", pts, "/".join(f for _, f in s5), s5[0][0]))

    # S6 不安全数据语（段级：强断言 + 精确数字 + 全段无来源标记）
    if not has_source:
        asserts = _scan(S6_PATTERNS, text)
        figs = list(NUMBER_NEAR.finditer(text))
        if asserts and figs:
            pts = min(S6_CAP, S6_BASE + S6_STEP * len(figs))
            frag = asserts[0][1] + " / " + "、".join(m.group(0) for m in figs[:3])
            hits.append(_hit("S6", "不安全数据语", pts, frag, asserts[0][0]))

    # S7 升华对比框（每处 +8，封顶 20；软信号）
    s7 = 0
    for off, frag in _scan(S7_PATTERNS, text):
        if s7 >= S7_CAP:
            break
        add = min(S7_PER, S7_CAP - s7)
        hits.append(_hit("S7", "升华对比框", add, frag, off))
        s7 += add

    score = min(100, sum(h["points"] for h in hits))
    return score, hits


def level_of(score):
    if score <= 25:
        return "低"
    if score <= 50:
        return "中"
    if score <= 75:
        return "中高"
    return "高"


# ==========================================================================
# 分析与聚合
# ==========================================================================

def analyze(blocks, min_len):
    paragraphs, skipped = [], []
    in_ref = False
    for i, b in enumerate(blocks):
        text, style = b["text"], b["style"]
        if in_ref:
            skipped.append({"index": i, "reason": "参考文献", "preview": text[:40]})
            continue
        if is_reference_heading(text):
            in_ref = True
            skipped.append({"index": i, "reason": "参考文献", "preview": text[:40]})
            continue
        reason = skip_reason(text, style, min_len)
        if reason:
            skipped.append({"index": i, "reason": reason, "preview": text[:40]})
            continue
        score, hits = score_paragraph(text)
        paragraphs.append({
            "index": i,
            "char_count": len(text),
            "surface_score": score,
            "level": level_of(score),
            "needs_semantic_review": score >= 26,
            "hits": hits,
            "text": text,
        })

    total_chars = sum(p["char_count"] for p in paragraphs)
    ai_rate = (round(sum(p["surface_score"] * p["char_count"] for p in paragraphs) / total_chars, 1)
               if total_chars else 0.0)
    high = sum(1 for p in paragraphs if p["surface_score"] >= 51)
    ratio = round(high / len(paragraphs), 3) if paragraphs else 0.0

    return {
        "document": {
            "ai_rate_surface": ai_rate,
            "level": level_of(ai_rate),
            "high_risk_ratio": ratio,
            "n_total_blocks": len(blocks),
            "n_scored": len(paragraphs),
            "n_skipped": len(skipped),
            "skipped_breakdown": dict(Counter(s["reason"] for s in skipped)),
        },
        "paragraphs": paragraphs,
        "skipped": skipped,
    }


# ==========================================================================
# 输出
# ==========================================================================

def format_summary(result, top):
    d = result["document"]
    lines = ["=" * 60]
    lines.append(f"文档表层 AI率：{d['ai_rate_surface']}%  [{d['level']}]   "
                 f"(语义项由 Claude 在 skill 流程中补判)")
    lines.append(f"高风险段占比：{d['high_risk_ratio'] * 100:.1f}%   "
                 f"参与打分 {d['n_scored']} 段 / 跳过 {d['n_skipped']} 段 / 共 {d['n_total_blocks']} 块")
    if d["skipped_breakdown"]:
        bd = "、".join(f"{k}{v}" for k, v in d["skipped_breakdown"].items())
        lines.append(f"跳过明细：{bd}")
    lines.append("-" * 60)

    ranked = sorted(result["paragraphs"], key=lambda p: p["surface_score"], reverse=True)
    shown = [p for p in ranked if p["surface_score"] > 0][:top]
    if shown:
        lines.append(f"风险最高的 {len(shown)} 段：")
        for p in shown:
            codes = " ".join(dict.fromkeys(h["code"] for h in p["hits"]))
            lines.append(f"  [块{p['index']}] {p['surface_score']:>3}% {p['level']:<2} «{codes}»")
            lines.append(f"        {p['text'][:42]}…")
    else:
        lines.append("未检测到表层 AI 痕迹。")
    lines.append("=" * 60)
    return "\n".join(lines)


def format_compare(before, after, top):
    """打印降前(before JSON)/降后(after result)对比。按正文段落顺序对齐。"""
    b, a = before["document"], after["document"]
    drop = round(b["ai_rate_surface"] - a["ai_rate_surface"], 1)
    lines = ["=" * 60, "降前 / 降后对比", "=" * 60]
    lines.append(f"文档表层 AI率：{b['ai_rate_surface']}%（{b['level']}）"
                 f" → {a['ai_rate_surface']}%（{a['level']}）　↓{drop}")
    lines.append(f"高风险段占比：{b['high_risk_ratio'] * 100:.0f}% → {a['high_risk_ratio'] * 100:.0f}%")
    bp, ap_ = before["paragraphs"], after["paragraphs"]
    n = min(len(bp), len(ap_))
    if len(bp) != len(ap_):
        lines.append(f"⚠ 段落数不一致（降前 {len(bp)} / 降后 {len(ap_)}）；按顺序对齐前 {n} 段。")
    lines.append("-" * 60)
    order = sorted(range(n), key=lambda i: bp[i]["surface_score"], reverse=True)
    shown = [i for i in order if bp[i]["surface_score"] > 0][:top]
    if shown:
        lines.append(f"降幅最大的 {len(shown)} 段（按降前分排序）：")
        for i in shown:
            bs, as_ = bp[i]["surface_score"], ap_[i]["surface_score"]
            lines.append(f"  第{i + 1}段  {bs}% → {as_}%  ↓{bs - as_}")
            lines.append(f"          {ap_[i]['text'][:38]}…")
    else:
        lines.append("降前无表层痕迹。")
    lines.append("=" * 60)
    return "\n".join(lines)


def format_report(before, after):
    """生成 Markdown 降前/降后对比报告：总览 + 逐段评分 + 改动段原文/改后对照。"""
    bd, ad = before["document"], after["document"]
    bp, ap_ = before["paragraphs"], after["paragraphs"]
    n = min(len(bp), len(ap_))
    changed = [i for i in range(n) if bp[i]["text"] != ap_[i]["text"]]
    L = ["# 降 AI 对比报告\n",
         "> 由 academic-humanizer-zh / score.py 生成。表层分为脚本计算；语义层（节奏/推理/口吻）需人工判读。\n",
         "## 一、总览\n",
         f"- **文档表层 AI 率：降前 {bd['ai_rate_surface']}%（{bd['level']}）"
         f" → 降后 {ad['ai_rate_surface']}%（{ad['level']}）**",
         f"- 高风险段占比：{bd['high_risk_ratio'] * 100:.0f}% → {ad['high_risk_ratio'] * 100:.0f}%",
         f"- 参与打分 {bd['n_scored']} 段；本次改动 {len(changed)} 段"]
    if len(bp) != len(ap_):
        L.append(f"- ⚠ 两版段落数不一致（降前 {len(bp)} / 降后 {len(ap_)}），按顺序对齐前 {n} 段")
    L.append("\n## 二、逐段评分对比（仅列改动段）\n")
    L.append("> 「变化」列：表层未变 = 这段改的是节奏 / 措辞等语义层，不在 S1–S7 扫描范围内。\n")
    L.append("| 段 | 降前 | 降后 | 变化 | 该段开头 |")
    L.append("|---|---|---|---|---|")
    for i in changed:
        bs, as_ = bp[i]["surface_score"], ap_[i]["surface_score"]
        diff = bs - as_
        mark = f"↓{diff}" if diff > 0 else ("节奏改写·表层未变" if diff == 0 else f"⚠ 升{-diff}")
        L.append(f"| 第{i + 1}段 | {bs}% | {as_}% | {mark} | {ap_[i]['text'][:14]}… |")
    L.append("\n## 三、全文逐段对照（原文 → 改后）\n")
    for i in changed:
        L.append(f"### 第 {i + 1} 段　{bp[i]['surface_score']}% → {ap_[i]['surface_score']}%\n")
        L.append(f"**原文：**{bp[i]['text']}\n")
        L.append(f"**改后：**{ap_[i]['text']}\n")
        L.append("---\n")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="中文学术文本 AI 表层痕迹打分器")
    ap.add_argument("input", help="输入文件 .txt / .md / .docx")
    ap.add_argument("--json", dest="json_out", help="写出完整 JSON 到该路径")
    ap.add_argument("--compare", dest="compare", help="对比基准 JSON（降前结果）；给出后打印降前/降后对比表")
    ap.add_argument("--report", dest="report", help="与 --compare 配合，把降前/降后逐段对照写成 Markdown 报告文件")
    ap.add_argument("--min-len", type=int, default=15, help="低于该字数的段落不打分（默认 15）")
    ap.add_argument("--top", type=int, default=8, help="摘要/对比里展示的段落数量（默认 8）")
    ap.add_argument("--quiet", action="store_true", help="不打印摘要（仅写 JSON）")
    args = ap.parse_args()

    path = Path(args.input)
    if not path.exists():
        sys.exit(f"文件不存在：{path}")

    before = None
    if args.compare:
        cpath = Path(args.compare)
        if not cpath.exists():
            sys.exit(f"对比基准 JSON 不存在：{cpath}")
        before = json.loads(cpath.read_text(encoding="utf-8"))

    result = analyze(read_blocks(path), args.min_len)
    result["input"] = str(path)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.report:
        if not before:
            sys.exit("--report 需要同时指定 --compare <降前.json>")
        Path(args.report).write_text(format_report(before, result), encoding="utf-8")

    if not args.quiet:
        print(format_compare(before, result, args.top) if before else format_summary(result, args.top))
        if args.json_out:
            print(f"\n完整结果已写入：{args.json_out}")
        if args.report:
            print(f"对比报告已写入：{args.report}")


if __name__ == "__main__":
    main()
