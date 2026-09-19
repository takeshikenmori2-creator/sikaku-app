#!/usr/bin/env python3
"""国土交通省の公開ページから海事代理士試験の過去問・模範解答PDFを収集する。

    python3 tools/fetch_official_pdfs.py            # 全年度
    python3 tools/fetch_official_pdfs.py --years 5  # 新しい5年分だけ
    python3 tools/fetch_official_pdfs.py --list     # ダウンロードせず一覧だけ表示

配布元: https://www.mlit.go.jp/about/file000049.html （海事代理士になるには）
標準ライブラリのみで動く。downloads/ に保存する。

注意: このスクリプトを作成したセッションの実行環境では mlit.go.jp への通信が
ネットワークポリシーで遮断されていたため、実際の取得は未検証。手元の環境で実行すること。
"""
import argparse
import html
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

INDEX_URL = "https://www.mlit.go.jp/about/file000049.html"
UA = "Mozilla/5.0 (compatible; kaiji-dairishi-study/1.0)"
OUT = pathlib.Path(__file__).resolve().parent.parent / "downloads"

# 「令和5年」「平成29年度」などを西暦に直す
ERA = {"令和": 2018, "平成": 1988}


def to_year(text: str) -> int | None:
    m = re.search(r"(令和|平成)\s*(元|[0-9０-９]+)\s*年", text)
    if not m:
        return None
    era, num = m.group(1), m.group(2)
    n = 1 if num == "元" else int(num.translate(str.maketrans("０１２３４５６７８９", "0123456789")))
    return ERA[era] + n


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def find_pdf_links(page_html: str, base: str) -> list[tuple[str, str]]:
    """(絶対URL, リンクテキスト) のリストを返す。"""
    out, seen = [], set()
    for m in re.finditer(r'<a\s[^>]*href="([^"]+\.pdf)"[^>]*>(.*?)</a>', page_html, re.I | re.S):
        url = urllib.parse.urljoin(base, html.unescape(m.group(1)))
        text = html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
        text = re.sub(r"\s+", " ", text)
        if url in seen:
            continue
        seen.add(url)
        out.append((url, text))
    return out


def kind_of(text: str) -> str:
    if "口述" in text:
        return "koujutsu"
    if "解答" in text:
        return "kaitou"
    return "hikki"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=0, help="新しい方からこの年数分だけ取得（0で全部）")
    ap.add_argument("--list", action="store_true", help="一覧表示のみ")
    ap.add_argument("--url", default=INDEX_URL)
    args = ap.parse_args()

    print(f"索引ページ: {args.url}", file=sys.stderr)
    try:
        page = fetch(args.url).decode("utf-8", "replace")
    except Exception as e:
        print(f"索引ページを取得できなかった: {e}", file=sys.stderr)
        return 1

    links = find_pdf_links(page, args.url)
    if not links:
        print("PDFリンクが見つからない。ページ構成が変わった可能性があるので --url を確認すること。", file=sys.stderr)
        return 1

    items = []
    for url, text in links:
        y = to_year(text) or to_year(page[max(0, page.find(url) - 400):page.find(url)])
        items.append({"url": url, "text": text, "year": y, "kind": kind_of(text)})

    years = sorted({i["year"] for i in items if i["year"]}, reverse=True)
    if args.years and years:
        keep = set(years[: args.years])
        items = [i for i in items if i["year"] in keep]

    for i in items:
        print(f"{i['year'] or '????'}  {i['kind']:9s}  {i['text'][:50]:50s}  {i['url']}")
    if args.list:
        return 0

    OUT.mkdir(exist_ok=True)
    ok = ng = 0
    for i in items:
        name = f"{i['year'] or 'unknown'}_{i['kind']}_{pathlib.Path(urllib.parse.urlparse(i['url']).path).name}"
        dest = OUT / name
        if dest.exists():
            print(f"skip  {name}")
            continue
        try:
            dest.write_bytes(fetch(i["url"]))
            print(f"saved {name}  ({dest.stat().st_size // 1024} KB)")
            ok += 1
            time.sleep(1)  # 相手方のサーバに負荷をかけない
        except Exception as e:
            print(f"FAIL  {i['url']}: {e}", file=sys.stderr)
            ng += 1
    print(f"\n{ok} 件保存 / {ng} 件失敗 → {OUT}")
    return 0 if ng == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
