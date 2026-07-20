"""把一批或多批新單字 JSON 檔合併進單字庫，並做格式驗證與去重。

用法：
    python3 scripts/merge_words.py new_batch.json                  # 預設英文
    python3 scripts/merge_words.py --lang en batch_a.json batch_b.json
    python3 scripts/merge_words.py --lang vi vi_batch.json

英文（--lang en，寫入 data/en/words.json）
------------------------------------------------
驗證規則（任何一項不符合就跳過該筆，並列在報告裡）：
- 必須恰好有 9 個 key: word, pos, meaning, example, level, theme, root, synonyms, antonyms
  （"lang" 不用 LLM 產生，由這支腳本自動補上）
- word/pos/meaning/example 必須是非空字串
- level 必須是 "中階" 或 "中高階"
- theme 必須是非空字串（主題清單是開放式的，不限定在 PROMPT_TEMPLATE.md 列出的建議清單裡；
  push.py 聚類時會正規化大小寫/底線與空白差異，盡量讓同一個主題不同寫法還是能歸在一起，
  但還是建議盡量沿用既有主題名稱，新主題才加新的 slug，避免同一個概念裂成太多相近主題）
- root 必須是 null 或非空字串（字根清單是開放式的，不限定在原本 22 個裡；
  push.py 聚類時只會比對「字根本身」（括號前的部分），不管括號裡的中文解釋
  寫法是否每次一致，所以同一個字根即使解釋文字略有出入也還是能湊成一組）
- synonyms / antonyms 必須是字串陣列（可以是空陣列）
去重：對現有單字庫裡的 word（不分大小寫）視為已存在。

越南文（--lang vi，寫入 data/vi/words.json）
------------------------------------------------
驗證規則：
- 必須恰好有 10 個 key: type, topic, text, meaning_zh, romanization,
  tone_note, example, example_zh, example_rom, grammar_point
  （"id" / "lang" / "region" 三個都由這支腳本自動補，不用 LLM 產生——
    交給 LLM 編 id 幾乎一定會跟現有資料撞號）
- type 必須是 word / phrase / dialogue 其中之一
- topic / text / meaning_zh / romanization / example / example_zh 必須是非空字串
- tone_note / example_rom / grammar_point 允許空字串（不是每筆都要填）
去重：對現有單字庫裡的 text（不分大小寫）視為已存在。
id 會從現有最大號往下接（vi-0011、vi-0012…）。

共通
------------------------------------------------
- 同一次執行合併多個檔案時，後面檔案裡跟前面檔案重複的字也會被跳過
- 每筆都會自動補上 "lang" 欄位，push.py 與回顧網頁靠它區分語言
- 會同步寫一份到 docs/ 供 GitHub Pages 發布（網頁的「整個單字庫」分頁靠這份抓資料）：
  英文 → docs/words.json，越南文 → docs/words.vi.json。
  兩種語言 schema 不同，刻意分成兩個檔，混在一起網頁會解析不出來。
"""

import argparse
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = BASE_DIR / "docs"
# 各語言在 docs/ 底下各有一個發布用副本，schema 不同不能混在同一個檔
DOCS_WORDS_PATHS = {
    "en": DOCS_DIR / "words.json",
    "vi": DOCS_DIR / "words.vi.json",
}

VALID_LEVELS = {"中階", "中高階"}
VALID_VI_TYPES = {"word", "phrase", "dialogue"}

EN_REQUIRED_KEYS = {
    "word", "pos", "meaning", "example", "level", "theme", "root", "synonyms", "antonyms",
}
VI_REQUIRED_KEYS = {
    "type", "topic", "text", "meaning_zh", "romanization",
    "tone_note", "example", "example_zh", "example_rom", "grammar_point",
}


def norm(text: str) -> str:
    return text.strip().lower()


# ---------------------------------------------------------------------------
# 驗證
# ---------------------------------------------------------------------------


def validate_en(entry: dict) -> str | None:
    """回傳錯誤訊息字串；合法的話回傳 None。"""
    if set(entry.keys()) != EN_REQUIRED_KEYS:
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


