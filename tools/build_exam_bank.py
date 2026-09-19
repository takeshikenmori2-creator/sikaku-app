#!/usr/bin/env python3
"""抽出済みの設問テキストと模範解答から、アプリ用の選択式問題を組み立てる。

大問の型ごとに扱いを変える。

  combo      ①②の正誤の組合せを選ぶ問題 → ①と②をそれぞれ独立した○×問題に分解する
  maru_batsu もともと○×の問題          → そのまま2択にする
  fill_bank  語群から語句を選ぶ穴埋め     → 正解＋語群からの誤答3つで4択にする
  choice     選択肢から選ぶ問題          → 選択肢をそのまま使う
  fill       自由記入の穴埋め            → 誤答を機械で作れないので needs_choices として書き出す

    python3 tools/build_exam_bank.py --exam data/exam --out data/exam/bank.json
"""
import argparse
import collections
import json
import pathlib
import random
import re

Z2H = str.maketrans("０１２３４５６７８９", "0123456789")
H2Z = str.maketrans("0123456789", "０１２３４５６７８９")
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
CIRCLED2 = "㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚㉛㉜㉝㉞㉟"
SUBJ = re.compile(r"^(?:令和[0-9０-９一二三四五六七八九十元]+年)?\s*([0-9０-９]{1,2})\s*[．.]\s*(\S.*?)\s*$")
POINTS = re.compile(r"[（(]\s*[0-9０-９]{1,2}\s*点\s*[）)]")
BANK = re.compile(r"【?語\s*群】?")
COMBO_OPT = re.compile(r"([ア-ン0-9０-９])\s*①\s*(正|誤)\s*[、,]?\s*②\s*(正|誤)")


def norm(s: str) -> str:
    return re.sub(r"[ 　]+", "", s)


def circled_index(ch: str) -> int | None:
    if ch in CIRCLED:
        return CIRCLED.index(ch) + 1
    if ch in CIRCLED2:
        return CIRCLED2.index(ch) + 21
    return None


def label_forms(lab: str) -> list[str]:
    if lab.isdigit():
        z = lab.translate(H2Z)
        out = [f"({z})", f"（{z}）", f"({lab})", f"（{lab}）"]
        n = int(lab)
        if 1 <= n <= 20:
            out.append(CIRCLED[n - 1])
        elif 21 <= n <= 35:
            out.append(CIRCLED2[n - 21])
        return out
    return [f"({lab})", f"（{lab}）", f"{lab}【】", f"{lab}．", f"{lab}.", lab]


def form_kind(form: str) -> str:
    if form[0] in "(（":
        return "paren"
    if form in CIRCLED or form in CIRCLED2:
        return "circled"
    if form.endswith("【】"):
        return "blank"
    if form.endswith(("．", ".")):
        return "dotted"
    return "bare"


def find_label(seg: str, lab: str, pos: int, kinds: tuple[str, ...]):
    best, blen = -1, 0
    for form in label_forms(lab):
        if form_kind(form) not in kinds:
            continue
        i = pos - 1
        while True:
            i = seg.find(form, i + 1)
            if i < 0:
                break
            if seg[i + len(form): i + len(form) + 1] in ("～", "〜", "~", "-", "－", "ー"):
                continue  # 「(ア)～(オ)」のような指示文中の参照
            break
        if i >= 0 and (best < 0 or i < best):
            best, blen = i, len(form)
    return best, blen


def slice_by_labels(seg: str, labels: list[str]):
    # 括弧つき → 空欄に付いたラベル → 丸数字 → 裸 の順に試す。
    # 丸数字を先に試すと「①及び②の文章の正誤について」のような指示文を枝番と誤認する。
    for kinds in (("paren",), ("paren", "blank"), ("blank",), ("dotted",),
                  ("blank", "dotted"), ("blank", "bare"), ("paren", "circled"),
                  ("circled",), ("bare",),
                  ("paren", "blank", "dotted", "circled", "bare")):
        pos, hits = 0, []
        for lab in labels:
            i, l = find_label(seg, lab, pos, kinds)
            if i < 0:
                hits = None
                break
            hits.append((lab, i, i + l))
            pos = i + l
        if hits:
            out = []
            for k, (lab, s, e) in enumerate(hits):
                end = hits[k + 1][1] if k + 1 < len(hits) else len(seg)
                out.append((lab, s, seg[e:end].strip()))
            return seg[: hits[0][1]].strip(), out
    return seg, []


