# 越南文擴充規劃文件 — daily-english-line

> 目標：在既有的英文推播專案上，加入**南部音越南文**的每日推播。
> 重點需求：看懂字義（中文）、主題式學習、常用文法帶入、英文式羅馬拼音當發音提示（無音檔、無金鑰、零成本）。

---

## 0. 設計原則（先讀）

1. **多語言共用一套 pipeline**：英文、越南文共用 `push.py`、`history.json`、回顧網頁，只靠 `lang` 欄位區分。未來加泰文同理。
2. **越南文用南部音**（`region: "south"`）。
3. **發音提示用英文式羅馬拼音**，不使用 IPA、不生成音檔、不接任何 TTS。
4. **內容生成用現有的 Gemini**（或你手動 + LLM 輔助），Claude/Gemini 只負責**文字**：中文字義、羅馬拼音、tone_note、例句、文法點。
5. 每則推播是「**主題 + 3 個字/詞 + 1 句對話 + 1 個文法點**」的小組合，符合每天半小時的節奏。

---

## 1. 檔案結構調整

從單一語言結構，調整為多語言結構：

```
daily-english-line/
├── data/
│   ├── en/
│   │   └── words.json          # 原本的英文單字庫（從舊 words.json 搬進來）
│   ├── vi/
│   │   └── words.json          # 【新增】越南文單字庫
│   └── history.json            # 共用歷史（靠 lang 欄位區分語言）
├── push.py                     # 【改】加 --lang 參數，多語言共用
├── formatters.py               # 【新增】各語言的推播文字排版
├── docs/
│   └── index.html              # 【改】加語言切換 tab
├── .github/workflows/
│   ├── daily-en.yml            # 英文推播（原本的，可保留）
│   └── daily-vi.yml            # 【新增】越南文推播（可設不同時間）
├── requirements.txt
├── .env                        # 本機測試用（.gitignore 排除）
├── .gitignore
└── README.md
```

> **搬遷提醒**：把舊的 `words.json` 移到 `data/en/words.json`，並在裡面每筆補上 `"lang": "en"`。`history.json` 移到 `data/` 底下並補 `lang` 欄位。

---

## 2. 資料模型（越南文 item schema）

每一筆越南文 item 的欄位定義：

| 欄位 | 型別 | 說明 | 範例 |
|---|---|---|---|
| `id` | string | 唯一 ID，`vi-` 開頭 | `"vi-0001"` |
| `lang` | string | 語言碼 | `"vi"` |
| `region` | string | 音系 | `"south"` |
| `type` | string | word / phrase / dialogue | `"word"` |
| `topic` | string | 主題分類 | `"greeting"` |
| `text` | string | 越南文原文 | `"xin chào"` |
| `meaning_zh` | string | **中文字義（你的核心需求）** | `"你好"` |
| `romanization` | string | **英文式羅馬拼音（發音提示）** | `"sin chow"` |
| `tone_note` | string | 音容易跑掉的提醒（可空） | `"chào 尾音下降"` |
| `example` | string | 越南文例句 | `"Xin chào, bạn khỏe không?"` |
| `example_zh` | string | 例句中文 | `"你好，你好嗎？"` |
| `example_rom` | string | 例句羅馬拼音（可空） | `"sin chow, ban kwe khom?"` |
| `grammar_point` | string | 隨字帶入的文法點（可空） | `"khỏe không? = ...嗎？疑問句尾"` |

> `tone_note`、`example_rom`、`grammar_point` 允許留空字串，不是每筆都要填。

---

## 3. 起步單字庫（主題：日常打招呼 & 自我介紹）

以下是可直接存成 `data/vi/words.json` 的第一批資料（**北部音／河內腔**）。
（羅馬拼音採英文直覺近似，非嚴格音標；北部音特徵：`d`／`gi`／`r` 三者都發 `z` 音、
`-nh` 與 `-ng` 分得清楚、`ơn` 近 `un`。注意 `đ` 不受此規則影響，仍是 d 音。）

> 原本規格寫「南部音（r→z、d→y）」，但 r→z 其實是北部特徵；南部音的 r 保留捲舌、
> 近英文 r，只有 d／gi 才發 y。兩者不能混用，故整批統一為北部音。
> 日後若要補南部音版本，建議另開 `region: "south"` 的資料，不要混在同一批裡。

已寫入 `data/vi/words.json`（10 筆）。

---

## 4. push.py 多語言改法

核心改動：加一個 `--lang` 參數，讓同一支程式能推不同語言。

### 邏輯流程
1. 解析 `--lang`（`en` 或 `vi`），預設 `en`
2. 讀 `data/{lang}/words.json` 與 `data/history.json`
3. 從 history 篩出「該 lang 尚未推過」的 item，隨機抽一個
4. 用對應語言的 formatter 排版成推播文字
5. append 進 history（含 lang 欄位）
6. 呼叫 LINE push
7. commit history 回 repo

