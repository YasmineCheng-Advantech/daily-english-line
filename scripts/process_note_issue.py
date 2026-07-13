"""解析一則「個人單字紀錄」GitHub Issue（依 .github/ISSUE_TEMPLATE/vocab-note.yml 格式），
把裡面的多個單字各自 append 成一筆進 notes.json（同步 docs/notes.json）。

一次可以記多個字（單字欄位一行一個或逗號分隔），共用同一組來源資訊。
每筆先標記 "enriched": false，中文意思等完整資訊之後由 scripts/enrich_notes.py 補上。

用法（由 GitHub Actions 呼叫，也可本機測試）：
    ISSUE_NUMBER=123 ISSUE_BODY="$(cat body.txt)" python3 scripts/process_note_issue.py
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
NOTES_PATH = BASE_DIR / "notes.json"
DOCS_NOTES_PATH = BASE_DIR / "docs" / "notes.json"

# 對應 .github/ISSUE_TEMPLATE/vocab-note.yml 裡 source_type 的下拉選項文字
SOURCE_TYPE_SLUGS = {
    "YouTube 影片": "youtube",
    "Podcast": "podcast",
    "短影音（Reels / Shorts / TikTok）": "shorts",
    "其他": "other",
}

NO_RESPONSE = "_No response_"


def parse_issue_form_body(body: str) -> list[str]:
    """依序抓出每個 `### 標題` 底下的內容，回傳依欄位順序排列的字串陣列。

    只依 .github/ISSUE_TEMPLATE/vocab-note.yml 裡欄位定義的順序取值（words, source_type,
    source_name, link, note），不比對標題文字本身，避免之後調整中文標題就讓解析失效。
    """
    normalized = body.strip() + "\n\n### __END__\n"
    sections = re.findall(r"### .+?\n+([\s\S]*?)(?=\n### )", normalized)
    return [s.strip() for s in sections]


def clean(value: str) -> str:
    return "" if value.strip() == NO_RESPONSE else value.strip()


def split_words(raw: str) -> list[str]:
    """一行一個或逗號分隔都接受，去掉空白與重複（保留順序）。"""
    parts = re.split(r"[\n,]+", raw)
    seen = set()
    words = []
    for p in parts:
        w = p.strip()
        key = w.lower()
        if w and key not in seen:
            seen.add(key)
            words.append(w)
    return words


def main() -> None:
    issue_number = os.environ.get("ISSUE_NUMBER", "")
    body = os.environ.get("ISSUE_BODY", "")

    values = parse_issue_form_body(body)
    if len(values) < 5:
        print(f"[error] 解析欄位數量不足（預期 5，實際 {len(values)}），略過。")
        sys.exit(1)

    words_raw, source_type_label, source_name, link, note = values[:5]

    words = split_words(clean(words_raw))
    if not words:
        print("[error] 沒有解析到任何單字，略過。")
        sys.exit(1)

    source_type = SOURCE_TYPE_SLUGS.get(source_type_label.strip(), "other")
    source_name = clean(source_name)
    link = clean(link)
    note = clean(note)
    date_added = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    issue_num = int(issue_number) if issue_number.isdigit() else None

    notes = json.loads(NOTES_PATH.read_text(encoding="utf-8")) if NOTES_PATH.exists() else []
    existing = {n["word"].strip().lower() for n in notes}

    added = 0
    for word in words:
        if word.lower() in existing:
            print(f"[info] 已存在，略過：{word}")
            continue
        existing.add(word.lower())
        notes.append(
            {
                "word": word,
                "meaning": "",
                "pos": "",
                "example": "",
                "level": "",
                "theme": "",
                "root": None,
                "synonyms": [],
                "antonyms": [],
                "source_type": source_type,
                "source_name": source_name,
                "link": link,
                "note": note,
                "date_added": date_added,
                "issue_number": issue_num,
                "enriched": False,
            }
        )
        added += 1

    for path in (NOTES_PATH, DOCS_NOTES_PATH):
        path.write_text(json.dumps(notes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[info] 已新增 {added} 筆個人紀錄（來源：{source_type}），等待補充完整資訊。")


if __name__ == "__main__":
    main()
