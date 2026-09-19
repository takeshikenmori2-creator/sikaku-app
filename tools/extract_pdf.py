#!/usr/bin/env python3
"""国土交通省の海事代理士試験PDF（筆記試験問題／模範解答）を構造化テキストに変換する。

    python3 tools/extract_pdf.py downloads/*.pdf --out data/exam

空欄（解答欄の枠）はPDF上では罫線であって文字ではないため、描画された矩形の位置を
拾って本文中に 【】 として復元する。模範解答は表組みなので、ラベルと解答をx座標で
突き合わせて対応付ける。

依存: pymupdf （pip install pymupdf）
"""
import argparse
import json
import pathlib
import re
import sys

try:
    import pymupdf
except ImportError:
    sys.exit("pymupdf が要る: pip install pymupdf")

ERA = {"令和": 2018, "平成": 1988}
KANJI = str.maketrans("０１２３４５６７８９", "0123456789")


def to_year(text: str) -> int | None:
    m = re.search(r"(令和|平成)\s*(元|[0-9０-９一二三四五六七八九十]+)\s*年", text)
    if not m:
        return None
    num = m.group(2)
    if num == "元":
        n = 1
    elif num.isascii() or any(c in "０１２３４５６７８９" for c in num):
        n = int(num.translate(KANJI))
    else:
        k = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        n = sum(k.get(c, 0) for c in num) if num != "十" else 10
        if len(num) == 2 and num[0] == "十":
            n = 10 + k.get(num[1], 0)
    return ERA[m.group(1)] + n


def answer_boxes(page) -> list[tuple[float, float, float, float]]:
    """解答欄の枠を返す。枠は細い横罫線の上下ペアとして描かれているので、
    同じx範囲で上下に並ぶ2本を1つの枠とみなす。"""
    rules = []
    for d in page.get_drawings():
        r = d["rect"]
        w, h = r.x1 - r.x0, r.y1 - r.y0
        if w >= 18 and h <= 3:
            rules.append((round(r.x0, 1), round(r.x1, 1), r.y0))
    rules.sort(key=lambda t: (t[0], t[1], t[2]))
    boxes = []
    used = set()
    for i, a in enumerate(rules):
        if i in used:
            continue
        for j in range(i + 1, len(rules)):
            b = rules[j]
            if j in used or abs(b[0] - a[0]) > 2 or abs(b[1] - a[1]) > 2:
                continue
            if 6 <= b[2] - a[2] <= 40:
                boxes.append((a[0], a[1], a[2], b[2]))
                used.update({i, j})
                break
    return boxes


def page_lines(page) -> list[str]:
    """空欄を 【】 に置き換えた行のリストを返す。"""
    words = [w for w in page.get_text("words") if w[4].strip()]
    boxes = answer_boxes(page)
    if not words:
        return ["【】" * len(boxes)] if boxes else []

    words.sort(key=lambda w: (round(w[1] / 4), w[0]))
    lines: list[list[tuple]] = []
    for w in words:
        if lines and abs(w[1] - lines[-1][-1][1]) <= 4:
            lines[-1].append(w)
        else:
            lines.append([w])

    out = []
    for ln in lines:
        ln.sort(key=lambda w: w[0])
        ytop, ybot = min(w[1] for w in ln), max(w[3] for w in ln)
        row = sorted(b for b in boxes if ytop - 4 < (b[2] + b[3]) / 2 < ybot + 4)
        buf, bi = [], 0
        for w in ln:
            while bi < len(row) and row[bi][1] <= w[0] + 3:
                buf.append("【】")
                bi += 1
            buf.append(w[4])
        buf.extend("【】" for _ in row[bi:])
        out.append("".join(buf))
    return out


SUBJ_HEAD = re.compile(r"^\s*([0-9０-９]{1,2})\s*[．.]\s*(\S.*?)\s*$")


def parse_pdf(path: pathlib.Path) -> dict:
    doc = pymupdf.open(str(path))
    first = doc[0].get_text()
    year = to_year(first)
    kind = "kaitou" if "模範解答" in first else "koujutsu" if "口述" in first else "hikki"

    pages = []
    for i, pg in enumerate(doc):
        lines = page_lines(pg)
        subject = None
        for ln in lines[:4]:
            m = SUBJ_HEAD.match(ln.replace("令和", "").strip())
            if m and len(m.group(2)) <= 40 and "時限" not in m.group(2):
                subject = m.group(2)
                break
        pages.append({"page": i + 1, "subject": subject, "lines": lines})

    return {"source": path.name, "year": year, "kind": kind, "pages": pages}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("data/exam"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    for p in args.pdfs:
        d = parse_pdf(p)
        name = f"{d['year'] or 'unknown'}_{d['kind']}.json"
        (args.out / name).write_text(
            json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        subs = [pg["subject"] for pg in d["pages"] if pg["subject"]]
        print(f"{p.name} -> {name}  {d['year']}年 {d['kind']}  {len(d['pages'])}ページ  科目検出 {len(subs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