TERM_TRIM = "．.、,　 ：:"


def parse_bank(seg: str) -> dict[str, str]:
    """末尾の【語群】を {番号: 語句} に開く。①語句 形式と 1．語句 形式の両方がある。"""
    # 指示文にも「下欄の語群」のように出てくるので、最後に現れたものを語群の始まりとみなす
    ms = list(BANK.finditer(seg))
    if not ms:
        return {}
    tail = seg[ms[-1].end():]

    out, cur, buf = {}, None, []
    for ch in tail:
        n = circled_index(ch)
        if n is not None:
            if cur is not None:
                out[str(cur)] = "".join(buf).strip(TERM_TRIM)
            cur, buf = n, []
        elif cur is not None:
            buf.append(ch)
    if cur is not None:
        out[str(cur)] = "".join(buf).strip(TERM_TRIM)
    out = {k: v for k, v in out.items() if v}
    if len(out) >= 4:
        return out

    # 「１．職員 ２．部員」のように番号＋区切りで並ぶ形式
    hits = list(re.finditer(r"([0-9０-９]{1,2})\s*[．.]\s*", tail))
    out = {}
    for k, h in enumerate(hits):
        end = hits[k + 1].start() if k + 1 < len(hits) else len(tail)
        term = tail[h.end():end].strip(TERM_TRIM)
        if term:
            out[h.group(1).translate(Z2H)] = term
    return out


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


def subject_blocks(doc: dict, names: dict[int, str]):
    blocks = []
    for pg in doc["pages"]:
        lines = [l for l in pg["lines"] if l.strip()]
        if not lines:
            continue
        joined = norm("".join(lines[:4]))
        if "時限目" in joined and "海事代理士試験" in joined:
            continue
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


NUMBERED = re.compile(r"[0-9０-９]{1,2}\s*[．.]")


def split_daimon(body: str, numbers: list[int]):
    """既知の大問番号を順に探して本文を割る。

    語群が「１．変更２．廃止…」と番号付きで並ぶため、素朴に「２．」を探すと
    語群の項目を大問の始まりと取り違える。直後に十分な長さの本文が続く箇所だけを
    大問の見出しとみなす。
    """
    spans, pos = [], 0
    for n in numbers:
        found, flen = -1, 0
        for form in (f"{str(n).translate(H2Z)}．", f"{n}.", f"{str(n).translate(H2Z)}.", f"{n}．"):
            i = pos - 1
            while True:
                i = body.find(form, i + 1)
                if i < 0:
                    break
                after = body[i + len(form): i + len(form) + 14]
                if not NUMBERED.search(after):
                    break  # 語群の項目ではなさそう
            if i >= 0 and (found < 0 or i < found):
                found, flen = i, len(form)
        if found < 0:
            return None
        spans.append((n, found, found + flen))
        pos = found + flen
    return [(n, body[e: spans[k + 1][1] if k + 1 < len(spans) else len(body)])
            for k, (n, s, e) in enumerate(spans)]


TARGET_BLANK = "＿＿＿＿"
MARU = {"○": True, "〇": True, "×": False, "✕": False}
# 「ア-○イ-×」のように、1つの枝番に2文の正誤がまとめて書かれている解答欄
PAIR = re.compile(r"([ア-ン])\s*[-ー－]?\s*([○〇×✕])")


