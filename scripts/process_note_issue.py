"""解析一則「個人單字紀錄」GitHub Issue（依 .github/ISSUE_TEMPLATE/vocab-note.yml 格式），
append 進 notes.json（同步 docs/notes.json）。

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

    GitHub Issue Form 送出後，body 會是固定格式：
    ### <label>\n\n<answer>\n\n### <label>\n\n<answer>\n\n...
    這裡不比對標題文字本身，只依照 .github/ISSUE_TEMPLATE/vocab-note.yml 裡欄位定義的
    順序取值，避免之後調整中文標題文字就讓解析失效。
    """
    normalized = body.strip() + "\n\n### __END__\n"
    sections = re.findall(r"### .+?\n+([\s\S]*?)(?=\n### )", normalized)
    return [s.strip() for s in sections]


def clean(value: str) -> str:
    return "" if value.strip() == NO_RESPONSE else value.strip()


def main() -> None:
    issue_number = os.environ.get("ISSUE_NUMBER", "")
    body = os.environ.get("ISSUE_BODY", "")

    values = parse_issue_form_body(body)
    if len(values) < 6:
        print(f"[error] 解析欄位數量不足（預期 6，實際 {len(values)}），略過。")
        sys.exit(1)

    word, meaning, source_type_label, source_name, link, note = values[:6]

    word = clean(word)
    if not word:
        print("[error] 單字欄位是空的，略過。")
        sys.exit(1)

    entry = {
        "word": word,
        "meaning": clean(meaning),
        "source_type": SOURCE_TYPE_SLUGS.get(source_type_label.strip(), "other"),
        "source_name": clean(source_name),
        "link": clean(link),
        "note": clean(note),
        "date_added": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d"),
        "issue_number": int(issue_number) if issue_number.isdigit() else None,
    }

    notes = json.loads(NOTES_PATH.read_text(encoding="utf-8")) if NOTES_PATH.exists() else []
    notes.append(entry)

    for path in (NOTES_PATH, DOCS_NOTES_PATH):
        path.write_text(json.dumps(notes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[info] 已新增個人紀錄：{word}（來源：{entry['source_type']}）")


if __name__ == "__main__":
    main()
