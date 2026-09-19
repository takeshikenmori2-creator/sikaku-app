#!/usr/bin/env python3
"""アプリ一式を1枚のHTMLにまとめ、Artifactとして公開できる形にする。

Artifact の公開時は <!doctype>/<html>/<head>/<body> が外側から付くので、
ここではページの中身だけを書き出す。CSS・JS・問題データはすべて埋め込むため、
配信されるのはこのファイル1つだけになる。

    python3 tools/build_artifact.py
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> int:
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "assets/style.css").read_text(encoding="utf-8")
    app = (ROOT / "assets/app.js").read_text(encoding="utf-8")
    data = (ROOT / "data/questions.js").read_text(encoding="utf-8")

    body = re.search(r"<body>(.*)</body>", html, re.S).group(1)
    body = re.sub(r'\s*<script src="[^"]+"></script>', "", body)

    out = (
        "<title>海事代理士 過去問ドリル</title>\n"
        "<style>\n" + css + "\n</style>\n"
        + body.strip() + "\n\n"
        "<script>\n" + data + "</script>\n"
        "<script>\n" + app + "</script>\n"
    )
    dest = ROOT / "artifact" / "kaiji-drill.html"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(out, encoding="utf-8")
    print(f"{dest} ({len(out.encode()) // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