def build_pair(base, parts, ans, n, skipped):
    """1枝に2文（ア・イ）が入っている正誤問題を、文ごとの○×問題に分ける。"""
    items = []
    for lab, _pos, text in parts:
        a = (ans.get(f"{n}-{lab}") or "").strip()
        marks = PAIR.findall(a)
        if len(marks) < 2:
            continue
        body = clean_body(text)
        chunks = {}
        for m in re.finditer(r"([ア-ン])\s*[．.]\s*", body):
            nxt = re.search(r"[ア-ン]\s*[．.]\s*", body[m.end():])
            end = m.end() + nxt.start() if nxt else len(body)
            chunks[m.group(1)] = body[m.end():end].strip()
        if not all(k in chunks and len(chunks[k]) > 10 for k, _ in marks):
            skipped.append({**base, "eda": lab, "why": "ア・イの本文に分けられない"})
            continue
        for k, mark in marks:
            items.append({**base, "eda": f"{lab}{k}", "kind": "maru_batsu",
                          "type": "maru_batsu", "text": chunks[k], "correct": MARU[mark]})
    return items


def has_pairs(parts, ans, n) -> bool:
    got = [len(PAIR.findall(ans.get(f"{n}-{l}", ""))) >= 2 for l, _p, _t in parts]
    return bool(got) and all(got)
CHECKED = re.compile(r"([○〇×✕ア-ンA-ZＡ-Ｚ0-9０-９]{1,2})\s*[-ー－]?\s*[■●☑✓]")


def decode_checkbox(a: str) -> str | None:
    """□■ で選択を表す解答欄から、塗られた選択肢のラベルを取り出す。"""
    if "■" not in a and "●" not in a:
        return None
    m = CHECKED.search(a)
    return m.group(1) if m else None


