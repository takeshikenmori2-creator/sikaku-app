#!/usr/bin/env python3
"""downloads/ のPDFからテキストを抜き、data/src/ に入れる問題JSONの下書きを作る。

    python3 tools/pdf_to_draft.py downloads/2023_hikki_001579736.pdf --subject senpakuhou

pypdf が入っていればそれを、無ければ pdftotext（poppler-utils）を使う。
出力は data/draft/<名前>.json で、q / choices / answer / explain が空の雛形。
中身を埋めて data/src/ に移し、tools/build.py を実行する。

公式の過去問は記入式・記述式の設問を含むので、選択肢は自分で4択に組み直すこと。
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def extract(pdf: pathlib.Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(pdf)).pages)
    except ImportError:
        pass
    try:
        return subprocess.run(
            ["pdftotext", "-layout", str(pdf), "-"],
            capture_output=True, text=True, check=True,
        ).stdout
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        sys.exit(f"テキストを抽出できない。`pip install pypdf` か poppler-utils を入れること: {e}")


def split_questions(text: str) -> list[str]:
    """「問1」「第1問」「〔1〕」などで区切る。取りこぼしは手で直す前提。"""
    parts = re.split(r"\n(?=\s*(?:問\s*[0-9０-９]+|第\s*[0-9０-９]+\s*問|〔\s*[0-9０-９]+\s*〕))", text)
    return [p.strip() for p in parts if len(p.strip()) > 20]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=pathlib.Path)
    ap.add_argument("--subject", required=True, help="data/subjects.json の科目id")
    ap.add_argument("--prefix", default="x", help="問題idの接頭辞（既存idとぶつけないため）")
    args = ap.parse_args()

    subjects = json.loads((ROOT / "data" / "subjects.json").read_text(encoding="utf-8"))
    if args.subject not in {s["id"] for s in subjects["subjects"]}:
        sys.exit(f"未知の科目id: {args.subject}")

    raw = extract(args.pdf)
    chunks = split_questions(raw)

    doc = {
        "subject": args.subject,
        "_source": args.pdf.name,
        "questions": [
            {
                "id": f"{args.prefix}{n:03d}",
                "_raw": c[:1200],
                "q": "",
                "choices": ["", "", "", ""],
                "answer": 0,
                "explain": "",
                "ref": "",
            }
            for n, c in enumerate(chunks, 1)
        ],
    }
    out = ROOT / "data" / "draft" / f"{args.pdf.stem}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(chunks)} 個の設問らしき塊を書き出した → {out}")
    print("_raw を見ながら q / choices / answer / explain を埋め、data/src/ に移すこと。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
