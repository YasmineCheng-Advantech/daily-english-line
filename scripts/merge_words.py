"""把一批或多批新單字 JSON 檔合併進 words.json，並做格式驗證與去重。

用法：
    python3 scripts/merge_words.py new_batch.json
    python3 scripts/merge_words.py batch_a.json batch_b.json batch_c.json

驗證規則（任何一項不符合就跳過該筆，並列在報告裡）：
- 必須恰好有 9 個 key: word, pos, meaning, example, level, theme, root, synonyms, antonyms
- word/pos/meaning/example 必須是非空字串
- level 必須是 "中階" 或 "中高階"
- theme 必須是固定清單裡的其中一個
- root 必須是 null 或固定清單裡的其中一個
- synonyms / antonyms 必須是字串陣列（可以是空陣列）

去重規則：
- 對現有 words.json 裡的字（不分大小寫）視為已存在，不會再加入
- 同一次執行合併多個檔案時，後面檔案裡跟前面檔案重複的字也會被跳過
"""

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
WORDS_PATH = BASE_DIR / "words.json"

VALID_THEMES = {
    "negotiation", "contracts_legal", "finance", "accounting", "marketing",
    "sales", "management", "leadership", "hr", "customer_service",
    "operations", "supply_chain", "project_management", "technology_it",
    "strategy", "compliance_risk", "economics", "trade", "communication",
    "presentations",
}

VALID_ROOTS = {
    "co-/con- (共同)", "counter- (相反/反制)", "over- (過度)", "under- (不足)",
    "re- (再次)", "de- (去除/相反)", "dis- (不/相反)", "sub- (次要/下)",
    "inter- (之間/相互)", "trans- (轉移/跨越)", "multi- (多)", "mono-/uni- (單一)",
    "pre- (事前)", "post- (事後)", "pro- (支持/向前)", "auto- (自動)",
    "-ize/-ise (使成為)", "-tion/-sion (名詞化:動作結果)", "-ment (名詞化:狀態結果)",
    "-able/-ible (可…的)", "-ship (身分狀態)", "-ance/-ence (性質狀態)",
}

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
    if entry.get("theme") not in VALID_THEMES:
        return f"theme 不合法: {entry.get('theme')!r}"
    root = entry.get("root")
    if root is not None and root not in VALID_ROOTS:
        return f"root 不合法: {root!r}"
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

    with open(WORDS_PATH, "w", encoding="utf-8") as f:
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
