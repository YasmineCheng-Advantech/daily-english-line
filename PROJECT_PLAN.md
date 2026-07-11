# 每日英文單字 LINE 推播專案 — 規劃文件

> 目標：一個全免費、無伺服器的系統，每天自動抽一個英文單字推播到 LINE，並記錄歷史供網頁回顧。

---

## 1. 專案概覽

| 項目 | 說明 |
|------|------|
| 核心功能 | 每天自動推播一個英文單字（含解釋、例句）到 LINE |
| 資料記錄 | 每天推播的單字寫入 `history.json`（GitHub repo 當資料庫） |
| 回顧功能 | GitHub Pages 靜態網頁，讀 `history.json` 做瀏覽與搜尋 |
| 成本 | 全程 0 元（GitHub + LINE + Gemini 免費額度） |
| 伺服器 | 無（Serverless，靠 GitHub Actions 排程觸發） |

---

## 2. 技術架構

```
┌──────────────────────────────────────────────────────┐
│  GitHub Repo（程式碼 + 資料庫 + 網站三合一）              │
│                                                       │
│  words.json                  ← 單字庫（Gemini 生成）    │
│  history.json                ← 每日推播紀錄（=資料庫）   │
│  push.py                     ← 每日抽字 + 推播主程式     │
│  requirements.txt            ← Python 依賴              │
│  docs/index.html             ← 回顧網頁（GitHub Pages）  │
│  .github/workflows/daily.yml ← cron 排程                │
│  README.md                   ← 設定步驟                 │
└──────────────────────────────────────────────────────┘
        │                              │
   每天 Actions cron 觸發          GitHub Pages 提供靜態頁
        │                              │
   ├ 從 words.json 抽未推過的字      └→ 使用者瀏覽器
   ├ (可選) 呼叫 Gemini 生成新字         fetch history.json
   ├ append 進 history.json             → 顯示回顧/搜尋
   ├ git commit + push 回 repo
   └ LINE Messaging API push 推播
```

### 技術選型與免費額度

| 層級 | 技術 | 免費額度 | 角色 |
|------|------|----------|------|
| 排程 | GitHub Actions | 公開 repo 無限；私有 repo 2000 分鐘/月 | 每天定時觸發 |
| 語言 | Python 3.12 | — | 抽字與推播邏輯 |
| LLM | Google Gemini API | 免費層每日請求額度 | 生成/擴充單字庫 |
| 資料庫 | GitHub repo（JSON 檔） | 隨 repo | 儲存推播歷史 |
| 推播 | LINE Messaging API | 免費方案每月 200–500 則 | 發送到 LINE |
| 網頁 | GitHub Pages | 免費 | 回顧介面 |

---

## 3. 資料結構設計

### `words.json`（單字庫）
```json
[
  {
    "word": "serendipity",
    "pos": "n.",
    "meaning": "意外發現美好事物的能力",
    "example": "Finding this cafe was pure serendipity."
  }
]
```

### `history.json`（推播紀錄 = 資料庫）
```json
[
  {
    "date": "2026-07-11",
    "word": "serendipity",
    "pos": "n.",
    "meaning": "意外發現美好事物的能力",
    "example": "Finding this cafe was pure serendipity."
  }
]
```

> 設計原則：抽字時比對 `history.json` 已出現的 `word`，避免重複；全部推完可再循環或呼叫 Gemini 補新字。

---

## 4. 開發步驟（依序執行）

### Phase 0：環境準備
1. 安裝 VS Code + Python 擴充套件
2. 安裝 Python 3.12+
3. 建立 GitHub repo（建議命名 `daily-english-line`）
4. `git clone` 到本機，用 VS Code 開啟

### Phase 1：申請三組金鑰
| 服務 | 要拿到什麼 | 申請位置 |
|------|-----------|----------|
| LINE | Channel access token + 你的 User ID | LINE Developers Console |
| Gemini | API Key | Google AI Studio |
| GitHub | （Actions 內建權限，暫不需額外 token） | — |

> 三組金鑰**都存進 GitHub repo 的 Settings → Secrets**，不可寫死在程式碼。

### Phase 2：建立單字庫
1. 用 Gemini（或直接請 Claude）生成第一批單字 → `words.json`
2. 人工快速審一遍解釋與例句品質
3. commit 進 repo

### Phase 3：撰寫每日推播程式 `push.py`
邏輯：
1. 讀 `words.json` 與 `history.json`
2. 篩出尚未推播的字，隨機抽一個
3. （若單字庫用完）呼叫 Gemini 生成新字
4. append 進 `history.json`
5. 呼叫 LINE push API 推播
6. 本機先用「今天的字印出來」測試，再接 LINE

### Phase 4：設定 GitHub Actions 排程
1. 建立 `.github/workflows/daily.yml`
2. 設定 `cron: "0 0 * * *"`（UTC 00:00 = 台灣 08:00）
3. 設定 `permissions: contents: write`（讓 Actions 能 commit）
4. 用 `workflow_dispatch` 手動觸發測試一次

### Phase 5：建立回顧網頁
1. 建立 `docs/index.html`（純 HTML + JS）
2. `fetch('../history.json')` 讀資料
3. 功能：依日期瀏覽、搜尋單字、隨機複習
4. GitHub repo Settings → Pages → 指向 `docs/` 資料夾
5. 取得公開網址

### Phase 6（可選）：進階功能
- 網頁「標記已學會」寫回資料 → 需 Cloudflare Workers 免費層當中間層
- 間隔複習演算法（記錄複習次數與日期）
- 多人訂閱 → 改用 LINE webhook + Broadcast API

---

## 5. 建議的檔案結構

```
daily-english-line/
├── .github/
│   └── workflows/
│       └── daily.yml
├── docs/
│   └── index.html
├── words.json
├── history.json
├── push.py
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 6. 待決定事項（開始寫程式前確認）

1. **Gemini 角色**：
   - A. 一次生成大批單字庫，每天只抽（穩、省額度）← 建議
   - B. 每天即時生成新字（活、依賴每日額度）
2. **單字難度/主題**：多益 / 托福 / 日常會話 / 商用英文？
3. **起步單字數量**：建議 100–300 字起步
4. **推播時間**：預設台灣早上 8:00，可調整 cron

---

## 7. 里程碑檢查點

- [ ] Phase 1：三組金鑰申請完成、存入 Secrets
- [ ] Phase 2：`words.json` 有第一批單字
- [ ] Phase 3：本機能成功推播一則到 LINE
- [ ] Phase 4：GitHub Actions 手動觸發成功
- [ ] Phase 5：GitHub Pages 網頁上線可回顧
- [ ] 觀察三天：cron 自動推播無誤