def validate_vi(entry: dict) -> str | None:
    if set(entry.keys()) != VI_REQUIRED_KEYS:
        return f"key 不對，應該恰好有 10 個: {sorted(entry.keys())}"
    if entry.get("type") not in VALID_VI_TYPES:
        return f"type 不合法（要 word/phrase/dialogue）: {entry.get('type')!r}"
    for field in ("topic", "text", "meaning_zh", "romanization", "example", "example_zh"):
        if not isinstance(entry.get(field), str) or not entry[field].strip():
            return f"{field} 必須是非空字串"
    for field in ("tone_note", "example_rom", "grammar_point"):
        if not isinstance(entry.get(field), str):
            return f"{field} 必須是字串（可以是空字串）"
    return None


# ---------------------------------------------------------------------------
# 各語言設定
# ---------------------------------------------------------------------------


def en_key(entry: dict) -> str:
    return norm(entry["word"])


def vi_key(entry: dict) -> str:
    return norm(entry["text"])


LANG_CONFIG = {
    "en": {
        "validate": validate_en,
        "key": en_key,
        "label": lambda e: e["word"],
    },
    "vi": {
        "validate": validate_vi,
        "key": vi_key,
        "label": lambda e: e["text"],
    },
}


def words_path(lang: str) -> Path:
    return DATA_DIR / lang / "words.json"


def next_vi_id(existing: list[dict]) -> int:
    """接續現有最大的 vi-NNNN 編號。"""
    used = [
        int(m.group(1))
        for e in existing
        if (m := re.fullmatch(r"vi-(\d+)", str(e.get("id", ""))))
    ]
    return max(used, default=0) + 1


def main() -> None:
    parser = argparse.ArgumentParser(description="合併新單字進單字庫")
    parser.add_argument("--lang", choices=sorted(LANG_CONFIG), default="en", help="要合併的語言（預設 en）")
    parser.add_argument(
        "--region",
        default="north",
        help="越南文音系標籤，寫進 region 欄位（預設 north）。英文會忽略此參數。",
    )
    parser.add_argument("files", nargs="+", help="一個或多個 JSON 批次檔")
    args = parser.parse_args()

    lang = args.lang
    config = LANG_CONFIG[lang]
    target = words_path(lang)

    if not target.exists():
        print(f"[錯誤] 找不到 {target.relative_to(BASE_DIR)}，請先建立該語言的單字庫。")
        sys.exit(1)

    with open(target, "r", encoding="utf-8") as f:
        existing = json.load(f)

    seen = {config["key"](w) for w in existing}
    next_id = next_vi_id(existing) if lang == "vi" else None

    added = []
    skipped_duplicate = []
    skipped_invalid = []

    for path_str in args.files:
        path = Path(path_str)
        if not path.exists():
            print(f"[錯誤] 找不到 {path}，略過")
            continue
        with open(path, "r", encoding="utf-8") as f:
            batch = json.load(f)

        if not isinstance(batch, list):
            print(f"[錯誤] {path} 內容不是 JSON 陣列，略過整個檔案")
            continue

        for entry in batch:
            error = config["validate"](entry)
            if error:
                label = entry.get("word") or entry.get("text") or "?"
                skipped_invalid.append((label, error))
                continue

            key = config["key"](entry)
            if key in seen:
                skipped_duplicate.append(config["label"](entry))
                continue

            seen.add(key)

            # 補上不該由 LLM 產生的欄位
            if lang == "vi":
                entry = {
                    "id": f"vi-{next_id:04d}",
                    "lang": "vi",
                    "region": args.region,
                    **entry,
                }
                next_id += 1
            else:
                entry = {**entry, "lang": "en"}

            added.append(entry)

    existing.extend(added)

    targets = [target, DOCS_WORDS_PATHS[lang]]
    for path in targets:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
            f.write("\n")

    print(f"語言: {lang}")
    print(f"新增: {len(added)}")
    print(f"跳過（重複）: {len(skipped_duplicate)}")
    print(f"跳過（格式錯誤）: {len(skipped_invalid)}")
    if skipped_invalid:
        print("\n格式錯誤明細（最多顯示 20 筆）：")
        for label, error in skipped_invalid[:20]:
            print(f"  - {label}: {error}")
    print(f"\n寫入: {', '.join(str(p.relative_to(BASE_DIR)) for p in targets)}")
    print(f"{target.relative_to(BASE_DIR)} 目前總筆數: {len(existing)}")


if __name__ == "__main__":
    main()
