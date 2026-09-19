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

MARU_CHOICES = ["正しい", "誤っている"]

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
    return t.strip()


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

    for b in bank:
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
        elif b["kind"] == "choice":
            q = ov.get("q") or f"次の条文等の《　》に入る語句として正しいものはどれか。\n\n{tidy(b['text'])}"
            if "choices" in ov:
                choices, answer = ov["choices"], ov["answer"]
            elif "wrong" in ov:
                choices, answer = [ov.get("ans") or clean_answer(b["answer_text"])] + list(ov["wrong"]), 0
            else:
                choices = [clean_answer(b["answer_text"])] + list(b["distractors"])
                answer = 0
        elif b["kind"] == "needs_choices":
            if "choices" not in ov and "wrong" not in ov:
                dropped["選択肢が未作成"] += 1
                continue
            q = ov.get("q") or f"次の条文等の【】に入る語句として正しいものはどれか。\n\n{tidy(b['text'])}"
            if "choices" in ov:
                choices, answer = ov["choices"], ov["answer"]
            else:
                choices, answer = [ov.get("ans") or clean_answer(b["answer_text"])] + list(ov["wrong"]), 0
        else:
            dropped[f"未対応の型 {b['kind']}"] += 1
            continue

        if len(set(choices)) != len(choices):
            dropped["選択肢が重複"] += 1
            continue

        order = list(range(len(choices)))
        r = random.Random(iid)
        r.shuffle(order)
        by_subject[sid].append({
            "id": iid,
            "q": q,
            "choices": [choices[i] for i in order],
            "answer": order.index(answer),
            "explain": ov.get("explain", ""),
            "ref": ref,
            "tag": wareki(b["year"]),
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
