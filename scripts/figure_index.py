"""列出 MinerU 提取目录中每张图所在的 PDF 页码和对应的面板图片。

用法:
    python -I figure_index.py "<提取目录>"

提取目录是包含 content_list.json 的那个文件夹，例如
    E:\\Zotero documents\\papers\\llm-for-zotero-mineru\\4359

MinerU 会把一张 Figure 切成多个面板图片，图注通常只挂在其中一个面板上。
本脚本按页把面板归到同页出现的图注下面，输出:
    Figure 编号 -> PDF 页码 -> 面板图片路径和坐标
归组是按"同页"推断的，同一页有多张图时可能分错，结果只用来定位页码、
查看图片和裁图，不要当作论文事实引用。

只用标准库，不需要安装任何包。crop_figure.py 复用这里的函数。
"""

import json
import re
import sys
from pathlib import Path

FIG_RE = re.compile(
    r"((?:Extended Data |Supplementary )?(?:Fig(?:ure)?\.?|Table|图|表)\s*S?\d+[A-Za-z]?)",
    re.IGNORECASE,
)
VISUAL_TYPES = {"image", "chart", "table", "figure"}


def locate_content_list(target):
    """接受提取目录或 content_list.json 本身，返回 json 文件路径；找不到返回 None。"""
    target = Path(target)
    if target.is_file():
        return target
    direct = target / "content_list.json"
    if direct.is_file():
        return direct
    if target.is_dir():
        candidates = sorted(target.glob("*content_list.json"))
        if candidates:
            return candidates[0]
    return None


def load_blocks(source):
    blocks = json.loads(Path(source).read_text(encoding="utf-8"))
    if isinstance(blocks, dict):
        blocks = blocks.get("content_list") or blocks.get("blocks") or []
    return [b for b in blocks if isinstance(b, dict)]


def caption_of(block):
    """把块里所有 *_caption 字段拼成一段文字（字段名随 MinerU 版本变化）。"""
    parts = []
    for key, value in block.items():
        if key.endswith("_caption"):
            if isinstance(value, list):
                parts.extend(str(v) for v in value)
            elif value:
                parts.append(str(value))
    return " ".join(p.strip() for p in parts if p and p.strip())


def normalize_label(label):
    """把 "Figure 2"、"Fig. 2"、"fig2" 统一成 "fig2"，用于比较图号。"""
    text = re.sub(r"[\s.]", "", (label or "").lower())
    return text.replace("figure", "fig")


def collect_figures(blocks, base):
    """返回 (figures, leftovers)。

    figures: [{label, page, caption, panels}]
    leftovers: {page: [panel]}，没能归到任何图注下的面板
    panel: {path, page, bbox, exists}，bbox 是 MinerU 给的页面归一化坐标 (0-1000)
    """
    base = Path(base)
    figures = []
    pending = {}
    for block in blocks:
        kind = block.get("type")
        page = block.get("page_idx")
        page = page + 1 if isinstance(page, int) else None

        if kind in VISUAL_TYPES:
            path = block.get("img_path") or ""
            if path:
                bbox = block.get("bbox")
                pending.setdefault(page, []).append(
                    {
                        "path": path,
                        "page": page,
                        "bbox": bbox if isinstance(bbox, list) and len(bbox) == 4 else None,
                        "exists": (base / path).is_file(),
                    }
                )
            caption = caption_of(block)
        elif kind == "text":
            caption = block.get("text", "")
            # 正文里提到 "Fig. 1" 的句子不是图注，只认以图号开头的段落
            if not FIG_RE.match(caption.strip()):
                continue
        else:
            continue

        match = FIG_RE.search(caption or "")
        if match:
            label = match.group(1)
            start = match.start(1)
            figures.append(
                {
                    "label": label,
                    "page": page,
                    "caption": caption[start : start + 110].strip(),
                    "panels": pending.pop(page, []),
                }
            )

    # 图注块有时排在同页部分面板之前；该页只有一张图时，剩下的面板也归它
    for page in list(pending):
        on_page = [fig for fig in figures if fig["page"] == page]
        if len(on_page) == 1:
            on_page[0]["panels"].extend(pending.pop(page))

    leftovers = {page: panels for page, panels in pending.items() if panels}
    return figures, leftovers


def describe_panel(panel):
    text = panel["path"]
    if panel["bbox"]:
        text += "  bbox=" + ",".join(str(v) for v in panel["bbox"])
    if not panel["exists"]:
        text += "  (文件缺失)"
    return text


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    sys.stdout.reconfigure(encoding="utf-8")

    source = locate_content_list(sys.argv[1])
    if source is None:
        print(f"未找到 content_list.json: {sys.argv[1]}")
        return 1

    figures, leftovers = collect_figures(load_blocks(source), source.parent)
    if not figures and not leftovers:
        print("content_list.json 中没有识别到图或表。请改为对照 PDF 页面读图。")
        return 0

    print(f"来源: {source}")
    print(f"识别到 {len(figures)} 个带编号的图/表\n")
    for fig in figures:
        print(f"{fig['label']}  ->  PDF 第 {fig['page']} 页")
        print(f"  图注开头: {fig['caption']}")
        for panel in fig["panels"]:
            print(f"  面板: {describe_panel(panel)}")
        if not fig["panels"]:
            print("  面板: (同页面板已归到前一张图，或该图没有被切出图片)")
        print()

    if leftovers:
        print("没有匹配到图注的图片（可能是跨页图、补充图或公式截图）:")
        for page in sorted(leftovers, key=lambda p: (p is None, p)):
            for panel in leftovers[page]:
                print(f"  第 {page} 页: {describe_panel(panel)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
