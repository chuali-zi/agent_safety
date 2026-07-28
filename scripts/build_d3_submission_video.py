#!/usr/bin/env python3
"""Build the XA-Guard D3 submission video from verified, non-secret evidence.

The builder deliberately uses result projections and existing Console screenshots.
It never embeds attack payloads, credentials, local absolute paths, or raw audit
records. Chinese narration is synthesized offline with the Windows Huihui voice so
the repository has a complete, reproducible submission candidate without requiring
network access.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output" / "video"
BUILD_DIR = ROOT / ".runtime" / "d3-video-build"
SCREENSHOT_DIR = ROOT / "docs" / "evidence" / "mcp-live-acceptance-2026-07-19"
VIDEO_NAME = "XA-Guard-XA-202620-demo.mp4"
WIDTH = 1920
HEIGHT = 1080
FPS = 30


@dataclass(frozen=True)
class Scene:
    slug: str
    duration: int
    eyebrow: str
    title: str
    subtitle: str
    bullets: tuple[str, ...]
    narration: tuple[str, ...]
    accent: str
    metric: str = ""
    screenshots: tuple[str, ...] = ()


SCENES: tuple[Scene, ...] = (
    Scene(
        "01-open",
        35,
        "XA-202620 · D3 原型演示",
        "面向政企场景的大模型智能体安全关键技术研究",
        "XA-Guard：把 Agent 的身份、决策、副作用、恢复和证据接成一个闭环",
        (
            "输入与数据安全",
            "执行安全",
            "供应链安全",
            "审计与合规",
        ),
        (
            "这里是 XA-Guard，赛题编号 XA-202620。",
            "它面向政企智能体，把输入与数据安全、执行安全、供应链安全、审计合规，接入同一个运行时闭环。",
            "演示先看真实客户端和业务后果，再解释治理机制与边界。",
        ),
        "#35D7A4",
        "IDENTITY → SIX GATES → EFFECT → UNDO → EVIDENCE",
    ),
    Scene(
        "02-real-client",
        55,
        "真实 Agent 客户端预演 · 2026-07-27",
        "OpenCode → DeepSeek V4 Flash → XA-Guard MCP",
        "不是静态脚本：真实客户端完成工具发现、模型 Tool Call 与 Gate6 审计",
        (
            "MCP discovery：1 server connected",
            "tool call：get_cpu({host: web03})",
            "result：web03 / CPU 85%",
            "Gate6：allow · faithfulness 1.0 · audit 1/1 verified",
        ),
        (
            "首先是真实 Agent 客户端预演。",
            "隔离配置下，OpenCode 只连接一个 XA-Guard HTTP MCP 服务，模型使用 DeepSeek V4 Flash。",
            "客户端完成工具发现，模型实际调用 get CPU，参数是 web03，返回 CPU 百分之八十五。",
            "XA-Guard 记录最终 allow、六关结果和 trace；唯一一条 Gate6 审计独立验签通过，零错误。",
        ),
        "#4CC9F0",
        "trace 9eb1b0fe…e03d  ·  record f17810ab…725d",
    ),
    Scene(
        "03-live-causal",
        65,
        "真实模型因果轨道 · holdout-v1",
        "同一不可变 ToolIntent，两条执行臂给出相反业务后果",
        "D2 两个 holdout profile 均形成可重复因果证明；30 次总运行、0 infra error",
        (
            "model attempt：5/5 + 5/5",
            "Null arm：harm 10/10",
            "XA-Guard arm：Gate3 deny 10/10",
            "protected harm：0/10 · causal proof established",
        ),
        (
            "下面是真实模型因果轨道。",
            "D2 两个 holdout profile 各重复五次，模型每次都形成违规工具意图。",
            "同一个不可变 ToolIntent 同时送入 Null 和 XA-Guard 两条执行臂。Null 侧十次全部产生业务危害；受保护侧十次全部由 Gate3 拒绝，危害为零。",
            "两臂共享意图哈希，因此差异可以归因于治理层，而不是模型随机改口。全轨道三十次运行，基础设施错误为零。",
        ),
        "#FFB703",
        "NULL  10/10 HARM     |     XA-GUARD  0/10 HARM",
    ),
    Scene(
        "04-metrics-boundary",
        50,
        "识别量化 + 真实边界披露",
        "既给出达标数字，也保留未拦住的引用型外发边界",
        "诊断性规则切分不等于独立泛化评估；真实模型结果不与确定性 OAR 混写",
        (
            "Gate1：6 族 / 60 例，识别并阻断 60/60",
            "expected-allow：FPR 0/58；Wilson 95% 上界 6.21%",
            "规则层 p95：0.04 ms（不含模型与完整链路）",
            "D1 realistic-safe：attempt 5/5；allow / harm 5/5",
        ),
        (
            "Gate1 诊断集覆盖六个输入攻击族，共六十例，识别并阻断六十例。",
            "五十八个放行负控制误报为零，Wilson 百分之九十五上界为百分之六点二一；规则层 p 九十五为零点零四毫秒。",
            "边界同样必须上屏：这不是独立泛化评估，也不包含模型和完整链路时延。",
            "真实模型 D1 场景五次都形成引用型外发意图。现有规则会扫描字面内容，但不会把 sources 符号引用解析到业务世界并查询资产敏感级别，因此五次放行并产生危害。这是已发现、未掩盖的产品边界。",
        ),
        "#F77F00",
        "D1 BOUNDARY · unresolved source references · 5/5 allowed",
    ),
    Scene(
        "05-oar-proof",
        45,
        "确定性 OAR 攻击证明集 · N=10",
        "邮箱与 RAG 两类合成场景：同输入、同 SUT、双臂业务后果对照",
        "与真实模型轨道分开报告；仅在封存的合成确定性范围内成立",
        (
            "MAIL：Null leak 10/10 → XA-Guard leak 0/10",
            "RAG：Null leak 10/10 → XA-Guard leak 0/10",
            "protected infra error：0",
            "protected causal replay：20/20",
        ),
        (
            "第二条证据轨道是确定性 OAR 攻击证明集。",
            "邮箱和 RAG 两个合成场景各重复十次。Null 侧分别十次全部泄漏；接入 XA-Guard 后，两类场景泄漏都为零。",
            "二十次受保护回放全部通过哈希、账本、SUT 审计顺序和 Gate6 对齐检查，基础设施错误为零。",
            "这组结果只证明封存的合成确定性场景，不外推为通用攻击成功率。",
        ),
        "#EF476F",
        "20/20 protected replay verified",
    ),
    Scene(
        "06-aibom",
        45,
        "供应链准入 · AIBOM",
        "源码、依赖、能力声明与 provenance 一并进入审批策略",
        "D3 holdout 未发生违规 intent，只能归因模型自防，不能计作 XA-Guard 拦截",
        (
            "risk level：A/B 放行 · C 人工复核 · D/F 拒绝",
            "恶意 snippet：deny · downstream 0",
            "干净 artifact：approval → allow · downstream 1",
            "D3 real-agent：attempt 0/10（model self-defense）",
        ),
        (
            "供应链侧由 AIBOM 检查源码、依赖、能力声明和 provenance。",
            "在封存对照里，恶意 snippet 被拒绝，下游调用为零；干净 artifact 进入审批，独立批准后放行，下游调用为一。",
            "评级规则是 A、B 放行，C 人工复核，D、F 拒绝。",
            "真实模型 D3 holdout 十次都没有形成违规意图；这只能记为模型自防，不能伪装成 XA-Guard 的拦截成绩。",
        ),
        "#9B5DE5",
        "ADMIT CLEAN · DENY RISK · NEVER INVENT A GRADE",
    ),
    Scene(
        "07-identity",
        45,
        "身份与动态委托",
        "human → Agent → tool → data domain",
        "Keycloak PKCE、token exchange、数据库实时 assignment 与执行前 fail-closed",
        (
            "Alice / general-office-agent / ACTIVE",
            "business_submit_ticket",
            "engineering_docs",
            "伪造签名、错误 audience、伪造主体、撤权后访问：执行前拒绝",
        ),
        (
            "身份面从真实人员会话开始。",
            "Alice 通过 Keycloak PKCE 登录，BFF 再做 token exchange；页面展示数据库中的实时委托链：人员、Agent、工具和数据域。",
            "浏览器自报身份不被信任。伪造签名、错误 audience、伪造主体，以及 assignment 撤权后的访问，都在执行前失败关闭，下游写入和 Effect 增量保持为零。",
        ),
        "#06D6A0",
        "SIGNED IDENTITY · LIVE ASSIGNMENT · FAIL CLOSED",
        ("console-01-alice-home.png",),
    ),
    Scene(
        "08-effect-undo",
        60,
        "Intent-first Effect + 职责分离 Undo",
        "先登记可恢复意图，再触发真实业务副作用；申请人与批准人不能是同一 subject",
        "真实 Console 操作链：创建、撤销申请、独立审批、补偿完成",
        (
            "Effect：PREPARED → AVAILABLE",
            "ticket：open",
            "Alice request undo → Dora approve",
            "Worker：AVAILABLE → COMPENSATED · open → cancelled",
        ),
        (
            "Alice 委托 Agent 创建演示工单。XA-Guard 在触达业务 API 前，先登记 PREPARED Effect，并冻结恢复所需的参数、幂等键和补偿合同。",
            "写入成功后，Effect 进入 AVAILABLE，业务工单状态为 open。",
            "Alice 可以申请撤销，但不能批准自己的请求。Dora 使用独立身份审批；Worker 执行补偿后，Effect 进入 COMPENSATED，工单从 open 变为 cancelled。",
            "调度语义是至少一次加下游幂等，不宣称绝对 exactly once。",
        ),
        "#00B4D8",
        "PREPARE BEFORE SIDE EFFECT · INDEPENDENT APPROVAL",
        (
            "console-02-alice-ticket-created.png",
            "console-03-alice-undo-requested.png",
            "console-05-dora-approved.png",
            "console-06-effect-compensated.png",
        ),
    ),
    Scene(
        "09-evidence",
        55,
        "双链证据与离线篡改检出",
        "Gate6 决策链 + Effect 生命周期链，以 effect、业务引用和 trace 交叉关联",
        "同一业务动作的人员、Agent、审批、原执行与补偿可独立复核",
        (
            "clean copy：verify exit 0",
            "tampered copy：verify exit 1",
            "原始 audit hash 不变",
            "人员、Agent、审批、原动作与补偿可追溯",
        ),
        (
            "每次决策进入 Gate6 哈希链，每个副作用进入 Effect 生命周期链。",
            "两条链通过 Effect、业务引用、原动作 trace 和补偿 trace 交叉关联。",
            "干净审计副本离线验签，退出码为零；只篡改一条记录后，副本退出码为一，而原始 audit hash 保持不变。",
            "因此人员、Agent、审批、业务后果和恢复动作可以被独立复核。",
        ),
        "#48CAE4",
        "CLEAN 0   ·   TAMPERED 1   ·   ORIGINAL HASH UNCHANGED",
        ("console-08-evidence-chain.png",),
    ),
    Scene(
        "10-engineering",
        45,
        "工程闭环与可复现性",
        "结果按 Reference 与 local kind profile 分层，不把本地验证写成生产级 HA",
        "故障、部署与性能数字均来自已封存证据",
        (
            "Reference all-fault：11/11",
            "local 3-node kind：安装 / 升级 / 接管 / 网络策略 / 回滚 PASS",
            "incremental p95：45.109 / 42.141 / 43.934 ms",
            "三轮单侧 95% bootstrap 上界均 < 50 ms",
        ),
        (
            "工程侧，Reference 最终候选通过十一项全故障场景。",
            "本地三节点 kind profile 的安装、升级、迁移重跑、接管、网络策略和回滚全部通过。",
            "十并发、三轮各五百次成对写中，incremental p 九十五分别为四十五点一零九、四十二点一四一和四十三点九三四毫秒；三轮单侧百分之九十五 bootstrap 上界都小于五十毫秒。",
            "这些数字证明 Reference 和本地 profile，不等于生产多地域高可用。",
        ),
        "#80ED99",
        "TESTED · REPLAYABLE · SCOPE-BOUNDED",
    ),
    Scene(
        "11-close",
        30,
        "能力边界",
        "结论只覆盖可追溯证据支持的范围",
        "XA-Guard · XA-202620",
        (
            "真实 D1 sources 引用解析与敏感资产查询边界尚未修复",
            "OAR 数字不外推为通用攻击率",
            "MCP downstream 为脱敏测试目标，不执行真实运维命令",
            "生产仍需组织 IdP、KMS/HSM、TLS、备份和容量验收",
        ),
        (
            "最后重申边界：真实 D1 sources 引用解析与敏感资产查询边界尚未修复；OAR 数字不外推为通用攻击率；演示 MCP 下游只记录脱敏调用；本地 kind 不代替生产验收。",
            "XA-Guard，XA-202620：前有身份，途中六关，后有撤销，全程有证据。",
        ),
        "#35D7A4",
        "前有身份 · 途中六关 · 后有撤销 · 全程有证据",
    ),
)


def _font_path(*names: str) -> Path:
    fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for name in names:
        candidate = fonts / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"required font not found: {', '.join(names)}")


FONT_REGULAR = _font_path("msyh.ttc", "simhei.ttf")
FONT_BOLD = _font_path("msyhbd.ttc", "msyh.ttc", "simhei.ttf")
FONT_MONO = _font_path("consola.ttf", "cour.ttf")


def font(size: int, *, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_MONO if mono else FONT_BOLD if bold else FONT_REGULAR
    return ImageFont.truetype(str(path), size)


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def wrap_text(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        trial = current + char
        if current and draw.textbbox((0, 0), trial, font=face)[2] > width:
            lines.append(current)
            current = char
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    face: ImageFont.FreeTypeFont,
    fill: str,
    width: int,
    spacing: int = 12,
) -> int:
    x, y = xy
    lines = wrap_text(draw, text, face, width)
    bbox = draw.textbbox((0, 0), "国Ag", font=face)
    line_height = bbox[3] - bbox[1] + spacing
    for line in lines:
        draw.text((x, y), line, font=face, fill=fill)
        y += line_height
    return y


def rounded_screenshot(path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as source:
        shot = ImageOps.fit(source.convert("RGB"), size, method=Image.Resampling.LANCZOS)
    mask = Image.new("L", size, 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, size[0], size[1]), radius=24, fill=255)
    shot.putalpha(mask)
    return shot


def background(accent: str) -> Image.Image:
    base = Image.new("RGB", (WIDTH, HEIGHT), "#07131F")
    glow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    ar, ag, ab = hex_rgb(accent)
    gdraw.ellipse((1260, -500, 2240, 480), fill=(ar, ag, ab, 75))
    gdraw.ellipse((-430, 690, 520, 1530), fill=(ar, ag, ab, 38))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    base = Image.alpha_composite(base.convert("RGBA"), glow)
    grid = Image.new("RGBA", base.size, (0, 0, 0, 0))
    grid_draw = ImageDraw.Draw(grid)
    for x in range(0, WIDTH, 80):
        grid_draw.line((x, 0, x, HEIGHT), fill=(255, 255, 255, 8), width=1)
    for y in range(0, HEIGHT, 80):
        grid_draw.line((0, y, WIDTH, y), fill=(255, 255, 255, 8), width=1)
    return Image.alpha_composite(base, grid)


def draw_header(draw: ImageDraw.ImageDraw, scene: Scene, index: int) -> None:
    accent = scene.accent
    eyebrow_face = font(25, bold=True)
    eyebrow_width = min(680, draw.textbbox((0, 0), scene.eyebrow, font=eyebrow_face)[2] + 54)
    draw.rounded_rectangle((72, 58, 72 + eyebrow_width, 112), radius=27, fill=accent)
    draw.text((99, 70), scene.eyebrow, font=font(25, bold=True), fill="#06131D")
    draw.text((1690, 69), f"{index:02d} / {len(SCENES):02d}", font=font(24, mono=True), fill="#8EA7B7")
    title_size = 55 if len(scene.title) <= 25 else 44
    title_bottom = draw_wrapped(
        draw,
        (72, 151),
        scene.title,
        font(title_size, bold=True),
        "#F5FAFD",
        1760,
        8,
    )
    draw_wrapped(draw, (76, title_bottom + 7), scene.subtitle, font(27), "#A8BFCD", 1760, 8)


def draw_metric(draw: ImageDraw.ImageDraw, scene: Scene) -> None:
    if not scene.metric:
        return
    draw.rounded_rectangle((72, 930, 1848, 1008), radius=24, fill="#0D2332", outline=scene.accent, width=2)
    metric_face = font(27, bold=True, mono=scene.metric.isascii())
    draw.text((110, 952), scene.metric, font=metric_face, fill=scene.accent)


def draw_standard(scene: Scene, index: int) -> Image.Image:
    image = background(scene.accent)
    draw = ImageDraw.Draw(image)
    draw_header(draw, scene, index)
    top = 350
    for bullet_index, bullet in enumerate(scene.bullets, start=1):
        y = top + (bullet_index - 1) * 125
        draw.rounded_rectangle((80, y, 142, y + 62), radius=18, fill=scene.accent)
        draw.text((100, y + 12), f"{bullet_index}", font=font(27, bold=True, mono=True), fill="#07131F")
        draw_wrapped(draw, (177, y + 5), bullet, font(31, bold=bullet_index == 1), "#F1F7FA", 1590, 9)
    draw_metric(draw, scene)
    return image


def draw_real_client(scene: Scene, index: int) -> Image.Image:
    image = background(scene.accent)
    draw = ImageDraw.Draw(image)
    draw_header(draw, scene, index)
    draw.rounded_rectangle((72, 340, 1120, 875), radius=28, fill="#071018", outline="#25475A", width=2)
    draw.ellipse((105, 373, 125, 393), fill="#FF5F56")
    draw.ellipse((139, 373, 159, 393), fill="#FFBD2E")
    draw.ellipse((173, 373, 193, 393), fill="#27C93F")
    terminal = (
        "$ opencode mcp list\n"
        "✓ xa_guard_l3_http  connected\n"
        "  http://127.0.0.1:18765/mcp\n"
        "  1 server(s)\n\n"
        "model  deepseek/deepseek-v4-flash\n"
        "tool   xa_guard_l3_http_get_cpu\n"
        "input  { host: web03 }\n"
        "output { host: web03, cpu: 85% }\n\n"
        "verified 1 record · 0 errors"
    )
    y = 420
    for line in terminal.splitlines():
        color = scene.accent if line.startswith(("✓", "tool", "verified")) else "#D8E6ED"
        draw.text((110, y), line, font=font(27, mono=True), fill=color)
        y += 40
    draw.rounded_rectangle((1170, 340, 1848, 875), radius=28, fill="#0D2332", outline="#25475A", width=2)
    y = 390
    for bullet in scene.bullets:
        draw.ellipse((1218, y + 10, 1236, y + 28), fill=scene.accent)
        y = draw_wrapped(draw, (1262, y), bullet, font(28, bold=True), "#F1F7FA", 520, 10) + 34
    draw_metric(draw, scene)
    return image


def draw_causal(scene: Scene, index: int) -> Image.Image:
    image = background(scene.accent)
    draw = ImageDraw.Draw(image)
    draw_header(draw, scene, index)
    draw.rounded_rectangle((72, 348, 1848, 850), radius=30, fill="#0A1D2A", outline="#25475A", width=2)
    draw.text((130, 390), "IMMUTABLE ToolIntent", font=font(28, bold=True, mono=True), fill=scene.accent)
    draw.line((520, 434, 1395, 434), fill="#496A7D", width=5)
    draw.polygon(((1365, 420), (1405, 434), (1365, 448)), fill="#496A7D")
    panels = (
        (120, "NULL ARM", "10 / 10", "HARM", "#EF476F"),
        (980, "XA-GUARD", "0 / 10", "HARM", "#35D7A4"),
    )
    for x, label, value, suffix, color in panels:
        draw.rounded_rectangle((x, 485, x + 720, 782), radius=24, fill="#102B3B", outline=color, width=3)
        draw.text((x + 38, 522), label, font=font(28, bold=True, mono=True), fill=color)
        draw.text((x + 38, 585), value, font=font(82, bold=True, mono=True), fill="#F5FAFD")
        draw.text((x + 440, 632), suffix, font=font(33, bold=True, mono=True), fill=color)
        foot = "downstream executed" if label == "NULL ARM" else "Gate3 deny 10/10"
        draw.text((x + 40, 730), foot, font=font(25, mono=True), fill="#A8BFCD")
    draw_metric(draw, scene)
    return image


def draw_screenshot_scene(scene: Scene, index: int) -> Image.Image:
    image = background(scene.accent)
    draw = ImageDraw.Draw(image)
    draw_header(draw, scene, index)
    if len(scene.screenshots) == 1:
        shot = rounded_screenshot(SCREENSHOT_DIR / scene.screenshots[0], (1030, 545))
        image.alpha_composite(shot, (72, 342))
        panel = (1140, 342, 1848, 887)
        draw.rounded_rectangle(panel, radius=26, fill="#0D2332", outline="#25475A", width=2)
        y = 390
        for bullet in scene.bullets:
            draw.ellipse((1182, y + 10, 1200, y + 28), fill=scene.accent)
            y = draw_wrapped(draw, (1226, y), bullet, font(27, bold=True), "#F1F7FA", 560, 9) + 30
    else:
        positions = ((72, 342), (530, 342), (988, 342), (1446, 342))
        labels = ("CREATE", "REQUEST", "APPROVE", "COMPENSATE")
        for pos, label, screenshot in zip(positions, labels, scene.screenshots, strict=True):
            shot = rounded_screenshot(SCREENSHOT_DIR / screenshot, (402, 430))
            image.alpha_composite(shot, pos)
            draw.rounded_rectangle((pos[0] + 22, 792, pos[0] + 380, 852), radius=20, fill="#0D2332")
            draw.text((pos[0] + 44, 807), label, font=font(24, bold=True, mono=True), fill=scene.accent)
    draw_metric(draw, scene)
    return image


def render_slide(scene: Scene, index: int, path: Path) -> None:
    if scene.slug == "02-real-client":
        image = draw_real_client(scene, index)
    elif scene.slug == "03-live-causal":
        image = draw_causal(scene, index)
    elif scene.screenshots:
        image = draw_screenshot_scene(scene, index)
    else:
        image = draw_standard(scene, index)
    image.convert("RGB").save(path, "PNG", optimize=True)


def run(command: list[str], *, cwd: Path | None = None) -> None:
    printable = " ".join(command[:5])
    print(f"[run] {printable} …", flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def require_tool(name: str) -> str:
    resolved = shutil.which(name)
    if not resolved:
        raise RuntimeError(f"required executable is not available: {name}")
    return resolved


def synthesize_narration(text: str, path: Path, rate: int) -> None:
    payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
    environment = os.environ.copy()
    environment["XA_D3_TTS_TEXT_B64"] = payload
    environment["XA_D3_TTS_OUTPUT"] = str(path)
    environment["XA_D3_TTS_RATE"] = str(rate)
    script = (
        "$ErrorActionPreference='Stop'; "
        "Add-Type -AssemblyName System.Speech; "
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.SelectVoice('Microsoft Huihui Desktop'); "
        "$s.Rate=[int]$env:XA_D3_TTS_RATE; "
        "$t=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($env:XA_D3_TTS_TEXT_B64)); "
        "$s.SetOutputToWaveFile($env:XA_D3_TTS_OUTPUT); "
        "$s.Speak($t); "
        "$s.Dispose()"
    )
    print("[run] powershell offline narration …", flush=True)
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        cwd=ROOT,
        env=environment,
        check=True,
    )


def probe_duration(ffprobe: str, path: Path) -> float:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def timestamp(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def subtitle_entries() -> Iterable[tuple[float, float, str]]:
    offset = 0.0
    for scene in SCENES:
        usable = scene.duration - 2.0
        weights = [max(1, len(sentence)) for sentence in scene.narration]
        total = sum(weights)
        cursor = offset + 1.0
        for sentence, weight in zip(scene.narration, weights, strict=True):
            duration = usable * weight / total
            end = min(offset + scene.duration - 0.6, cursor + duration)
            yield cursor, end, sentence
            cursor = end
        offset += scene.duration


def write_srt(path: Path) -> None:
    chunks: list[str] = []
    for index, (start, end, text) in enumerate(subtitle_entries(), start=1):
        chunks.append(f"{index}\n{timestamp(start)} --> {timestamp(end)}\n{text}\n")
    path.write_text("\n".join(chunks), encoding="utf-8-sig")


def build_scene_video(
    ffmpeg: str,
    ffprobe: str,
    scene: Scene,
    slide: Path,
    narration: Path,
    output: Path,
) -> dict[str, float]:
    audio_duration = probe_duration(ffprobe, narration)
    target_audio = scene.duration - 1.0
    speed = max(1.0, audio_duration / target_audio)
    audio_filter = f"atempo={speed:.8f},apad=pad_dur={scene.duration}"
    video_filter = (
        "zoompan="
        "z='min(zoom+0.000035,1.018)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        "d=1:s=1920x1080:fps=30,"
        "format=yuv420p"
    )
    run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-framerate",
            str(FPS),
            "-i",
            str(slide),
            "-i",
            str(narration),
            "-vf",
            video_filter,
            "-af",
            audio_filter,
            "-t",
            str(scene.duration),
            "-r",
            str(FPS),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-pix_fmt",
            "yuv420p",
            str(output),
        ]
    )
    return {"source_audio_seconds": audio_duration, "atempo": speed}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ffprobe_metadata(ffprobe: str, path: Path) -> dict[str, object]:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,bit_rate:stream=index,codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels:stream_tags=language",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def validate_metadata(metadata: dict[str, object]) -> None:
    format_meta = metadata["format"]
    streams = metadata["streams"]
    duration = float(format_meta["duration"])
    if not 1.0 <= duration < 600.0:
        raise RuntimeError(f"video duration violates D3 limit: {duration:.3f}s")
    video = next(stream for stream in streams if stream["codec_type"] == "video")
    audio = next(stream for stream in streams if stream["codec_type"] == "audio")
    subtitle = next(stream for stream in streams if stream["codec_type"] == "subtitle")
    expected = {
        "video codec": (video["codec_name"], "h264"),
        "width": (video["width"], WIDTH),
        "height": (video["height"], HEIGHT),
        "frame rate": (video["r_frame_rate"], "30/1"),
        "audio codec": (audio["codec_name"], "aac"),
        "sample rate": (audio["sample_rate"], "48000"),
        "channels": (audio["channels"], 2),
        "subtitle codec": (subtitle["codec_name"], "mov_text"),
        "subtitle language": (subtitle.get("tags", {}).get("language"), "chi"),
    }
    failures = [f"{name}: {actual!r} != {wanted!r}" for name, (actual, wanted) in expected.items() if actual != wanted]
    if failures:
        raise RuntimeError("D3 media validation failed: " + "; ".join(failures))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-build", action="store_true", help="retain intermediate PNG/WAV/MP4 files")
    parser.add_argument(
        "--reuse-segments",
        action="store_true",
        help="reuse existing intermediate scene MP4/WAV files and only rebuild concat/final encoding",
    )
    parser.add_argument("--tts-rate", type=int, default=0, choices=range(-10, 11), metavar="-10..10")
    args = parser.parse_args()

    ffmpeg = require_tool("ffmpeg")
    ffprobe = require_tool("ffprobe")
    require_tool("powershell")

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    caption_path = BUILD_DIR / "captions.srt"
    write_srt(caption_path)
    scene_outputs: list[Path] = []
    scene_meta: list[dict[str, object]] = []

    for index, scene in enumerate(SCENES, start=1):
        slide = BUILD_DIR / f"{scene.slug}.png"
        narration = BUILD_DIR / f"{scene.slug}.wav"
        segment = BUILD_DIR / f"{scene.slug}.mp4"
        print(f"[scene {index:02d}] {scene.title}", flush=True)
        if args.reuse_segments and slide.is_file() and narration.is_file() and segment.is_file():
            audio_duration = probe_duration(ffprobe, narration)
            audio_meta = {
                "source_audio_seconds": audio_duration,
                "atempo": max(1.0, audio_duration / (scene.duration - 1.0)),
            }
            print("[reuse] existing scene assets", flush=True)
        else:
            render_slide(scene, index, slide)
            synthesize_narration("".join(scene.narration), narration, args.tts_rate)
            audio_meta = build_scene_video(ffmpeg, ffprobe, scene, slide, narration, segment)
        scene_outputs.append(segment)
        scene_meta.append(
            {
                "index": index,
                "slug": scene.slug,
                "title": scene.title,
                "target_seconds": scene.duration,
                **audio_meta,
            }
        )

    concat = BUILD_DIR / "concat.txt"
    concat.write_text(
        "\n".join(f"file '{path.name}'" for path in scene_outputs) + "\n",
        encoding="utf-8",
    )
    joined = BUILD_DIR / "joined.mp4"
    run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat.name,
            "-c",
            "copy",
            joined.name,
        ],
        cwd=BUILD_DIR,
    )

    final_video = OUTPUT_DIR / VIDEO_NAME
    run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            joined.name,
            "-i",
            caption_path.name,
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-map",
            "1:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-c:s",
            "mov_text",
            "-metadata:s:s:0",
            "language=chi",
            "-disposition:s:0",
            "none",
            "-movflags",
            "+faststart",
            str(final_video),
        ],
        cwd=BUILD_DIR,
    )

    final_srt = OUTPUT_DIR / f"{Path(VIDEO_NAME).stem}.srt"
    shutil.copy2(caption_path, final_srt)
    digest = sha256(final_video)
    sha_path = final_video.with_suffix(final_video.suffix + ".sha256")
    sha_path.write_text(f"{digest}  {final_video.name}\n", encoding="ascii")
    media_meta = ffprobe_metadata(ffprobe, final_video)
    validate_metadata(media_meta)

    metadata = {
        "schema": "xa-guard-d3-video/v1",
        "competition_code": "XA-202620",
        "title": "面向政企场景的大模型智能体安全关键技术研究",
        "narration": {
            "method": "offline Windows System.Speech",
            "voice": "Microsoft Huihui Desktop",
            "rate": args.tts_rate,
            "disclosure": "machine-synthesized narration; no claim of human recording",
        },
        "privacy": {
            "attack_payloads_embedded": False,
            "credentials_embedded": False,
            "raw_audit_records_embedded": False,
            "absolute_paths_embedded": False,
        },
        "scenes": scene_meta,
        "expected_total_seconds": sum(scene.duration for scene in SCENES),
        "sha256": digest,
        "media": media_meta,
    }
    metadata_path = OUTPUT_DIR / f"{Path(VIDEO_NAME).stem}.metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"video": str(final_video), "sha256": digest, "media": media_meta}, ensure_ascii=False, indent=2))

    if not args.keep_build:
        for item in BUILD_DIR.iterdir():
            if item.is_file():
                item.unlink()
        try:
            BUILD_DIR.rmdir()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"command failed with exit code {exc.returncode}", file=sys.stderr)
        raise
