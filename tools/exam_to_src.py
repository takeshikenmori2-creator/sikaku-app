#!/usr/bin/env python3
"""過去問バンク（bank.json）と手書きの上書き（data/overlay/）を合成して
アプリ用の問題ソース data/src/kako/<科目id>.json を作る。

bank.json は機械変換の結果なので、設問文の言い回し・誤答の選択肢・解説は
data/overlay/<科目id>.json で項目idごとに上書きする。上書きは追記式で、
指定した項目だけが差し替わる。

    python3 tools/exam_to_src.py
"""
import argparse
import collections
import json
import pathlib
import random
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent

SUBJECT_ID = {
    "憲法": "kenpou", "民法": "minpou", "商法": "shouhou", "国土交通省設置法": "setchihou",
    "船員法": "senninhou", "船員職業安定法": "shokuan",
    "船舶職員及び小型船舶操縦者法": "shokuinhou", "海上運送法": "kaijou",
    "港湾運送事業法": "kouwan", "内航海運業法": "naikou", "港則法": "kousokuhou",
    "海上交通安全法": "kaikouan", "海洋汚染等及び海上災害の防止に関する法律": "kaiyouosen",
    "領海等における外国船舶の航行に関する法律": "ryoukai", "船舶法": "senpakuhou",
    "船舶安全法": "anzenhou", "船舶のトン数の測度に関する法律": "tonsuu",
    "造船法": "zousen",
    "国際航海船舶及び国際港湾施設の保安の確保等に関する法律": "hoanhou",
    "船舶の再資源化解体の適正な実施に関する法律": "saishigen",
}

MARU_CHOICES = ["○", "×"]

def clean_answer(a: str) -> str:
    """模範解答の但し書きを落とす。

    「四分の一（算用数字可）」「一年（１年）」「三分ノ二以上(３分ノ２以上、２／３以上等)」
    のように、末尾の括弧が別表記の言い換えであることが多い。括弧の中に数字が入るか、
    可・等・正解といった語が入る場合を但し書きとみなす。「六（６）級海技士（機関）」の
    ような本文の一部は残す。
    """
    a = a.strip()
    i = a.find("（")
    j = a.find("(")
    i = min(x for x in (i, j) if x >= 0) if (i >= 0 or j >= 0) else -1
    if i <= 0:
        return a
    note = a[i:]
    if re.search(r"[0-9０-９]", note) or any(k in note for k in ("可", "等", "正解", "など")):
        return a[:i].strip()
    return a


def wareki(year: int) -> str:
    return f"令和{year - 2018}年"


def item_id(b: dict) -> str:
    return f"{b['year']}-{b['subject_no']:02d}-{b['daimon']}-{b['eda']}"


def tidy(t: str) -> str:
    t = re.sub(r"^[、。，,．.・\s]+", "", t)
    t = re.sub(r"\s+", "", t)
    # ○×問題の解答欄の枠が本文末尾に【】として残ることがある。設問には不要
    t = re.sub(r"(?:【】)+$", "", t.strip())
    return t.strip()


KANSUU = "〇一二三四五六七八九十"
ITEM_MARK = re.compile(r"[（(]([0-9０-９一二三四五六七八九十]{1,3})[）)]")
BLANK_MARK = re.compile(r"【([^】]{1,3})】")
MAX_BLANKS = 5  # 1問あたりの空欄の上限。これを超える大問は条文の項番で分割する
MAX_CHARS = 420  # 1問あたりの本文の字数の目安


def to_int(s: str) -> int:
    t = s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    if t.isdigit():
        return int(t)
    if s == "十":
        return 10
    if len(s) == 1:
        return KANSUU.find(s)
    if len(s) == 2 and s[0] == "十":
        return 10 + KANSUU.find(s[1])
    if len(s) == 2 and s[1] == "十":
        return KANSUU.find(s[0]) * 10
    return -1


