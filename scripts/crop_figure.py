"""从 PDF 里裁出一张图（整张 Figure、其中几个子图，或任意区域），存成 PNG。

依赖: PyMuPDF (pip install pymupdf)

四种用法，区域的确定方式不同:

  1) 整张 Figure —— 合并 MinerU 给出的该图所有面板坐标
     python -I crop_figure.py --pdf P.pdf --extraction <提取目录> --figure "Fig. 2" --out OUT.png

  2) 子图 —— 只合并指定的面板（路径取自 figure_index.py 的输出）
     python -I crop_figure.py --pdf P.pdf --extraction <提取目录> --panels images/a.jpg images/b.jpg --out OUT.png

  3) 手动区域 —— 页面归一化坐标 x0,y0,x1,y1，范围 0-1000，左上角为原点
     python -I crop_figure.py --pdf P.pdf --page 4 --bbox 80,60,920,640 --out OUT.png

  4) 整页
     python -I crop_figure.py --pdf P.pdf --page 4 --out OUT.png

裁出的区域会在四周各加 --margin（默认 12，即页面宽高的 1.2%），因为
MinerU 的面板坐标常常不含面板字母和坐标轴标签。裁完务必打开图片检查
是否完整；不完整时加大 --margin，或改用 --bbox 手动指定。
"""

import argparse
import sys
from pathlib import Path

# -I 模式下脚本所在目录不在 sys.path 里，这里显式加入以复用 figure_index
sys.path.insert(0, str(Path(__file__).resolve().parent))
from figure_index import collect_figures, load_blocks, locate_content_list, normalize_label  # noqa: E402


def fail(message, code=1):
    print(message)
    return code


def import_pymupdf():
    """导入 PyMuPDF；找不到时返回 None。

    pip 在装不进 Python 自身目录时会装到用户级 site-packages，而 -I 模式
    会屏蔽这个目录。所以第一次导入失败后，把它补进搜索路径再试一次。
    """
    try:
        import pymupdf

        return pymupdf
    except ImportError:
        pass

    import site

    try:
        user_site = site.getusersitepackages()
    except Exception:
        user_site = None
    if user_site and Path(user_site).is_dir() and user_site not in sys.path:
        site.addsitedir(user_site)
        try:
            import pymupdf

            return pymupdf
        except ImportError:
            pass

    try:
        import fitz  # 旧版 PyMuPDF 的模块名

        return fitz
    except ImportError:
        return None


def union_bbox(panels):
    boxes = [p["bbox"] for p in panels if p["bbox"]]
    if not boxes:
        return None
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def resolve_region(args):
    """返回 (page, bbox 或 None, 错误信息)。bbox 为 None 表示整页。"""
    if args.bbox:
        if not args.page:
            return None, None, "--bbox 需要同时给出 --page。"
        try:
            bbox = [float(v) for v in args.bbox.split(",")]
        except ValueError:
            return None, None, "--bbox 格式应为 x0,y0,x1,y1（0-1000 的数字）。"
        if len(bbox) != 4 or bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
            return None, None, "--bbox 需要 4 个数，且 x0<x1、y0<y1。"
        return args.page, bbox, None

    if args.figure or args.panels:
        if not args.extraction:
            return None, None, "--figure 和 --panels 需要同时给出 --extraction。"
        source = locate_content_list(args.extraction)
        if source is None:
            return None, None, f"未找到 content_list.json: {args.extraction}"
        figures, leftovers = collect_figures(load_blocks(source), source.parent)

        if args.panels:
            every = [p for fig in figures for p in fig["panels"]]
            every += [p for panels in leftovers.values() for p in panels]
            wanted = []
            for name in args.panels:
                key = Path(name).name
                hits = [p for p in every if Path(p["path"]).name == key]
                if not hits:
                    return None, None, f"content_list.json 里没有这个面板: {name}"
                wanted.append(hits[0])
            label = "指定面板"
        else:
            target = normalize_label(args.figure)
            hits = [fig for fig in figures if normalize_label(fig["label"]) == target]
            if not hits:
                known = "、".join(fig["label"] for fig in figures) or "无"
                return None, None, f"没有识别到 {args.figure}。已识别的图: {known}"
            wanted = hits[0]["panels"]
            label = hits[0]["label"]
            if not wanted:
                return hits[0]["page"], None, None  # 没有面板坐标，退回整页

        pages = {p["page"] for p in wanted}
        if len(pages) != 1:
            return None, None, f"{label} 的面板分布在多页 {sorted(pages)}，请分别裁剪或改用 --page/--bbox。"
        bbox = union_bbox(wanted)
        return pages.pop(), bbox, None

    if args.page:
        return args.page, None, None
    return None, None, "请给出 --figure、--panels、--bbox 或 --page 之一。"


def main():
    parser = argparse.ArgumentParser(description="从 PDF 裁出图片", add_help=True)
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--extraction", help="MinerU 提取目录")
    parser.add_argument("--figure", help='图号，例如 "Fig. 2"')
    parser.add_argument("--panels", nargs="+", help="面板图片路径（子图）")
    parser.add_argument("--page", type=int, help="PDF 页码，从 1 开始")
    parser.add_argument("--bbox", help="x0,y0,x1,y1，页面归一化坐标 0-1000")
    parser.add_argument("--margin", type=float, default=12.0)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--max-side", type=int, default=3000, help="输出图片长边像素上限")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    pymupdf = import_pymupdf()
    if pymupdf is None:
        return fail(
            "缺少 PyMuPDF，无法裁图。安装命令:\n"
            f'  "{sys.executable}" -m pip install pymupdf',
            3,
        )

    pdf = Path(args.pdf)
    if not pdf.is_file():
        return fail(f"PDF 不存在: {pdf}")

    page_no, bbox, error = resolve_region(args)
    if error:
        return fail(error)

    doc = pymupdf.open(pdf)
    if not 1 <= page_no <= doc.page_count:
        return fail(f"页码 {page_no} 超出范围（该 PDF 共 {doc.page_count} 页）。")
    page = doc[page_no - 1]
    rect = page.rect

    if bbox is None:
        clip = rect
        used = [0, 0, 1000, 1000]
    else:
        used = [
            max(0.0, bbox[0] - args.margin),
            max(0.0, bbox[1] - args.margin),
            min(1000.0, bbox[2] + args.margin),
            min(1000.0, bbox[3] + args.margin),
        ]
        clip = pymupdf.Rect(
            rect.x0 + used[0] / 1000 * rect.width,
            rect.y0 + used[1] / 1000 * rect.height,
            rect.x0 + used[2] / 1000 * rect.width,
            rect.y0 + used[3] / 1000 * rect.height,
        )

    dpi = args.dpi
    longest_inch = max(clip.width, clip.height) / 72
    if longest_inch * dpi > args.max_side:
        dpi = max(72, int(args.max_side / longest_inch))

    pix = page.get_pixmap(dpi=dpi, clip=clip, alpha=False)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pix.save(out)

    print(f"已保存: {out}")
    print(f"PDF 第 {page_no} 页，{pix.width}x{pix.height} 像素，{dpi} dpi")
    print("裁剪区域（0-1000）: " + ",".join(f"{v:g}" for v in used) + ("  [整页]" if bbox is None else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
