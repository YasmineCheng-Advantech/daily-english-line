"""把 notes.json 裡「還沒補充完整資訊」的個人紀錄（enriched == False），
用 Gemini 補齊成跟單字庫一樣的欄位（pos/meaning/example/level/theme/root/synonyms/antonyms）。

設計成可以安全重跑：只處理 enriched == False 的字，補成功才標記 enriched = True，
補不動的（例如 Gemini 429）就維持原狀，下次再試。若 Gemini 長期補不動，
可以改由 Claude 在對話裡批次補（讀 notes.json、填好未補的字、寫回兩份檔案）。

用法：
    GEMINI_API_KEY=xxx python3 scripts/enrich_notes.py
    # 沒有 GEMINI_API_KEY 時直接結束，不影響其他流程
"""

import json
import os
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
NOTES_PATH = BASE_DIR / "notes.json"
DOCS_NOTES_PATH = BASE_DIR / "docs" / "notes.json"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)

ENRICH_FIELDS = ("pos", "meaning", "example", "level", "theme", "root", "synonyms", "antonyms")


def save(notes: list) -> None:
    for path in (NOTES_PATH, DOCS_NOTES_PATH):
        path.write_text(json.dumps(notes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def enrich_one(word: str) -> dict | None:
    prompt = (
        f'請為英文單字或片語 "{word}" 補充以下資訊，只回傳一個 JSON 物件，'
        "不要加任何說明文字或 markdown 標記，格式為："
        '{"pos": "詞性縮寫，如 n./v./adj./adv./phr.", '
        '"meaning": "繁體中文意思（簡短，20字內）", '
        '"example": "一句自然的英文例句", '
        '"level": "中階 或 中高階", '
        '"theme": "一個英文主題 slug（小寫底線），例如 daily/business/technology 等", '
        '"root": "字根字首字尾標籤，格式 \\"詞綴 (中文解釋)\\"，沒有明顯字根則為 null", '
        '"synonyms": ["1-3個英文同義字"], '
        '"antonyms": ["0-2個英文反義字"]}'
    )
    try:
        resp = requests.post(
            GEMINI_URL,
            params={"key": GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        data = json.loads(text)
        if not data.get("meaning"):
            return None
        return {k: data.get(k) for k in ENRICH_FIELDS}
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 補充失敗（{word}）：{e}")
        return None


def main() -> None:
    if not NOTES_PATH.exists():
        print("[info] 沒有 notes.json，略過。")
        return

    notes = json.loads(NOTES_PATH.read_text(encoding="utf-8"))
    pending = [n for n in notes if not n.get("enriched")]
    if not pending:
        print("[info] 沒有待補充的個人紀錄。")
        return

    if not GEMINI_API_KEY:
        print(f"[info] 未設定 GEMINI_API_KEY，{len(pending)} 筆待補充暫時保留（可之後補）。")
        return

    filled = 0
    for note in pending:
        result = enrich_one(note["word"])
        if result is None:
            continue
        note.update(result)
        note["enriched"] = True
        filled += 1

    save(notes)
    print(f"[info] 本次補充成功 {filled} / {len(pending)} 筆；剩 {len(pending) - filled} 筆待下次重試。")


if __name__ == "__main__":
    main()
