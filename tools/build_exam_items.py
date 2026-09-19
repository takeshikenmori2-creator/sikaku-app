#!/usr/bin/env python3
"""抽出済みの設問テキストと模範解答を突き合わせ、枝問単位の項目一覧を作る。

    python3 tools/build_exam_items.py --exam data/exam --answers data/exam/answers.json \
        --out data/exam/items.json

出力は 1 枝問 1 レコード。type は maru_batsu（○×）/ fill（穴埋め）/ choice（選択）/
combo（正誤の組合せ）/ other。ここまでは機械的な整形で、4択への組み直しは次の工程。
"""
import argparse
import json
import pathlib
import re

Z2H = str.maketrans("０１２３４５６７８９", "0123456789")
DAIMON = re.compile(r"^\s*([0-9０-９]{1,2})\s*[．.]\s*")
EDA = re.compile(r"^\s*(?:[（(]\s*([0-9０-９]{1,2}|[ア-ン]|[A-ZＡ-Ｚ])\s*[）)]|([①-⑳]))\s*")
SUBJ = re.compile(r"^令和[0-9０-９一二三四五六七八九十元]+年\s*([0-9０-９]{1,2})\s*[．.]\s*(.+?)\s*$")
POINTS = re.compile(r"[（(]\s*([0-9０-９]{1,2})\s*点\s*[）)]")


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def classify(instruction: str) -> str:
    t = norm(instruction)
    if "正しい組み合わせ" in t or "正しい組合せ" in t or "正誤について" in t:
        return "combo"
    if ("○" in t or "〇" in t) and "×" in t:
        return "maru_batsu"
    if "に入る" in t or "当てはまる" in t or "あてはまる" in t:
        return "fill_bank" if ("語群" in t or "選択肢" in t) else "fill"
    if "選び" in t or "選べ" in t:
        return "choice"
    return "other"


def subject_blocks(doc: dict):
    """(科目番号, 科目名, 本文行) を返す。ページをまたぐ科目はつなぐ。"""
    blocks: list[dict] = []
    for pg in doc["pages"]:
        lines = pg["lines"]
        if not lines:
            continue
        m = SUBJ.match(lines[0].strip())
        if m:
            blocks.append({"no": int(m.group(1).translate(Z2H)), "name": m.group(2), "lines": lines[1:]})
        elif blocks and "時限目" not in "".join(lines[:4]):
            blocks[-1]["lines"].extend(lines)
    return blocks


def split_daimon(lines: list[str]):
    out, cur = [], None
    for ln in lines:
        m = DAIMON.match(ln)
        # 「１．」で始まり、かつ直後が本文らしい行を大問の始まりとみなす
        if m and len(ln) > len(m.group(0)) + 4:
            cur = {"no": int(m.group(1).translate(Z2H)), "lines": [ln[m.end():]]}
            out.append(cur)
        elif cur is not None:
            cur["lines"].append(ln)
    return out


def split_eda(text: str):
    """本文を (枝ラベル, 本文) に割る。最初の枝より前は設問の指示文。"""
    parts = re.split(r"(?=(?:[（(]\s*(?:[0-9０-９]{1,2}|[ア-ン]|[A-ZＡ-Ｚ])\s*[）)]|[①-⑳]))", text)
    head, eds = "", []
    for p in parts:
        m = EDA.match(p)
        if m:
            lab = (m.group(1) or m.group(2)).translate(Z2H)
            eds.append((lab, p[m.end():].strip()))
        elif not eds:
            head += p
    return head.strip(), eds


CIRCLED = {c: str(i + 1) for i, c in enumerate("①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exam", type=pathlib.Path, required=True)
    ap.add_argument("--answers", type=pathlib.Path, required=True)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    args = ap.parse_args()

    answers = json.loads(args.answers.read_text(encoding="utf-8"))
    ans_by = {}
    for k, v in answers.items():
        y, no, name = k.split("/", 2)
        ans_by[(int(y), int(no))] = {"name": name, "ans": v}

    items = []
    for f in sorted(args.exam.glob("*_hikki.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        year = doc["year"]
        for blk in subject_blocks(doc):
            key = (year, blk["no"])
            akey = ans_by.get(key, {}).get("ans", {})
            body = "".join(blk["lines"])
            for dm in split_daimon(blk["lines"]):
                text = "".join(dm["lines"])
                head, eds = split_eda(text)
                typ = classify(head)
                pts = POINTS.search(head)
                for lab, t in eds:
                    a = akey.get(f"{dm['no']}-{lab}")
                    if a is None and lab in CIRCLED:
                        a = akey.get(f"{dm['no']}-{CIRCLED[lab]}")
                    items.append({
                        "year": year,
                        "subject_no": blk["no"],
                        "subject": ans_by.get(key, {}).get("name") or blk["name"],
                        "daimon": dm["no"],
                        "eda": lab,
                        "type": typ,
                        "points": int(pts.group(1).translate(Z2H)) if pts else None,
                        "instruction": POINTS.sub("", head).strip(),
                        "text": t,
                        "answer": a,
                    })
            if not split_daimon(blk["lines"]):
                items.append({"year": year, "subject_no": blk["no"],
                              "subject": ans_by.get(key, {}).get("name") or blk["name"],
                              "daimon": 0, "eda": "", "type": "other",
                              "points": None, "instruction": "", "text": body, "answer": None})

    args.out.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")

    import collections
    c = collections.Counter(i["type"] for i in items)
    matched = sum(1 for i in items if i["answer"])
    print(f"{len(items)} 枝問 / うち解答が付いたもの {matched}")
    for k, v in c.most_common():
        m = sum(1 for i in items if i["type"] == k and i["answer"])
        print(f"  {k:12s} {v:5d}  (解答あり {m})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