def build(exam: pathlib.Path):
    answers = json.loads((exam / "answers.json").read_text(encoding="utf-8"))
    ans_by = {}
    for k, v in answers.items():
        y, no, name = k.split("/", 2)
        ans_by[(int(y), int(no))] = {"name": name, "ans": v}

    out, skipped = [], []
    rnd = random.Random(20260919)

    for f in sorted(exam.glob("*_hikki.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        year = doc["year"]
        names = {no: rec["name"] for (y, no), rec in ans_by.items() if y == year}
        for blk in subject_blocks(doc, names):
            rec = ans_by[(year, blk["no"])]
            grouped = collections.defaultdict(list)
            for key in rec["ans"]:
                d, lab = key.split("-", 1)
                grouped[int(d)].append(lab)
            body = norm("".join(blk["lines"]))
            dms = split_daimon(body, sorted(grouped))
            if dms is None:
                skipped.append({"year": year, "no": blk["no"], "subject": rec["name"], "why": "大問を特定できない"})
                continue
            for n, seg in dms:
                labs = grouped[n]
                head, parts = slice_by_labels(seg, labs)
                typ = classify(head)
                head = POINTS.sub("", head).strip()
                if not parts:
                    skipped.append({"year": year, "no": blk["no"], "subject": rec["name"],
                                    "daimon": n, "type": typ, "why": "枝番を特定できない", "labels": labs})
                    continue
                base = {"year": year, "subject_no": blk["no"], "subject": rec["name"],
                        "daimon": n, "instruction": head, "type": typ}
                if has_pairs(parts, rec["ans"], n):
                    out += build_pair(base, parts, rec["ans"], n, skipped)
                elif typ == "combo":
                    out += build_combo(base, seg, parts, rec["ans"], n, skipped)
                elif typ == "maru_batsu":
                    out += build_maru(base, parts, rec["ans"], n, skipped)
                elif typ == "fill_bank":
                    sample = [decode_checkbox(rec["ans"].get(f"{n}-{l}", "")) or
                              rec["ans"].get(f"{n}-{l}", "") for l in labs]
                    if all(s0[:1] in MARU for s0 in sample if s0):
                        out += build_maru({**base, "type": "maru_batsu"}, parts, rec["ans"], n, skipped)
                    else:
                        out += build_bank(base, seg, parts, rec["ans"], n, rnd, skipped)
                else:
                    pair = [x for x in parts if len(PAIR.findall(rec["ans"].get(f"{n}-{x[0]}", ""))) >= 2]
                    if pair:
                        out += build_pair(base, pair, rec["ans"], n, skipped)
                        parts = [x for x in parts if x not in pair]
                    maru = [(l, p0, t0) for (l, p0, t0) in parts
                            if (decode_checkbox(rec["ans"].get(f"{n}-{l}", "")) or
                                rec["ans"].get(f"{n}-{l}", ""))[:1] in MARU]
                    rest = [x for x in parts if x not in maru]
                    if maru:
                        out += build_maru({**base, "type": "maru_batsu"}, maru, rec["ans"], n, skipped)
                    if rest:
                        out += build_raw(base, rest, rec["ans"], n, seg, skipped)
    return out, skipped


def clean_body(t: str) -> str:
    t = COMBO_OPT.sub("", t)
    t = re.sub(r"【?語\s*群】?.*$", "", t)
    t = re.sub(r"[0-9０-９]{1,2}\s*[．.]\s*(?:次の|以下の|法令の規定を|下欄の).*$", "", t)
    t = re.sub(r"[0-9０-９]{1,2}[．.]\s*(?:次の|以下の|法令|この法律)?.*$", "", t) if t.rstrip().endswith(("．", ".")) else t
    t = re.sub(r"[0-9０-９]{1,2}[．.]$", "", t.rstrip())
    t = re.sub(r"^[（(][0-9０-９]{1,2}[）)]", "", t.strip())
    return t.strip("　 、,")


def build_combo(base, seg, parts, ans, n, skipped):
    """①②の正誤の組合せ問題を、①と②それぞれの○×問題にばらす。"""
    mapping = {m.group(1).translate(Z2H): (m.group(2) == "正", m.group(3) == "正")
               for m in COMBO_OPT.finditer(seg)}
    items = []
    for lab, _pos, text in parts:
        a = ans.get(f"{n}-{lab}")
        key = (a or "").translate(Z2H)[:1]
        if key not in mapping:
            skipped.append({**base, "eda": lab, "why": f"組合せの対応表を読めない(答 {a!r})"})
            continue
        truth = mapping[key]
        # 「ア①正、②誤」といった選択肢の並びを先に落としてから①②に割る
        cleaned = clean_body(text)
        got = {}
        for h in re.split(r"(?=[①②])", cleaned):
            if h and h[0] in "①②":
                got[h[0]] = h[1:].strip("　 、,")
        if len(got) != 2 or not all(got.values()):
            skipped.append({**base, "eda": lab, "why": "①②に分けられない"})
            continue
        for i, mark in enumerate("①②"):
            items.append({**base, "eda": f"{lab}{mark}", "kind": "maru_batsu",
                          "text": got[mark], "correct": truth[i]})
    return items


def build_maru(base, parts, ans, n, skipped):
    items = []
    for lab, _pos, text in parts:
        a = (ans.get(f"{n}-{lab}") or "").strip()
        a = decode_checkbox(a) or a
        if a[:1] not in MARU:
            skipped.append({**base, "eda": lab, "why": f"○×として読めない(答 {a!r})"})
            continue
        body = clean_body(text)
        if len(body) < 10:
            skipped.append({**base, "eda": lab, "why": "本文が短すぎる"})
            continue
        items.append({**base, "eda": lab, "kind": "maru_batsu",
                      "text": body, "correct": MARU[a[:1]]})
    return items


def sentence_ends(seg: str) -> list[int]:
    """文末の「。」の位置。ただし括弧の内側のものは文末とみなさない。"""
    depth, out = 0, []
    for i, ch in enumerate(seg):
        if ch in "（(「『【":
            depth += 1
        elif ch in "）)」』】":
            depth = max(0, depth - 1)
        elif ch == "。" and depth == 0:
            out.append(i)
    return out


def sentence_around(seg: str, pos: int) -> str:
    """指定位置を含む一文を返す。項番があればそこから始める。"""
    ends = sentence_ends(seg)
    start = 0
    for e in ends:
        if e < pos:
            start = e + 1
        else:
            break
    m = list(re.finditer(r"[（(][0-9０-９]{1,2}[）)]", seg[:pos]))
    if m and m[-1].end() > start:
        start = m[-1].end()
    end = next((e + 1 for e in ends if e >= pos), len(seg))
    return seg[start:end].strip()


def build_bank(base, seg, parts, ans, n, rnd, skipped):
    bank = parse_bank(seg)
    items = []
    for lab, pos, _text in parts:
        a = (ans.get(f"{n}-{lab}") or "").strip()
        a = decode_checkbox(a) or a
        num = re.sub(r"[^0-9]", "", a.translate(Z2H))
        ci = circled_index(a[:1])
        key = str(ci) if ci else (num or None)
        correct = bank.get(key) if key else None
        if not correct:
            m = re.search(r"[（(]([^（()）]+)[）)]\s*$", a)
            correct = m.group(1) if m else None
        if not correct:
            skipped.append({**base, "eda": lab, "why": f"語群から正解を引けない(答 {a!r})"})
            continue
        lim = max(len(correct) * 3 + 8, 16)
        wrong = [v for v in bank.values() if v != correct and len(v) <= lim]
        if len(wrong) < 3:
            wrong = [v for v in bank.values() if v != correct]
        if len(wrong) < 3:
            skipped.append({**base, "eda": lab, "why": "語群の候補が足りない"})
            continue
        sent = clean_body(sentence_around(seg, pos))
        sent = sent.replace(f"{lab}【】", TARGET_BLANK)
        sent = re.sub(r"[ア-ンA-ZＡ-Ｚ](?=【】)", "", sent)
        items.append({**base, "eda": lab, "kind": "choice", "text": sent,
                      "answer_text": correct, "distractors": rnd.sample(wrong, 3)})
    return items


def mark_blank(seg: str, lab: str, pos: int) -> str | None:
    """空欄を含む一文を取り出し、対象の空欄だけを目立つ形にする。

    設問によっては空欄に枝番の記号が印刷されておらず、どの空欄が問われているのか
    本文からは決められないものがある（箇条書きの各行が別々の枝番になっている場合など）。
    その場合は None を返して機械変換の対象から外す。
    """
    raw = sentence_around(seg, pos)
    if f"{lab}【】" in raw:
        raw = raw.replace(f"{lab}【】", TARGET_BLANK)
    elif raw.count("【】") == 1:
        raw = raw.replace("【】", TARGET_BLANK)
    else:
        return None
    sent = clean_body(raw)
    if TARGET_BLANK not in sent:
        return None  # 目印が本文整形で落ちた＝対象の空欄が文の外にある
    sent = re.sub(r"[ア-ンA-ZＡ-Ｚ](?=【】)", "", sent)
    return sent


def build_raw(base, parts, ans, n, seg=None, skipped=None):
    items = []
    for lab, pos, text in parts:
        if seg is not None and "【】" in seg:
            body = mark_blank(seg, lab, pos)
            if body is None:
                if skipped is not None:
                    skipped.append({**base, "eda": lab, "why": "どの空欄が問われているか特定できない"})
                continue
        else:
            body = clean_body(text)
        items.append({**base, "eda": lab, "kind": "needs_choices",
                      "text": body, "answer_text": (ans.get(f"{n}-{lab}") or "").strip()})
    return items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exam", type=pathlib.Path, required=True)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    args = ap.parse_args()
    items, skipped = build(args.exam)
    args.out.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    (args.out.parent / "skipped.json").write_text(json.dumps(skipped, ensure_ascii=False, indent=1), encoding="utf-8")
    c = collections.Counter(i["kind"] for i in items)
    print(f"組み立てた問題 {len(items)}")
    for k, v in c.most_common():
        print(f"  {k:14s} {v:5d}")
    print(f"積み残し {len(skipped)} -> {args.out.parent / 'skipped.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
