"""Build the formal XA-202620 D1 technical report PDF."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import fitz
from pypdf import PdfReader
from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, CondPageBreak, Flowable, Frame, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/delivery/D1-technical-report-review-draft.md"
OUTPUT = ROOT / "output/pdf/XA-Guard-XA-202620-technical-report.pdf"
NAVY, BLUE, CYAN = colors.HexColor("#0B1F3A"), colors.HexColor("#1769AA"), colors.HexColor("#00A6A6")
INK, MUTED, PALE = colors.HexColor("#172033"), colors.HexColor("#596579"), colors.HexColor("#EAF2F8")


def register_font() -> str:
    candidates = [Path("C:/Windows/Fonts/NotoSansSC-VF.ttf"),
                  Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/simhei.ttf")]
    for path in candidates:
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont("CN", str(path), subfontIndex=0))
                return "CN"
            except Exception:
                continue
    raise RuntimeError("No usable Chinese font found in C:/Windows/Fonts")


class Diagram(Flowable):
    LABELS = {
        "threat": ["不可信输入", "身份/授权", "工具执行", "真实副作用", "可验证证据"],
        "architecture": ["Human + Agent", "Governance", "Gate1–6", "Effect + Worker", "业务系统"],
        "identity": ["OIDC 登录", "Token Exchange", "双主体声明", "动态 Assignment", "最小权限"],
        "state": ["prepared", "executed", "available", "undo_pending", "compensated"],
        "oar": ["攻击任务", "Null / Guard", "工具尝试", "审计对齐", "A/B 结论"],
        "results": ["11/11 故障", "kind HA", "p95 < 50ms", "Undo < 1s", "证据签名"],
        "deployment": ["Console/BFF", "XA-Guard API", "Worker", "PostgreSQL", "Keycloak/业务"],
    }

    def __init__(self, name: str):
        super().__init__()
        self.name, self.width, self.height = name, 168 * mm, 27 * mm

    def draw(self):
        labels = self.LABELS.get(self.name, [self.name])
        gap, arrow = 3 * mm, 5 * mm
        width = (self.width - (len(labels) - 1) * (gap + arrow)) / len(labels)
        self.canv.setFont("CN", 7.7)
        for index, label in enumerate(labels):
            x = index * (width + gap + arrow)
            self.canv.setFillColor(PALE if index % 2 == 0 else colors.HexColor("#D9F3F2"))
            self.canv.setStrokeColor(BLUE)
            self.canv.roundRect(x, 5 * mm, width, 15 * mm, 2 * mm, fill=1, stroke=1)
            self.canv.setFillColor(INK)
            self.canv.drawCentredString(x + width / 2, 11 * mm, label)
            if index < len(labels) - 1:
                ax = x + width + gap
                self.canv.setStrokeColor(CYAN)
                self.canv.line(ax, 12.5 * mm, ax + arrow, 12.5 * mm)
                self.canv.line(ax + arrow - 2 * mm, 14 * mm, ax + arrow, 12.5 * mm)
                self.canv.line(ax + arrow - 2 * mm, 11 * mm, ax + arrow, 12.5 * mm)


class MermaidDiagram(Flowable):
    def __init__(self, source: str):
        super().__init__()
        self.source = source
        self.lines = [line.strip() for line in source.splitlines() if line.strip()]
        self.kind = self.lines[0] if self.lines else "mermaid"
        self.width, self.height = 168 * mm, 50 * mm

    def wrap(self, avail_width, _avail_height):
        self.width = min(avail_width, 168 * mm)
        if self.kind.startswith("sequenceDiagram"):
            _participants, messages = self._sequence()
            self.height = 24 * mm + max(1, len(messages)) * 7 * mm
        else:
            nodes, _edges = self._graph()
            cols = self._cols(len(nodes))
            rows = max(1, math.ceil(len(nodes) / cols))
            self.height = 14 * mm + rows * 25 * mm
        return self.width, self.height

    def draw(self):
        self.canv.saveState()
        self.canv.setFillColor(colors.HexColor("#FBFDFF"))
        self.canv.setStrokeColor(colors.HexColor("#D5DEE7"))
        self.canv.roundRect(0, 0, self.width, self.height, 3 * mm, fill=1, stroke=1)
        if self.kind.startswith("sequenceDiagram"):
            self._draw_sequence()
        else:
            self._draw_graph()
        self.canv.restoreState()

    @staticmethod
    def _cols(count: int) -> int:
        count = max(1, count)
        if count <= 6:
            return count
        return min(count, 4 if count <= 8 else 5)

    @staticmethod
    def _wrap_lines(text: str, max_width: float, font_size: float, max_lines: int) -> list[str]:
        text = re.sub(r"\s+", " ", text.strip().strip('"'))
        if not text:
            return [""]
        lines, pos = [], 0
        for _ in range(max_lines):
            line = ""
            while pos < len(text):
                candidate = line + text[pos]
                if not line or pdfmetrics.stringWidth(candidate, "CN", font_size) <= max_width:
                    line = candidate
                    pos += 1
                else:
                    break
            if line:
                lines.append(line)
            if pos >= len(text):
                break
        if pos < len(text) and lines:
            while lines[-1] and pdfmetrics.stringWidth(lines[-1] + "...", "CN", font_size) > max_width:
                lines[-1] = lines[-1][:-1]
            lines[-1] += "..."
        return lines or [text[:1]]

    def _draw_center(self, text: str, cx: float, cy: float, max_width: float,
                     font_size: float = 7.2, max_lines: int = 2):
        lines = self._wrap_lines(text, max_width, font_size, max_lines)
        leading = font_size + 1.4
        y = cy + (len(lines) - 1) * leading / 2 - font_size / 3
        self.canv.setFont("CN", font_size)
        self.canv.setFillColor(INK)
        for line in lines:
            self.canv.drawCentredString(cx, y, line)
            y -= leading

    def _draw_arrow(self, x1: float, y1: float, x2: float, y2: float,
                    color=CYAN, width: float = 0.7):
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 2:
            return
        self.canv.setStrokeColor(color)
        self.canv.setLineWidth(width)
        self.canv.line(x1, y1, x2, y2)
        angle = math.atan2(dy, dx)
        head, spread = 2.2 * mm, 0.75
        for sign in (-1, 1):
            hx = x2 - head * math.cos(angle + sign * spread)
            hy = y2 - head * math.sin(angle + sign * spread)
            self.canv.line(x2, y2, hx, hy)

    @staticmethod
    def _node(token: str) -> tuple[str, str]:
        token = token.strip().strip(";")
        if token == "[*]":
            return "__start__", "start"
        match = re.match(r"([A-Za-z][\w-]*)", token)
        node_id = match.group(1) if match else re.sub(r"\W+", "_", token)[:20]
        label = None
        for pattern in (r'\["([^"]+)"\]', r'\{"([^"]+)"\}', r'\("([^"]+)"\)',
                        r"\[([^\]]+)\]", r"\{([^}]+)\}", r"\(([^)]+)\)"):
            found = re.search(pattern, token)
            if found:
                label = found.group(1)
                break
        return node_id, (label or node_id.replace("_", " ")).strip()

    def _split_edge(self, line: str):
        match = re.match(r"(.+?)\s*-->\s*(?:\|([^|]+)\|\s*)?(.+)", line)
        if not match:
            return None
        left, label, right = match.group(1), match.group(2), match.group(3)
        if self.kind.startswith("stateDiagram") and ":" in right:
            right, state_label = right.split(":", 1)
            label = label or state_label.strip()
        return left.strip(), (label or "").strip(), right.strip()

    def _graph(self) -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
        labels, order, edges = {}, [], []

        def add(node_id: str, label: str):
            if node_id == "__start__":
                return
            if node_id not in labels:
                labels[node_id] = label
                order.append(node_id)
            elif label and labels[node_id] == node_id:
                labels[node_id] = label

        for line in self.lines[1:]:
            if line.startswith("%%"):
                continue
            split = self._split_edge(line)
            if split:
                left, label, right = split
                src, src_label = self._node(left)
                dst, dst_label = self._node(right)
                add(src, src_label)
                add(dst, dst_label)
                if src != "__start__" and dst != "__start__":
                    edges.append((src, dst, label))
                continue
            node_id, node_label = self._node(line)
            add(node_id, node_label)
        return [(node_id, labels[node_id]) for node_id in order], edges

    def _edge_points(self, src, dst):
        x1, y1, w1, h1 = src
        x2, y2, w2, h2 = dst
        c1x, c1y = x1 + w1 / 2, y1 + h1 / 2
        c2x, c2y = x2 + w2 / 2, y2 + h2 / 2
        dx, dy = c2x - c1x, c2y - c1y
        if abs(dx) >= abs(dy):
            sign = 1 if dx >= 0 else -1
            return c1x + sign * w1 / 2, c1y, c2x - sign * w2 / 2, c2y
        sign = 1 if dy >= 0 else -1
        return c1x, c1y + sign * h1 / 2, c2x, c2y - sign * h2 / 2

    def _draw_graph(self):
        nodes, edges = self._graph()
        if not nodes:
            self._draw_center("Mermaid diagram", self.width / 2, self.height / 2, self.width - 12 * mm)
            return
        cols = self._cols(len(nodes))
        gap, margin = 4 * mm, 5 * mm
        box_w = (self.width - 2 * margin - (cols - 1) * gap) / cols
        box_h, row_gap = 14 * mm, 11 * mm
        top = self.height - 7 * mm
        positions = {}
        for index, (node_id, label) in enumerate(nodes):
            row, col = divmod(index, cols)
            if row % 2:
                col = cols - 1 - col
            x = margin + col * (box_w + gap)
            y = top - (row + 1) * box_h - row * row_gap
            positions[node_id] = (x, y, box_w, box_h, label)
        for src, dst, label in edges:
            if src not in positions or dst not in positions:
                continue
            x1, y1, x2, y2 = self._edge_points(positions[src][:4], positions[dst][:4])
            self._draw_arrow(x1, y1, x2, y2)
            if label:
                self.canv.setFont("CN", 5.9)
                self.canv.setFillColor(BLUE)
                self.canv.drawCentredString((x1 + x2) / 2, (y1 + y2) / 2 + 1.5 * mm, label)
        for index, (node_id, label) in enumerate(nodes):
            x, y, w, h, _label = positions[node_id]
            self.canv.setFillColor(PALE if index % 2 == 0 else colors.HexColor("#DDF5F2"))
            self.canv.setStrokeColor(BLUE)
            self.canv.roundRect(x, y, w, h, 2 * mm, fill=1, stroke=1)
            self._draw_center(label, x + w / 2, y + h / 2, w - 4 * mm, 6.7, 2)

    def _sequence(self):
        labels, order, messages = {}, [], []

        def add(identifier: str, label: str | None = None):
            if identifier not in labels:
                labels[identifier] = label or identifier
                order.append(identifier)
            elif label:
                labels[identifier] = label

        for line in self.lines[1:]:
            participant = re.match(r"participant\s+(\w+)\s+as\s+(.+)", line)
            if participant:
                add(participant.group(1), participant.group(2).strip())
                continue
            message = re.match(r"(\w+)\s*[-.]+>>\s*(\w+)\s*:\s*(.+)", line)
            if message:
                src, dst, label = message.group(1), message.group(2), message.group(3).strip()
                add(src)
                add(dst)
                messages.append((src, dst, label))
        return [(identifier, labels[identifier]) for identifier in order], messages

    def _draw_sequence(self):
        participants, messages = self._sequence()
        if not participants:
            self._draw_center("Sequence diagram", self.width / 2, self.height / 2, self.width - 12 * mm)
            return
        margin, top = 5 * mm, self.height - 6 * mm
        usable = self.width - 2 * margin
        step = usable / max(1, len(participants) - 1)
        xs = {identifier: margin + index * step for index, (identifier, _label) in enumerate(participants)}
        box_w = min(22 * mm, usable / max(1, len(participants)) - 1 * mm)
        box_h = 9 * mm
        for identifier, label in participants:
            x = xs[identifier]
            self.canv.setFillColor(PALE)
            self.canv.setStrokeColor(BLUE)
            self.canv.roundRect(x - box_w / 2, top - box_h, box_w, box_h, 1.5 * mm, fill=1, stroke=1)
            self._draw_center(label, x, top - box_h / 2, box_w - 2 * mm, 6.2, 2)
            self.canv.setStrokeColor(colors.HexColor("#B9C8D6"))
            self.canv.setDash(1, 2)
            self.canv.line(x, top - box_h, x, 5 * mm)
            self.canv.setDash()
        y = top - box_h - 7 * mm
        for src, dst, label in messages:
            x1, x2 = xs[src], xs[dst]
            if src == dst:
                loop = 9 * mm
                self.canv.setStrokeColor(CYAN)
                self.canv.line(x1, y, x1 + loop, y)
                self.canv.line(x1 + loop, y, x1 + loop, y - 3 * mm)
                self._draw_arrow(x1 + loop, y - 3 * mm, x1, y - 3 * mm, CYAN, 0.6)
                self._draw_center(label, x1 + loop / 2, y + 2.3 * mm, 34 * mm, 5.7, 1)
            else:
                end_pad = 2 * mm if x2 >= x1 else -2 * mm
                self._draw_arrow(x1, y, x2 - end_pad, y, CYAN, 0.6)
                self._draw_center(label, (x1 + x2) / 2, y + 2.3 * mm,
                                  max(18 * mm, abs(x2 - x1) - 3 * mm), 5.7, 1)
            y -= 6.8 * mm


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(text: str) -> str:
    text = esc(text.strip())
    text = re.sub(r"`([^`]+)`", r'<font color="#1769AA">\1</font>', text)
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)


def styles(font: str):
    base = getSampleStyleSheet()
    return {
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName=font, fontSize=14, leading=19,
                              textColor=NAVY, spaceBefore=2 * mm, spaceAfter=4 * mm,
                              keepWithNext=True),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName=font, fontSize=16, leading=22,
                              textColor=NAVY, spaceBefore=1 * mm, spaceAfter=5 * mm,
                              keepWithNext=True),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontName=font, fontSize=11, leading=15,
                              textColor=BLUE, spaceBefore=2 * mm, spaceAfter=2 * mm,
                              keepWithNext=True),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName=font, fontSize=9.2, leading=15,
                                alignment=TA_JUSTIFY, textColor=INK, spaceAfter=2.8 * mm, wordWrap="CJK"),
        "bullet": ParagraphStyle("bullet", parent=base["BodyText"], fontName=font, fontSize=8.9, leading=14,
                                  leftIndent=5 * mm, firstLineIndent=-3 * mm, textColor=INK,
                                  spaceAfter=1.5 * mm, wordWrap="CJK"),
        "code": ParagraphStyle("code", parent=base["Code"], fontName=font, fontSize=7.5, leading=11,
                                leftIndent=5 * mm, textColor=colors.HexColor("#31465F"),
                                backColor=colors.HexColor("#F4F7FA"), borderPadding=3 * mm, spaceAfter=2 * mm),
        "cell": ParagraphStyle("cell", parent=base["BodyText"], fontName=font, fontSize=7.2, leading=10,
                                textColor=INK, wordWrap="CJK"),
        "headcell": ParagraphStyle("headcell", parent=base["BodyText"], fontName=font, fontSize=7.2,
                                    leading=10, textColor=colors.white, wordWrap="CJK"),
        "reference": ParagraphStyle("reference", parent=base["BodyText"], fontName=font,
                                     fontSize=7.0, leading=9.4, alignment=TA_LEFT,
                                     textColor=INK, spaceAfter=0.5 * mm, wordWrap="CJK"),
    }


def cover(font: str):
    title = ParagraphStyle("cover-title", fontName=font, fontSize=27, leading=38,
                           alignment=TA_CENTER, textColor=NAVY)
    competition = ParagraphStyle("cover-competition", fontName=font, fontSize=10.5, leading=16,
                                 alignment=TA_CENTER, textColor=MUTED)
    sub = ParagraphStyle("cover-sub", fontName=font, fontSize=15, leading=24,
                         alignment=TA_CENTER, textColor=BLUE)
    report_type = ParagraphStyle("cover-report-type", fontName=font, fontSize=12, leading=19,
                                 alignment=TA_CENTER, textColor=NAVY)
    meta_label = ParagraphStyle("cover-meta-label", fontName=font, fontSize=9.2, leading=15,
                                alignment=TA_LEFT, textColor=MUTED)
    meta_value = ParagraphStyle("cover-meta-value", fontName=font, fontSize=9.2, leading=15,
                                alignment=TA_LEFT, textColor=INK)
    footer = ParagraphStyle("cover-footer", fontName=font, fontSize=8.5, leading=14,
                            alignment=TA_CENTER, textColor=MUTED)
    rule = Table([[""]], colWidths=[42 * mm], rowHeights=[1.5 * mm],
                 style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), CYAN)]))
    metadata = Table(
        [
            [Paragraph("题目编号", meta_label), Paragraph("XA-202620", meta_value)],
            [Paragraph("题目名称", meta_label),
             Paragraph("面向政企场景的大模型智能体安全关键技术研究", meta_value)],
            [Paragraph("参赛赛道", meta_label), Paragraph("学生赛道", meta_value)],
            [Paragraph("文档版本", meta_label), Paragraph("v1.0（提交版）", meta_value)],
            [Paragraph("提交日期", meta_label), Paragraph("2026-07-27", meta_value)],
        ],
        colWidths=[25 * mm, 88 * mm],
        hAlign="CENTER",
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW", (0, 0), (-1, -2), 0.35, colors.HexColor("#D5DEE7")),
            ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
            ("TOPPADDING", (0, 0), (-1, -1), 2.2 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2 * mm),
        ]),
    )
    return [
        Spacer(1, 24 * mm),
        Paragraph("2026 年度中国青年科技创新“揭榜挂帅”擂台赛", competition),
        Spacer(1, 16 * mm),
        Paragraph("XA-Guard", title),
        Spacer(1, 4 * mm),
        Paragraph("面向政企场景的大模型智能体<br/>运行时安全治理与可验证恢复", sub),
        Spacer(1, 10 * mm),
        rule,
        Spacer(1, 10 * mm),
        Paragraph("D1 技术方案报告", report_type),
        Spacer(1, 13 * mm),
        metadata,
        Spacer(1, 24 * mm),
        Paragraph("发榜单位：中国雄安集团数字城市科技有限公司", footer),
        PageBreak(),
    ]


def _column_ratios(count: int, header: list[str]) -> list[float]:
    """Readable portrait-A4 profiles for the report's recurring table shapes."""
    header_text = "|".join(header)
    if count == 2:
        return [0.35, 0.65]
    if count == 3:
        return [0.22, 0.37, 0.41]
    if count == 4 and "处理与输出" in header_text:
        return [0.16, 0.20, 0.40, 0.24]
    if count == 4:
        return [0.17, 0.23, 0.30, 0.30]
    if count == 5 and "当前结果" in header_text:
        return [0.13, 0.15, 0.22, 0.32, 0.18]
    if count == 5:
        return [0.18, 0.20, 0.20, 0.21, 0.21]
    if count == 6:
        return [0.20, 0.14, 0.11, 0.11, 0.22, 0.22]
    if count == 7:
        return [0.11, 0.145, 0.145, 0.145, 0.145, 0.155, 0.155]
    return [1 / count] * count


