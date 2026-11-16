#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""列出 Obsidian 库里已有的标签及其出现次数。

用法:
    python -I vault_tags.py "E:\\Obsidian-document\\文献笔记\\文献笔记"

只读。扫描库内所有 .md 文件的 YAML frontmatter `tags` 字段，
同时收集正文中的 #标签，按出现次数排序输出，并按层级前缀分组。
"""

import os
import re
import sys
from collections import Counter, defaultdict

# Windows 控制台默认 GBK，会把中文标签打成乱码
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

SKIP_DIRS = {".obsidian", ".trash", "_assets", ".git"}

# frontmatter 内联写法: tags: [a, b, c]
INLINE_RE = re.compile(r"^tags\s*:\s*\[(.*?)\]\s*$", re.IGNORECASE)
# frontmatter 块写法: tags:\n  - a\n  - b
BLOCK_START_RE = re.compile(r"^tags\s*:\s*$", re.IGNORECASE)
LIST_ITEM_RE = re.compile(r"^\s*-\s*(.+?)\s*$")
# 正文行内标签 #主题/xxx
BODY_TAG_RE = re.compile(r"(?<![\w&])#([^\s#,\[\]()（）、。，]+)")


def read_text(path):
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, LookupError):
            continue
    return None


def split_frontmatter(text):
    """返回 (frontmatter 文本, 正文文本)。没有 frontmatter 时前者为空串。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return "", text
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:])
    return "", text


def clean_tag(raw):
    tag = raw.strip().strip("\"'").strip()
    if tag.startswith("#"):
        tag = tag[1:]
    return tag.strip()


def tags_from_frontmatter(fm):
    tags = []
    lines = fm.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = INLINE_RE.match(line.strip())
        if m:
            for part in m.group(1).split(","):
                t = clean_tag(part)
                if t:
                    tags.append(t)
            i += 1
            continue
        if BLOCK_START_RE.match(line.strip()):
            i += 1
            while i < len(lines):
                item = LIST_ITEM_RE.match(lines[i])
                if not item:
                    break
                t = clean_tag(item.group(1))
                if t:
                    tags.append(t)
                i += 1
            continue
        i += 1
    return tags


def main():
    if len(sys.argv) < 2:
        print("用法: python -I vault_tags.py <Obsidian 库根目录>", file=sys.stderr)
        return 2

    vault = os.path.abspath(sys.argv[1])
    if not os.path.isdir(vault):
        print("目录不存在: %s" % vault, file=sys.stderr)
        return 2

    counter = Counter()
    tag_files = defaultdict(list)
    note_count = 0

    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            if not name.lower().endswith(".md"):
                continue
            path = os.path.join(root, name)
            text = read_text(path)
            if text is None:
                print("读取失败，已跳过: %s" % path, file=sys.stderr)
                continue
            note_count += 1
            fm, body = split_frontmatter(text)
            found = set(tags_from_frontmatter(fm))
            for m in BODY_TAG_RE.finditer(body):
                t = clean_tag(m.group(1))
                # 排除纯数字（markdown 标题或锚点误匹配）
                if t and not t.isdigit():
                    found.add(t)
            rel = os.path.relpath(path, vault)
            for t in found:
                counter[t] += 1
                tag_files[t].append(rel)

    print("库: %s" % vault)
    print("扫描到 %d 篇笔记，%d 个不同标签\n" % (note_count, len(counter)))

    if not counter:
        print("库里还没有任何标签。这是第一篇带标签的笔记，")
        print("标签体系从这里开始建立，后续笔记应尽量复用。")
        return 0

    groups = defaultdict(list)
    for tag, n in counter.items():
        prefix = tag.split("/")[0] if "/" in tag else "（无层级）"
        groups[prefix].append((tag, n))

    def group_key(item):
        prefix, items = item
        return (prefix == "（无层级）", -sum(n for _, n in items), prefix)

    for prefix, items in sorted(groups.items(), key=group_key):
        print("[%s]" % prefix)
        for tag, n in sorted(items, key=lambda x: (-x[1], x[0])):
            files = tag_files[tag]
            shown = files[0] if len(files) == 1 else "%s 等 %d 篇" % (files[0], len(files))
            print("  %-28s %2d 次   %s" % (tag, n, shown))
        print()

    print("推荐标签时优先从上面复用；确有必要新建时，沿用已有的层级前缀和措辞粒度。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