def item_segments(passage: str):
    """本文を条文の項番「（１）（２）…」で切る。

    本文中の（略）や挿入句と区別するため、1から順に増える番号だけを項番とみなす。
    項番が2つ未満なら分割できないので None を返す。
    """
    marks = []
    want = 1
    for m in ITEM_MARK.finditer(passage):
        if to_int(m.group(1)) == want:
            marks.append((m.start(), want))
            want += 1
    if len(marks) < 2:
        return None
    segs = []
    if marks[0][0] > 0:  # 項番の前の前置き。最初の塊に付ける
        segs.append((passage[: marks[0][0]], 0))
    for i, (pos, num) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(passage)
        segs.append((passage[pos:end], num))
    return segs


def split_passage(passage: str, cap: int = MAX_BLANKS, chars: int = MAX_CHARS):
    """空欄が多い／本文が長い大問を、条文の項番の切れ目で小分けにする。

    返り値は (本文, 項番のリスト) の並び。まず何分割するかを空欄の数と字数の
    両方から決め、各塊の空欄の数がなるべく揃うように項をまとめる。1つの項だけで
    上限を超える場合は、条文の途中で切ると意味が通らなくなるのでそのまま出す。
    """
    total = len(BLANK_MARK.findall(passage))
    if total <= cap and len(passage) <= chars:
        return [(passage, [])]
    segs = item_segments(passage)
    if not segs:
        return [(passage, [])]
    k = max(-(-total // cap), -(-len(passage) // chars), 1)
    k = min(k, len(segs))
    chunks: list[list] = []
    cur: list = []
    count = 0
    left = total
    for i, (text, num) in enumerate(segs):
        n = len(BLANK_MARK.findall(text))
        rest = len(chunks)  # すでに確定した塊の数
        target = max(1, -(-left // max(1, k - rest)))
        if cur and count + n > target and len(chunks) < k - 1:
            chunks.append(cur)
            left -= count
            cur, count = [], 0
        cur.append((text, num))
        count += n
    if cur:
        chunks.append(cur)
    return [("".join(t for t, _ in c), [n for _, n in c if n]) for c in chunks]


SUFFIX = "abcdefghijklmnopqrstuvwxyz"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", type=pathlib.Path, default=ROOT / "data/exam/bank.json")
    ap.add_argument("--overlay", type=pathlib.Path, default=ROOT / "data/overlay")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "data/src/kako")
    args = ap.parse_args()

    bank = json.loads(args.bank.read_text(encoding="utf-8"))
    overlay: dict[str, dict] = {}
    if args.overlay.exists():
        for f in sorted(args.overlay.glob("*.json")):
            overlay.update(json.loads(f.read_text(encoding="utf-8")))

    by_subject: dict[str, list] = collections.defaultdict(list)
    dropped = collections.Counter()

    # 同じ大問の空欄はひとまとめにして「1問ですべての空欄を答える」形にする
    groups: dict[str, list] = collections.defaultdict(list)
    singles = []
    for b in bank:
        # overlay で設問文を差し替えたものや、本文に空欄の目印が無いもの
        # （乗船履歴の計算問題など）は穴埋めではないので、まとめずに単独で出す
        if (b.get("group") and not overlay.get(item_id(b), {}).get("q")
                and f"【{b['eda']}】" in b.get("passage", "")):
            groups[b["group"]].append(b)
        else:
            singles.append(b)

    def shuffled(choices, answer, seed):
        order = list(range(len(choices)))
        random.Random(seed).shuffle(order)
        return [choices[i] for i in order], order.index(answer)

    def blank_choices(b, ov):
        """1つの空欄の選択肢と正解を決める。overlay の加筆があればそれを使う。"""
        if "choices" in ov:
            return list(ov["choices"]), ov["answer"]
        wrong = ov.get("wrong") or b.get("distractors")
        if not wrong:
            return None, None
        return [ov.get("ans") or clean_answer(b["answer_text"])] + list(wrong), 0

    for b in singles:
        sid = SUBJECT_ID.get(b["subject"])
        if not sid:
            dropped["科目名を解決できない"] += 1
            continue
        iid = item_id(b)
        ov = overlay.get(iid, {})
        ref = ov.get("ref") or f"{wareki(b['year'])} {b['subject']} 大問{b['daimon']}({b['eda']})"
        if b["kind"] == "maru_batsu":
            q = ov.get("q") or f"次の記述は正しいか、誤っているか。\n\n{tidy(b['text'])}"
            choices = ov.get("choices") or MARU_CHOICES
            answer = ov["answer"] if "answer" in ov else (0 if b["correct"] else 1)
        else:
            q = ov.get("q") or f"次の条文等の ＿＿＿＿ に入る語句として正しいものはどれか。\n\n{tidy(b['text'])}"
            choices, answer = blank_choices(b, ov)
            if not choices:
                dropped["選択肢が未作成"] += 1
                continue
        ch, ai = shuffled(choices, answer, iid)
        by_subject[sid].append({
            "id": iid, "q": q, "choices": ch, "answer": ai,
            "explain": ov.get("explain", ""), "ref": ref, "tag": wareki(b["year"]),
        })

    for gid, members in sorted(groups.items()):
        sid = SUBJECT_ID.get(members[0]["subject"])
        if not sid:
            dropped["科目名を解決できない"] += 1
            continue
        blanks = []
        for b in members:
            iid = item_id(b)
            ov = overlay.get(iid, {})
            choices, answer = blank_choices(b, ov)
            if not choices or len(set(choices)) != len(choices):
                dropped["選択肢が未作成" if not choices else "選択肢が重複"] += 1
                continue
            ch, ai = shuffled(choices, answer, iid)
            blanks.append({
                "id": iid, "label": str(b["eda"]), "choices": ch, "answer": ai,
                "explain": ov.get("explain", ""),
            })
        if not blanks:
            continue
        head = members[0]
        keep = {bl["label"] for bl in blanks}
        # 大問idをキーにした overlay の passage で、抽出が崩れた本文を差し替えられる
        passage = overlay.get(gid, {}).get("passage") or head["passage"]
        # 選択肢を作れなかった空欄は【】のままにせず、答えを直接入れて読めるようにする
        for b in members:
            if str(b["eda"]) not in keep:
                passage = passage.replace(f"【{b['eda']}】", clean_answer(b.get("answer_text", "")) or "…")
        # 空欄が多い大問はそのまま出すと1問が長すぎるので、条文の項番で小分けにする
        parts = split_passage(passage)
        base_ref = f"{wareki(head['year'])} {head['subject']} 大問{head['daimon']}"
        for k, (text, nums) in enumerate(parts):
            keep_here = set(BLANK_MARK.findall(text))
            mine = [bl for bl in blanks if bl["label"] in keep_here]
            if not mine:
                continue
            qid = gid if len(parts) == 1 else f"{gid}{SUFFIX[k]}"
            ref = base_ref
            if len(parts) > 1 and nums:
                ref += f"({nums[0]})" if len(nums) == 1 else f"({nums[0]})〜({nums[-1]})"
            by_subject[sid].append({
                "id": qid,
                "q": f"次の条文等の空欄【】に入る語句を、それぞれ選べ。\n\n{text}",
                "blanks": mine,
                "explain": "",
                "ref": ref,
                "tag": wareki(head["year"]),
            })

    args.out.mkdir(parents=True, exist_ok=True)
    for old in args.out.glob("*.json"):
        old.unlink()  # 前回の出力が残ると消えたはずの問題が生き続ける
    for sid, qs in sorted(by_subject.items()):
        qs.sort(key=lambda x: x["id"])
        (args.out / f"{sid}.json").write_text(
            json.dumps({"subject": sid, "source": "過去問", "questions": qs},
                       ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    total = sum(len(v) for v in by_subject.values())
    print(f"過去問から {total} 問を書き出した -> {args.out}")
    for sid, qs in sorted(by_subject.items(), key=lambda kv: -len(kv[1])):
        done = sum(1 for q in qs if q["explain"])
        print(f"  {sid:12s} {len(qs):4d}  (解説あり {done})")
    if dropped:
        print("除外:", dict(dropped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
