#!/usr/bin/env python3
"""模範解答PDFを {年/科目番号/科目名: {大問-枝番: 解答}} に変換する。

模範解答は罫線表なので find_tables() でセル単位に読み、ラベル行の直下を解答行として
列位置で対応付ける。文字がアウトライン化されていてテキストを持たないページは
検出して報告するだけにし、そのページは手で補う（--missing-out にページ一覧を書く）。

    python3 tools/parse_answers.py downloads/*_kaitou.pdf --out data/exam/answers.json
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
K = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
Z2H = str.maketrans("０１２３４５６７８９", "0123456789")

# 枝番ラベル: (１) （ア） ① ア イ Ａ など
LABEL = re.compile(r"^[（(]?\s*([0-9０-９]{1,2}|[ア-ン]|[A-ZＡ-Ｚa-z]|[①-⑳])\s*[）)]?$")
DAIMON = re.compile(r"^([0-9０-９]{1,2})\s*[．.]$")
HEAD = re.compile(r"([0-9０-９]{1,2})\s*[．.]\s*(.+?)\s*(?:模範解答|解答用紙)")
YEAR = re.compile(r"(令和|平成)\s*([0-9０-９一二三四五六七八九十元]+)\s*年")
CIRCLED = {c: str(i + 1) for i, c in enumerate("①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳")}
NOISE = re.compile(r"^(受\s*験\s*地|受験番号|氏\s*名|採\s*点|点|)$")


def num(s: str) -> int:
    s = s.translate(Z2H)
    if s.isdigit():
        return int(s)
    if s == "元":
        return 1
    if s == "十":
        return 10
    if len(s) == 2 and s[0] == "十":
        return 10 + K.get(s[1], 0)
    return K.get(s, 0)


def clean(c: str | None) -> str:
    return re.sub(r"\s+", "", (c or "").replace("\n", ""))


def is_label(c: str) -> bool:
    return bool(LABEL.match(c)) and c != ""


def parse_page(page, year: int):
    text = page.get_text()
    raw = re.sub(r"\s+", "", text)
    head = HEAD.search(raw)
    if not head:
        return None, {}, bool(raw.strip(" ()（）")) is False
    meta = {"year": year, "subject_no": num(head.group(1)), "subject": head.group(2)}

    answers: dict[str, str] = {}
    daimon = None
    for tab in page.find_tables().tables:
        rows = [[clean(c) for c in r] for r in tab.extract()]
        for i, row in enumerate(rows):
            cells = [c for c in row if c]
            if len(cells) == 1 and DAIMON.match(cells[0]):
                daimon = num(DAIMON.match(cells[0]).group(1))
                continue
            labs = [(j, c) for j, c in enumerate(row) if c and is_label(c)]
            if not labs or len(labs) != len(cells) or i + 1 >= len(rows):
                continue
            if any(NOISE.match(c) for c in cells):
                continue
            nxt = rows[i + 1]
            if daimon is None:
                daimon = 1
            for j, lab in labs:
                val = clean(nxt[j]) if j < len(nxt) else ""
                if val:
                    g = LABEL.match(lab).group(1)
                    g = CIRCLED.get(g, g).translate(Z2H)
                    key = f"{daimon}-{g}"
                    answers.setdefault(key, val)
    return meta, answers, False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    args = ap.parse_args()

    result: dict = {}
    blanks: list[str] = []
    for p in args.pdfs:
        doc = pymupdf.open(str(p))
        if "模範解答" not in doc[0].get_text():
            continue
        ym = YEAR.search(re.sub(r"\s+", "", doc[0].get_text()))
        year = ERA[ym.group(1)] + num(ym.group(2))
        got = 0
        for i, pg in enumerate(doc):
            if i == 0:
                continue
            meta, ans, no_text = parse_page(pg, year)
            if no_text or (meta is None and len(pg.find_tables().tables) > 0):
                blanks.append(f"{p.name}#{i + 1}")
                continue
            if not meta:
                continue
            key = f"{meta['year']}/{meta['subject_no']:02d}/{meta['subject']}"
            result.setdefault(key, {}).update(ans)
            got += len(ans)
        print(f"{p.name}: {year}年 {got} 解答")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(result)} 科目 / {sum(len(v) for v in result.values())} 解答 -> {args.out}")
    if blanks:
        print(f"テキストを持たないページ（手で補う）: {', '.join(blanks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