def table_from(lines: list[str], st) -> Table:
    raw_rows: list[list[str]] = []
    for line in lines:
        raw_cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r"[-: ]+", cell) for cell in raw_cells):
            continue
        raw_rows.append(raw_cells)
    count = max(len(row) for row in raw_rows)
    for row in raw_rows:
        row.extend([""] * (count - len(row)))

    font_size, leading = {
        2: (7.3, 10.2),
        3: (7.2, 10.0),
        4: (6.8, 9.4),
        5: (6.2, 8.8),
        6: (5.8, 8.2),
        7: (5.6, 8.0),
    }.get(count, (5.5, 7.8))
    body_style = ParagraphStyle(
        f"cell-{count}", parent=st["cell"], fontSize=font_size, leading=leading,
    )
    head_style = ParagraphStyle(
        f"headcell-{count}", parent=st["headcell"], fontSize=font_size, leading=leading,
    )
    rows = [
        [Paragraph(inline(cell), head_style if row_index == 0 else body_style) for cell in row]
        for row_index, row in enumerate(raw_rows)
    ]
    ratios = _column_ratios(count, raw_rows[0])
    table = Table(
        rows,
        colWidths=[168 * mm * ratio for ratio in ratios],
        repeatRows=1,
        hAlign="LEFT",
        splitByRow=1,
    )
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "CN"),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B9C8D6")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F9FB")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]))
    return table