### 關鍵程式片段

```python
import argparse, json, random, os, requests
from pathlib import Path

def load_json(path, default):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))

def pick_item(lang):
    words = load_json(f"data/{lang}/words.json", [])
    history = load_json("data/history.json", [])
    pushed_ids = {h["id"] for h in history if h.get("lang") == lang}
    candidates = [w for w in words if w["id"] not in pushed_ids]
    if not candidates:                      # 全推過了 → 重新循環
        candidates = words
    return random.choice(candidates)

def push_line(text):
    token = os.environ["LINE_TOKEN"]
    user_id = os.environ["LINE_USER_ID"]
    requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
        json={"to": user_id,
              "messages": [{"type": "text", "text": text}]},
    )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", default="en", choices=["en", "vi"])
    args = parser.parse_args()

    item = pick_item(args.lang)

    from formatters import format_message
    text = format_message(args.lang, item)

    push_line(text)

    # 寫回 history
    history = load_json("data/history.json", [])
    from datetime import date
    history.append({"id": item["id"], "lang": args.lang,
                    "date": date.today().isoformat()})
    Path("data/history.json").write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
```

---

## 5. formatters.py（推播排版）

把「怎麼排版一則訊息」獨立出來，每個語言一個函式。

```python
def format_message(lang, item):
    if lang == "vi":
        return format_vi(item)
    return format_en(item)

def format_vi(item):
    lines = []
    topic = item.get("topic", "")
    lines.append(f"【今日越南文 · {topic}】\n")
    lines.append(f"🇻🇳 {item['text']}")
    lines.append(f"意思：{item['meaning_zh']}")
    lines.append(f"唸法：{item['romanization']}")
    if item.get("tone_note"):
        lines.append(f"⚠️ {item['tone_note']}")
    if item.get("example"):
        lines.append(f"\n💬 {item['example']}")
        lines.append(f"    {item.get('example_zh','')}")
        if item.get("example_rom"):
            lines.append(f"    ({item['example_rom']})")
    if item.get("grammar_point"):
        lines.append(f"\n📌 文法：{item['grammar_point']}")
    return "\n".join(lines)

def format_en(item):
    # 沿用你原本英文的排版邏輯
    return (f"【每日英文】{item['word']}\n"
            f"意思：{item.get('meaning','')}\n"
            f"例句：{item.get('example','')}")
```

---

## 6. daily-vi.yml（越南文專用排程）

跟英文分開，可設不同推播時間（例如越南文晚上 9 點）。

```yaml
name: Daily Vietnamese Word
on:
  schedule:
    - cron: "0 13 * * *"   # UTC 13:00 = 台灣 21:00
  workflow_dispatch:

permissions:
  contents: write

jobs:
  push:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python push.py --lang vi
        env:
          LINE_TOKEN: ${{ secrets.CHANNEL_ACCESS_TOKEN }}
          LINE_USER_ID: ${{ secrets.USER_ID }}
      - name: Commit history
        run: |
          git config user.name "github-actions"
          git config user.email "actions@github.com"
          git add data/history.json
          git commit -m "Add Vietnamese word for $(date +%Y-%m-%d)" || echo "No changes"
          git push
```

> 英文的 `daily.yml` 改成 `python push.py --lang en` 即可。

---

## 7. 回顧網頁調整（docs/index.html）

- 讀 `data/history.json`，多一個 **語言切換 tab**（English / Tiếng Việt）
- 依 `lang` 欄位過濾顯示
- 越南文卡片顯示：越南文、中文字義、羅馬拼音、tone_note、例句
- 這步可以最後做，前期先把推播跑起來

---

## 8. 開發順序（依序執行）

- [ ] **Step 1** 建 `data/en/`、`data/vi/` 資料夾，搬遷舊 `words.json` 與 `history.json`，補 `lang` 欄位
- [ ] **Step 2** 放入 `data/vi/words.json` 起步單字庫（附檔）
- [ ] **Step 3** 改寫 `push.py` 加 `--lang` 參數
- [ ] **Step 4** 新增 `formatters.py`
- [ ] **Step 5** 本機測試：`python push.py --lang vi`，確認 LINE 收到越南文推播
- [ ] **Step 6** 新增 `.github/workflows/daily-vi.yml`
- [ ] **Step 7** 到 GitHub → Actions 手動觸發 `daily-vi.yml` 測一次
- [ ] **Step 8**（可選）回顧網頁加語言切換
- [ ] **Step 9** 觀察三天，確認排程自動推播無誤

---

## 9. 之後可擴充（現在不用做）

- 主題輪替：greeting → food → transport → shopping，一個主題推完自動換下一個
- 間隔複習：記錄每個 item 推過幾次，難記的字加權重推
- 每日推「一組」而非「一個」：一次推 3 字 + 1 對話（可調 `pick_item` 抽多個）
- Gemini 自動生成新主題單字庫，擴充 `data/vi/words.json`
