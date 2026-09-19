#!/usr/bin/env python3
"""模範解答の構造（大問→枝番）を手がかりに設問本文を切り出し、枝問単位の項目を作る。

素朴に「(１)」「①」で切ると、正誤組合せの表や語群の番号まで拾ってしまう。
そこで「その大問にどの枝番が存在するか」を模範解答から先に知り、その並び順どおりに
本文中の位置を探して切る。並び順どおりに見つからない大問は unresolved として報告し、
機械処理に任せずに残す。

    python3 tools/build_items.py --exam data/exam --out data/exam/items.json
"""
import argparse
import collections
import json
import pathlib
import re

Z2H = str.maketrans("０１２３４５６７８９", "0123456789")
H2Z = str.maketrans("0123456789", "０１２３４５６７８９")
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
SUBJ = re.compile(r"^(?:令和[0-9０-９一二三四五六七八九十元]+年)?\s*([0-9０-９]{1,2})\s*[．.]\s*(\S.*?)\s*$")
POINTS = re.compile(r"[（(]\s*([0-9０-９]{1,2})\s*点\s*[）)]")


def norm(s: str) -> str:
    return re.sub(r"[ 　]+", "", s)


def label_forms(lab: str) -> list[str]:
    """枝番ラベルの表記ゆれを列挙する。"""
    out = []
    if lab.isdigit():
        z = lab.translate(H2Z)
        out += [f"({z})", f"（{z}）", f"({lab})", f"（{lab}）"]
        if len(lab) == 1 and 1 <= int(lab) <= 20:
            out.append(CIRCLED[int(lab) - 1])
    else:
        out += [f"({lab})", f"（{lab}）", lab]
    return out


def subject_blocks(doc: dict, names: dict[int, str]):
    """科目の見出し行でページを束ねる。

    見出しは「８．海上運送法」のような形だが、継続ページの先頭に大問の「２．…」が
    来ることがあり、そのままだと別科目の始まりと誤認する。模範解答から分かっている
    科目名と一致するときだけ見出しとみなすことで、この誤認を防ぐ。
    """
    blocks = []
    for pg in doc["pages"]:
        lines = [l for l in pg["lines"] if l.strip()]
        if not lines:
            continue
        joined = norm("".join(lines[:4]))
        if "時限目" in joined and "海事代理士試験" in joined:
            continue  # 中扉
        m = SUBJ.match(norm(lines[0]))
        hit = False
        if m:
            no = int(m.group(1).translate(Z2H))
            want = names.get(no)
            if want and norm(m.group(2)).startswith(norm(want)[:8]):
                blocks.append({"no": no, "name": want, "lines": lines[1:]})
                hit = True
        if not hit and blocks:
            blocks[-1]["lines"].extend(lines)
    return blocks


def split_daimon(body: str, numbers: list[int]):
    """既知の大問番号を順に探して本文を割る。見つからなければ None。"""
    spans, pos = [], 0
    for n in numbers:
        found = -1
        for form in (f"{str(n).translate(H2Z)}．", f"{n}.", f"{str(n).translate(H2Z)}.", f"{n}．"):
            i = body.find(form, pos)
            if i >= 0 and (found < 0 or i < found):
                found, flen = i, len(form)
        if found < 0:
            return None
        spans.append((n, found, found + flen))
        pos = found + flen
    out = []
    for k, (n, s, e) in enumerate(spans):
        end = spans[k + 1][1] if k + 1 < len(spans) else len(body)
        out.append((n, body[e:end]))
    return out