def parse(markdown: str, st) -> list:
    lines = markdown.splitlines()
    if "<!-- pagebreak -->" in lines:
        lines = lines[lines.index("<!-- pagebreak -->") + 1:]
    else:
        first_nonempty = next((line.strip() for line in lines if line.strip()), "")
        first_h2 = next((i for i, line in enumerate(lines) if line.startswith("## ")), None)
        if first_nonempty.startswith("# ") and first_h2 is not None:
            # The formal cover already carries the source preamble and metadata.
            lines = lines[first_h2:]
    story, index = [], 0
    while index < len(lines):
        raw, stripped = lines[index], lines[index].strip()
        if not stripped:
            index += 1
            continue
        if re.fullmatch(r"-{3,}", stripped):
            index += 1
            continue
        if stripped == "<!-- pagebreak -->":
            story.append(PageBreak())
            index += 1
            continue
        match = re.fullmatch(r"\[DIAGRAM:([a-z]+)\]", stripped)
        if match:
            story.extend([Spacer(1, 2 * mm), Diagram(match.group(1)), Spacer(1, 3 * mm)])
            index += 1
            continue
        if stripped.startswith("```"):
            lang = stripped[3:].strip().split(maxsplit=1)[0].lower() if stripped[3:].strip() else ""
            block = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                block.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            if lang == "mermaid":
                story.extend([Spacer(1, 2 * mm), MermaidDiagram("\n".join(block)), Spacer(1, 3 * mm)])
            else:
                code = [esc(line.rstrip()) or "&#160;" for line in block]
                story.append(Paragraph("<br/>".join(code), st["code"]))
            continue
        if stripped.startswith("|"):
            block = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                block.append(lines[index])
                index += 1
            story.extend([table_from(block, st), Spacer(1, 3 * mm)])
            continue
        if raw.startswith("    "):
            block = []
            while index < len(lines) and (lines[index].startswith("    ") or not lines[index].strip()):
                if lines[index].strip():
                    block.append(esc(lines[index].strip()))
                index += 1
            story.append(Paragraph("<br/>".join(block), st["code"]))
            continue
        if stripped.startswith("# "):
            story.append(CondPageBreak(25 * mm))
            story.append(Paragraph(inline(stripped[2:]), st["h1"]))
            index += 1
            continue
        if stripped.startswith("### "):
            story.append(CondPageBreak(22 * mm))
            story.append(Paragraph(inline(stripped[4:]), st["h3"]))
            index += 1
            continue
        if stripped.startswith("## "):
            heading = stripped[3:]
            if heading.startswith("附录") and story and not isinstance(story[-1], PageBreak):
                story.append(PageBreak())
            else:
                story.append(CondPageBreak(28 * mm))
            story.append(Paragraph(inline(heading), st["h2"]))
            index += 1
            continue
        if re.match(r"^(?:[-*]|\d{1,3}\.)\s+", stripped):
            label = re.sub(r"^(?:[-*]|\d{1,3}\.)\s+", "", re.sub(r"\s+", " ", stripped))
            story.append(Paragraph("• " + inline(label), st["bullet"]))
            index += 1
            continue
        paragraph = [stripped]
        index += 1
        special = r"^(?:#{1,3} |\| |    |```|[-*] |\d{1,3}\. |<!--|\[DIAGRAM:)|^-{3,}$"
        while index < len(lines) and lines[index].strip() and not re.match(special, lines[index]):
            paragraph.append(lines[index].strip())
            index += 1
        paragraph_style = st["reference"] if re.match(r"^\[\d+\]", paragraph[0]) else st["body"]
        story.append(Paragraph(inline(" ".join(paragraph)), paragraph_style))
    return story


