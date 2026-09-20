#!/usr/bin/env python3
"""過去5年の出題頻度から問題ごとの重要度（★1〜3）を算出する。

同じ論点が何年分に出ているかで測る。設問の言い回しは年によって変わるので、
科目ごとに本文の文字3-gramの重なり（Jaccard係数）で問題をまとめ、
そのまとまりに含まれる年度の数を数える。

  3年以上 → ★3 ／ 2年 → ★2 ／ 1年のみ → ★1

条文ベースの自作問題は年度を持たないが、過去問と同じまとまりに入れば
その論点の★を引き継ぐ。

    python3 tools/rank_importance.py        # data/importance.json を生成
"""
import argparse
import collections
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DROP = re.compile(r"[\s、。，．・「」『』（）()【】〔〕＿①-⑳ア-ンぁ-んー]")
YEAR = re.compile(r"令和([0-9０-９]+)年")
Z2H = str.maketrans("０１２３４５６７８９", "0123456789")


def sentence_around(text: str, pos: int) -> str:
    """指定位置を含む一文を返す。項番があればそこから始める。"""
    start = text.rfind("。", 0, pos) + 1
    m = list(re.finditer(r"[（(][0-9０-９]{1,2}[）)]", text[:pos]))
    if m and m[-1].end() > start:
        start = m[-1].end()
    end = text.find("。", pos)
    return text[start: len(text) if end < 0 else end + 1]


def units_of(q: dict) -> list[str]:
    """問題を論点の単位に分ける。

    まとめ問題は大問まるごとで比べると年ごとの差に埋もれてしまうので、
    空欄1つを1論点として、その空欄を含む一文と正解の語句で比べる。
    """
    text = q["q"].split("\n\n", 1)[-1]
    if "blanks" not in q:
        return [text + q["choices"][q["answer"]]]
    out = []
    for bl in q["blanks"]:
        mark = f"【{bl['label']}】"
        i = text.find(mark)
        sent = sentence_around(text, i) if i >= 0 else text[:120]
        out.append(sent + bl["choices"][bl["answer"]])
    return out


def body_of(q: dict) -> str:
    return units_of(q)[0]


def grams(text: str, n: int = 3) -> set[str]:
    t = DROP.sub("", text)
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cluster(items: list[tuple[str, set]], threshold: float) -> list[list[str]]:
    """単純な単連結クラスタリング。1科目あたり高々100問程度なので総当たりで足りる。"""
    parent = {i: i for i in range(len(items))}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if jaccard(items[i][1], items[j][1]) >= threshold:
                parent[find(i)] = find(j)

    groups = collections.defaultdict(list)
    for i, (qid, _g) in enumerate(items):
        groups[find(i)].append(qid)
    return list(groups.values())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", type=pathlib.Path, default=ROOT / "data/questions.json")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "data/importance.json")
    ap.add_argument("--threshold", type=float, default=0.33)
    args = ap.parse_args()

    data = json.loads(args.questions.read_text(encoding="utf-8"))
    qs = data["questions"]
    by_id = {q["id"]: q for q in qs}

    # (問題id, 何番目の論点か) を単位にクラスタリングする
    by_subject = collections.defaultdict(list)
    for q in qs:
        for k, unit in enumerate(units_of(q)):
            by_subject[q["subject"]].append(((q["id"], k), grams(unit)))

    stars: dict[str, int] = {}
    spread: dict[str, list[str]] = {}
    for _sid, items in by_subject.items():
        for group in cluster(items, args.threshold):
            years = set()
            for qid, _k in group:
                q = by_id[qid]
                # 複数年で全く同じ設問はまとめてあるので、まとめる前の年度を見る
                for tag in q.get("tags") or [q.get("tag", "")]:
                    m = YEAR.search(tag)
                    if m:
                        years.add(int(m.group(1).translate(Z2H)))
            n = 3 if len(years) >= 3 else 2 if len(years) == 2 else 1
            for qid, _k in group:
                # 1つでも頻出の論点を含む問題は、その重要度で扱う
                if n > stars.get(qid, 0):
                    stars[qid] = n
                    spread[qid] = [f"令和{y}年" for y in sorted(years)]

    args.out.write_text(json.dumps(
        {"stars": stars, "years": spread}, ensure_ascii=False, indent=1), encoding="utf-8")

    dist = collections.Counter(stars.values())
    print(f"{len(stars)} 問に重要度を付けた -> {args.out}")
    for n in (3, 2, 1):
        print(f"  ★{n}: {dist.get(n, 0)} 問")
    print("\n★3の例:")
    shown = 0
    for qid, ys in spread.items():
        if len(ys) >= 3 and shown < 5:
            print(f"  {by_id[qid]['subject']:12s} {'/'.join(ys)}  {body_of(by_id[qid])[:40]}")
            shown += 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