def split_eda(seg: str, labels: list[str]):
    """枝番の並び順どおりに位置を探して切る。(head, [(lab, text)], mode) を返す。"""
    for bracketed in (True, False):
        pos, hits = 0, []
        for lab in labels:
            best = -1
            for form in label_forms(lab):
                if bracketed and not (form.startswith("(") or form.startswith("（") or form in CIRCLED):
                    continue
                if not bracketed and (form.startswith("(") or form.startswith("（")):
                    continue
                i = pos - 1
                while True:
                    i = seg.find(form, i + 1)
                    if i < 0:
                        break
                    # 「(ア)～(オ)について」のような指示文中の参照は枝番ではない
                    if seg[i + len(form): i + len(form) + 1] in ("～", "〜"):
                        continue
                    break
                if i >= 0 and (best < 0 or i < best):
                    best, blen = i, len(form)
            if best < 0:
                hits = None
                break
            hits.append((lab, best, best + blen))
            pos = best + blen
        if hits:
            head = seg[: hits[0][1]]
            out = []
            for k, (lab, s, e) in enumerate(hits):
                end = hits[k + 1][1] if k + 1 < len(hits) else len(seg)
                out.append((lab, seg[e:end].strip()))
            return head.strip(), out, ("bracketed" if bracketed else "inline")
    return seg, [], "unresolved"


def classify(instruction: str) -> str:
    t = norm(instruction)
    if "正しい組み合わせ" in t or "正しい組合せ" in t:
        return "combo"
    if ("○" in t or "〇" in t) and "×" in t:
        return "maru_batsu"
    if "に入る" in t or "当てはまる" in t or "あてはまる" in t:
        return "fill_bank" if ("語群" in t or "選択肢" in t) else "fill"
    if "選び" in t or "選べ" in t:
        return "choice"
    return "other"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exam", type=pathlib.Path, required=True)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    args = ap.parse_args()

    answers = json.loads((args.exam / "answers.json").read_text(encoding="utf-8"))
    ans_by: dict[tuple[int, int], dict] = {}
    for k, v in answers.items():
        y, no, name = k.split("/", 2)
        ans_by[(int(y), int(no))] = {"name": name, "ans": v}

    items, unresolved = [], []
    for f in sorted(args.exam.glob("*_hikki.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        year = doc["year"]
        names = {no: rec["name"] for (y, no), rec in ans_by.items() if y == year}
        for blk in subject_blocks(doc, names):
            rec = ans_by.get((year, blk["no"]))
            if not rec:
                unresolved.append({"year": year, "subject_no": blk["no"], "why": "模範解答なし"})
                continue
            grouped: dict[int, list[str]] = collections.defaultdict(list)
            for key in rec["ans"]:
                d, lab = key.split("-", 1)
                grouped[int(d)].append(lab)
            body = norm("".join(blk["lines"]))
            dm = split_daimon(body, sorted(grouped))
            if dm is None:
                unresolved.append({"year": year, "subject_no": blk["no"],
                                   "subject": rec["name"], "why": "大問を特定できない"})
                continue
            for n, seg in dm:
                labs = grouped[n]
                head, eds, mode = split_eda(seg, labs)
                if mode == "unresolved":
                    unresolved.append({"year": year, "subject_no": blk["no"], "subject": rec["name"],
                                       "daimon": n, "why": "枝番を特定できない", "labels": labs})
                    continue
                typ = classify(head)
                pts = POINTS.search(head)
                for lab, t in eds:
                    items.append({
                        "id": f"{year}-{blk['no']:02d}-{n}-{lab}",
                        "year": year, "subject_no": blk["no"], "subject": rec["name"],
                        "daimon": n, "eda": lab, "type": typ, "mode": mode,
                        "points": int(pts.group(1).translate(Z2H)) if pts else None,
                        "instruction": POINTS.sub("", head).strip(),
                        "text": t,
                        "answer": rec["ans"][f"{n}-{lab}"],
                    })

    args.out.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    (args.out.parent / "unresolved.json").write_text(
        json.dumps(unresolved, ensure_ascii=False, indent=1), encoding="utf-8")

    total_ans = sum(len(v) for v in answers.values())
    print(f"模範解答 {total_ans} / 切り出せた枝問 {len(items)} ({len(items) / total_ans:.0%})")
    for k, v in collections.Counter(i["type"] for i in items).most_common():
        print(f"  {k:12s} {v:5d}")
    print(f"未解決 {len(unresolved)} 件 -> {args.out.parent / 'unresolved.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