def decorate(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, A4[1] - 8 * mm, A4[0], 8 * mm, fill=1, stroke=0)
    if doc.page > 1:
        canvas.setFont("CN", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(21 * mm, 11 * mm, "XA-Guard · D1 技术方案报告")
        canvas.drawRightString(A4[0] - 21 * mm, 11 * mm, str(doc.page))
        canvas.setStrokeColor(colors.HexColor("#D5DEE7"))
        canvas.line(21 * mm, 15 * mm, A4[0] - 21 * mm, 15 * mm)
    canvas.restoreState()


def build(source: Path, output: Path, render_dir: Path | None):
    rl_config.invariant = 1
    font = register_font()
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(
        str(output), pagesize=A4, leftMargin=21 * mm, rightMargin=21 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
        title="XA-Guard：面向政企场景的大模型智能体安全关键技术研究",
        author="XA-Guard 参赛团队",
        subject="XA-202620 D1 技术方案报告",
        creator="XA-Guard D1 deterministic PDF builder",
        keywords="XA-202620, XA-Guard, 智能体安全, MCP, AIBOM, 审计溯源, 可验证恢复",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")
    doc.addPageTemplates(PageTemplate(id="report", frames=[frame], onPage=decorate))
    doc.build(cover(font) + parse(source.read_text(encoding="utf-8"), styles(font)))
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{digest}  {output.name}\n", encoding="ascii")
    if render_dir:
        render_dir.mkdir(parents=True, exist_ok=True)
        pdf = fitz.open(output)
        for number, page in enumerate(pdf, 1):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7), alpha=False)
            pixmap.save(render_dir / f"page-{number:02d}.png")
    pages = len(PdfReader(str(output)).pages)
    print(json.dumps({"output": str(output), "pages": pages, "sha256": digest,
                      "render_dir": str(render_dir) if render_dir else None},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--render-dir", type=Path)
    args = parser.parse_args()
    build(args.source, args.output, args.render_dir)
