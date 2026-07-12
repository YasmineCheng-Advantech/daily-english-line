"""把一批或多批新單字 JSON 檔合併進 words.json，並做格式驗證與去重。

用法：
    python3 scripts/merge_words.py new_batch.json
    python3 scripts/merge_words.py batch_a.json batch_b.json batch_c.json

驗證規則（任何一項不符合就跳過該筆，並列在報告裡）：
- 必須恰好有 9 個 key: word, pos, meaning, example, level, theme, root, synonyms, antonyms
- word/pos/meaning/example 必須是非空字串
- level 必須是 "中階" 或 "中高階"
- theme 必須是非空字串（主題清單是開放式的，不限定在 PROMPT_TEMPLATE.md 列出的建議清單裡；
  push.py 聚類時會正規化大小寫/底線與空白差異，盡量讓同一個主題不同寫法還是能歸在一起，
  但還是建議盡量沿用既有主題名稱，新主題才加新的 slug，避免同一個概念裂成太多相近主題）
- root 必須是 null 或非空字串（字根清單是開放式的，不限定在原本 22 個裡；
  push.py 聚類時只會比對「字根本身」（括號前的部分），不管括號裡的中文解釋
  寫法是否每次一致，所以同一個字根即使解釋文字略有出入也還是能湊成一組）
- synonyms / antonyms 必須是字串陣列（可以是空陣列）

去重規則：
- 對現有 words.json 裡的字（不分大小寫）視為已存在，不會再加入
- 同一次執行合併多個檔案時，後面檔案裡跟前面檔案重複的字也會被跳過

會同時寫入 words.json（根目錄，供 push.py 讀取）與 docs/words.json（GitHub Pages
實際發布的內容，網頁靠這份才抓得到資料）兩份，保持同步。
"""

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
WORDS_PATH = BASE_DIR / "words.json"
DOCS_WORDS_PATH = BASE_DIR / "docs" / "words.json"

VALID_LEVELS = {"中階", "中高階"}
REQUIRED_KEYS = {
    "word", "pos", "meaning", "example", "level", "theme", "root", "synonyms", "antonyms",
}


def norm(word: str) -> str:
    return word.strip().lower()


def validate_entry(entry: dict) -> str | None:
    """回傳錯誤訊息字串；合法的話回傳 None。"""
    if set(entry.keys()) != REQUIRED_KEYS:
        return f"key 不對，應該恰好有 9 個: {sorted(entry.keys())}"
    for field in ("word", "pos", "meaning", "example"):
        if not isinstance(entry.get(field), str) or not entry[field].strip():
            return f"{field} 必須是非空字串"
    if entry.get("level") not in VALID_LEVELS:
        return f"level 不合法: {entry.get('level')!r}"
    theme = entry.get("theme")
    if not isinstance(theme, str) or not theme.strip():
        return f"theme 必須是非空字串: {theme!r}"
    root = entry.get("root")
    if root is not None and (not isinstance(root, str) or not root.strip()):
        return f"root 必須是 null 或非空字串: {root!r}"
    for field in ("synonyms", "antonyms"):
        val = entry.get(field)
        if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
            return f"{field} 必須是字串陣列"
    return None


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python3 scripts/merge_words.py <batch1.json> [batch2.json ...]")
        sys.exit(1)

    with open(WORDS_PATH, "r", encoding="utf-8") as f:
        existing = json.load(f)

    seen = {norm(w["word"]) for w in existing}
    added = []
    skipped_duplicate = []
    skipped_invalid = []

    for path_str in sys.argv[1:]:
        path = Path(path_str)
        with open(path, "r", encoding="utf-8") as f:
            batch = json.load(f)

        if not isinstance(batch, list):
            print(f"[錯誤] {path} 內容不是 JSON 陣列，略過整個檔案")
            continue

        for entry in batch:
            error = validate_entry(entry)
            if error:
                skipped_invalid.append((entry.get("word", "?"), error))
                continue

            key = norm(entry["word"])
            if key in seen:
                skipped_duplicate.append(entry["word"])
                continue

            seen.add(key)
            added.append(entry)

    existing.extend(added)

    for path in (WORDS_PATH, DOCS_WORDS_PATH):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
            f.write("\n")

    print(f"新增: {len(added)}")
    print(f"跳過（重複）: {len(skipped_duplicate)}")
    print(f"跳過（格式錯誤）: {len(skipped_invalid)}")
    if skipped_invalid:
        print("\n格式錯誤明細（最多顯示 20 筆）：")
        for word, error in skipped_invalid[:20]:
            print(f"  - {word}: {error}")
    print(f"\nwords.json 目前總字數: {len(existing)}")


if __name__ == "__main__":
    main()
