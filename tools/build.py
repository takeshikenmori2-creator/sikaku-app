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
            for key in REQUIRED:
                if key not in q:
                    errors.append(f"{where}: '{key}' がない")
            if errors and errors[-1].startswith(where):
                continue
            if errors and errors[-1].startswith(where):
                continue
            if not isinstance(q["choices"], list) or len(q["choices"]) < 2:
                errors.append(f"{where}: choices は2つ以上の配列である必要がある")
                continue
            if len(set(q["choices"])) != len(q["choices"]):
                errors.append(f"{where}: 選択肢が重複している")
            if not isinstance(q["answer"], int) or not 0 <= q["answer"] < len(q["choices"]):
                errors.append(f"{where}: answer が選択肢の範囲外")
                continue
            qid = q["id"] if str(q["id"]).count("-") >= 2 else f"{subject}-{q['id']}"
            if qid in seen_ids:
                errors.append(f"{where}: id '{qid}' が重複")
                continue
            seen_ids.add(qid)
            questions.append({
                "id": qid,
                "subject": subject,
                "q": q["q"],
                "choices": q["choices"],
                "answer": q["answer"],
                "explain": q["explain"],
                "ref": q.get("ref", ""),
                "tag": q.get("tag", doc.get("source", "")),
            })

    if errors:
        for e in errors:
            print("ERROR:", e, file=sys.stderr)
        return 1

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
    print(f"{len(questions)} 問 / {len(by_subject)} 科目")
    for s in meta["subjects"]:
        print(f"  {by_subject.get(s['id'], 0):>4}  {s['name']}")
    missing = [s["name"] for s in meta["subjects"] if s["id"] not in by_subject]
    if missing:
        print("問題が無い科目:", ", ".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
