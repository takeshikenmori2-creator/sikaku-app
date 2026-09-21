#!/usr/bin/env python3
"""data/src/*.json をまとめて data/questions.js / data/questions.json を生成する。

    python3 tools/build.py

検証も兼ねる。スキーマ違反があれば非ゼロ終了。
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "src"
SUBJECTS_FILE = ROOT / "data" / "subjects.json"

REQUIRED = ("id", "q", "choices", "answer", "explain")


def main() -> int:
    meta = json.loads(SUBJECTS_FILE.read_text(encoding="utf-8"))
    imp_file = ROOT / "data" / "importance.json"
    imp = json.loads(imp_file.read_text(encoding="utf-8")) if imp_file.exists() else {}
    stars, years = imp.get("stars", {}), imp.get("years", {})
    valid_subjects = {s["id"] for s in meta["subjects"]}

    questions: list[dict] = []
    seen_ids: set[str] = set()
    errors: list[str] = []

    for path in sorted(SRC.rglob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        subject = doc.get("subject")
        rel = path.relative_to(SRC)
        if subject not in valid_subjects:
            errors.append(f"{path.name}: 未知の subject '{subject}'")
            continue
        for i, q in enumerate(doc.get("questions", [])):
            where = f"{rel}[{i}]"
            if "id" not in q or "q" not in q:
                errors.append(f"{where}: 'id' か 'q' がない")
                continue
            qid = q["id"] if str(q["id"]).count("-") >= 2 else f"{subject}-{q['id']}"
            if qid in seen_ids:
                errors.append(f"{where}: id '{qid}' が重複")
                continue

            def check(opt, label):
                """選択肢と正解の組を検証する。問題があればその旨を返す。"""
                if not isinstance(opt.get("choices"), list) or len(opt["choices"]) < 2:
                    return f"{label}: choices は2つ以上の配列である必要がある"
                if len(set(opt["choices"])) != len(opt["choices"]):
                    return f"{label}: 選択肢が重複している"
                a = opt.get("answer")
                if not isinstance(a, int) or not 0 <= a < len(opt["choices"]):
                    return f"{label}: answer が選択肢の範囲外"
                return None

            if "blanks" in q:
                # 大問まるごと。空欄ごとに選択肢と正解を持つ
                if not q["blanks"]:
                    errors.append(f"{where}: blanks が空")
                    continue
                bad = [m for m in (check(bl, f"{where} 空欄{bl.get('label')}")
                                   for bl in q["blanks"]) if m]
                if bad:
                    errors.extend(bad)
                    continue
                if any(f"【{bl['label']}】" not in q["q"] for bl in q["blanks"]):
                    errors.append(f"{where}: 本文に現れない空欄がある")
                    continue
                item = {
                    "id": qid, "subject": subject, "q": q["q"],
                    "blanks": [{"label": str(bl["label"]), "choices": bl["choices"],
                                "answer": bl["answer"], "explain": bl.get("explain", "")}
                               for bl in q["blanks"]],
                }
            else:
                msg = check(q, where)
                if msg:
                    errors.append(msg)
                    continue
                item = {
                    "id": qid, "subject": subject, "q": q["q"],
                    "choices": q["choices"], "answer": q["answer"],
                }

            seen_ids.add(qid)
            item["explain"] = q.get("explain", "")
            item["ref"] = q.get("ref", "")
            item["tag"] = q.get("tag", doc.get("source", ""))
            item["stars"] = stars.get(qid, 1)
            item["years"] = years.get(qid, [])
            questions.append(item)

    if errors:
        for e in errors:
            print("ERROR:", e, file=sys.stderr)
        return 1

    # 同じ設問が複数年にまたがって出題されていることがある。中身が完全に同じものは
    # 1件にまとめ、出典に出題年を併記する（★の頻度判定は別途まとめる前の情報で行う）
    merged: dict[tuple, dict] = {}
    order: list[dict] = []
    for q in questions:
        # 選択肢の並びはid由来のシャッフルで年度ごとに変わるので、並び順は鍵に入れず
        # 「正解の語」と「選択肢の顔ぶれ」で同一性を判定する
        def shape(choices, answer):
            return (choices[answer], frozenset(choices))
        key = (q["subject"], q["q"],
               shape(q["choices"], q["answer"]) if "choices" in q else None,
               tuple((b["label"],) + shape(b["choices"], b["answer"])
                     for b in q.get("blanks", ())))
        first = merged.get(key)
        if first is None:
            merged[key] = q
            order.append(q)
        else:
            first.setdefault("also", []).append(q["ref"])
            first.setdefault("tags", [first["tag"]]).append(q["tag"])
    dropped_dupes = len(questions) - len(order)
    for q in order:
        if q.get("also"):
            refs = [q["ref"]] + q["also"]
            years = sorted({r.split()[0] for r in refs})
            q["ref"] = f"{'・'.join(years)} {' '.join(refs[0].split()[1:])} ほか"
            q["tags"] = years  # 重要度の頻度判定でまとめる前の年度を使えるように残す
            del q["also"]
    questions = order

    bundle = {
        "subjects": meta["subjects"],
        "blocks": meta["blocks"],
        "questions": questions,
    }
    payload = json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))

    (ROOT / "data" / "questions.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (ROOT / "data" / "questions.js").write_text(
        "/* 自動生成ファイル — 編集しないこと。data/src/*.json を直して tools/build.py を実行する。 */\n"
        "window.KDQ = " + payload + ";\n",
        encoding="utf-8",
    )

    by_subject: dict[str, int] = {}
    for q in questions:
        by_subject[q["subject"]] = by_subject.get(q["subject"], 0) + 1
    if dropped_dupes:
        print(f"完全に同じ内容の設問 {dropped_dupes} 件を1件にまとめた")
    blanks = sum(len(q["blanks"]) for q in questions if "blanks" in q)
    print(f"{len(questions)} 問 / {len(by_subject)} 科目"
          f"（うち空欄まとめ問題 {sum(1 for q in questions if 'blanks' in q)} 問・空欄 {blanks} 個）")
    for s in meta["subjects"]:
        print(f"  {by_subject.get(s['id'], 0):>4}  {s['name']}")
    missing = [s["name"] for s in meta["subjects"] if s["id"] not in by_subject]
    if missing:
        print("問題が無い科目:", ", ".join(missing))
    if not stars:
        print("重要度が未算出。tools/rank_importance.py を実行してから再度ビルドすること。")
    else:
        dist: dict[int, int] = {}
        for q in questions:
            dist[q["stars"]] = dist.get(q["stars"], 0) + 1
        print("重要度 " + " / ".join(f"★{n}:{dist.get(n, 0)}" for n in (3, 2, 1)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
