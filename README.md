# 每日商用英文單字 LINE 推播

全免費、無伺服器的每日英文單字推播系統。每天自動從單字庫挑 5 個「彼此相關」的中階到中高階商用英文單字推播到 LINE，並記錄歷史，可透過網頁回顧與複習。

詳細設計請見 [PROJECT_PLAN.md](./PROJECT_PLAN.md)。

## 專案結構

```
.
├── .github/workflows/daily.yml  # 每日 cron 排程
├── docs/index.html              # 回顧網頁（GitHub Pages）
├── words.json                   # 中階～中高階商用英文單字庫（含主題/字根/相似字/反義字標籤）
├── history.json                 # 每日推播紀錄（= 資料庫）
├── push.py                      # 每日抽字 + 推播主程式
└── requirements.txt
```

## 單字庫資料格式

`words.json` 每個單字物件包含：

```json
{
  "word": "leverage",
  "pos": "n.",
  "meaning": "談判籌碼；優勢",
  "example": "Having multiple suppliers gives us leverage in price negotiations.",
  "level": "中高階",
  "theme": "negotiation",
  "root": null,
  "synonyms": ["advantage", "clout"],
  "antonyms": ["disadvantage"]
}
```

- `theme`：固定分類 slug（negotiation、finance、marketing、hr… 共 20 種），用來找同主題的字
- `root`：字根/字首/字尾標籤（例如 `"re- (再次)"`），沒有明顯字根則為 `null`。這個清單是開放式的，不限定只能用某幾個固定詞綴——`push.py` 聚類時只比對括號前的詞綴本身（見 `root_key()`），忽略括號內中文解釋的寫法差異，所以新字根只要格式一致（`"詞綴 (解釋)"`），累積到 2 個以上就能被抽出來湊一組
- `synonyms` / `antonyms`：純英文字串，不需要保證在單字庫裡也找得到，推播時程式會自動比對是否存在

## 擴充單字庫

想自己去其他 LLM（ChatGPT、Gemini…）生成更多單字補進來，可以用 [PROMPT_TEMPLATE.md](./PROMPT_TEMPLATE.md) 裡現成的提示詞，拿到 JSON 後執行：

```bash
python3 scripts/merge_words.py new_batch.json
```

這支腳本會驗證格式、自動去除跟現有單字庫重複的字，並印出新增/跳過的統計。

## 設定步驟

### 1. 申請四組金鑰

`push.py` 每次執行時會用 **Channel ID + Channel Secret** 向 LINE 動態換一個短期（30 天）access token 來推播，而不是手動在 LINE Developers Console 裡「Issue」一個長效 token —— 這樣完全不用擔心 token 過期，也不用之後手動更新。

| 金鑰 | 用途 | 申請位置 |
|------|------|----------|
| `LINE_CHANNEL_ID` | Messaging API channel 的 Channel ID | LINE Official Account Manager → 設定 → Messaging API |
| `LINE_CHANNEL_SECRET` | 同上頁面的 Channel secret | 同上 |
| `LINE_USER_ID` | 你自己的 LINE User ID（推播對象，`U` 開頭 33 碼） | LINE Developers Console → 該 channel → Basic settings →「Your user ID」 |
| `GEMINI_API_KEY` | 即時生成新單字用 | [Google AI Studio](https://aistudio.google.com/apikey) |

> 注意：一定要確認 Messaging API 頁面顯示「狀態：使用中」，且是掛在正確的官方帳號底下，不要跟 LINE Login channel 的 Channel ID / Secret 搞混（兩者格式一樣、但完全不是同一組）。

### 2. 存進 GitHub Secrets

到 GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**，新增：

- `GEMINI_API_KEY`
- `LINE_CHANNEL_ID`
- `LINE_CHANNEL_SECRET`
- `LINE_USER_ID`

**絕對不要**把這些金鑰寫死在程式碼或 commit 進 repo。

### 3. 本機測試（可選，先不接 LINE）

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 不設定 LINE_* 環境變數時，push.py 只會印出今天抽到的字，不會真的推播
python push.py
```

若要本機測試完整推播，先 `export` 四個環境變數再執行：

```bash
export GEMINI_API_KEY=xxx
export LINE_CHANNEL_ID=xxx
export LINE_CHANNEL_SECRET=xxx
export LINE_USER_ID=xxx
python push.py
```

### 4. 啟用 GitHub Actions 排程

`.github/workflows/daily.yml` 已設定：

- `cron: "0 0 * * *"`（UTC 00:00 = 台灣時間 08:00）
- `workflow_dispatch`：可在 GitHub Actions 頁面手動觸發測試
- `permissions: contents: write`：讓 Action 能把新的 `history.json` commit 回 repo

推送到 GitHub 後，到 **Actions** 分頁手動執行一次 `Daily English Word Push` 確認流程正常。

### 5. 開啟 GitHub Pages 回顧網頁

Repo → **Settings → Pages** → Source 選擇 `main` 分支、資料夾選 `/docs`，儲存後會拿到公開網址，例如：

```
https://<你的帳號>.github.io/<repo 名稱>/
```

網頁功能：
- 依日期瀏覽所有推播過的單字（同一天的 5 個字會分組顯示，並標示當天的關聯模式）
- 搜尋單字或中文意思
- 隨機複習模式（先隱藏意思與例句，按按鈕才顯示）

## 抽字邏輯

`push.py` 每天執行時：

1. 讀取 `words.json` 與 `history.json`，算出已經推播過的單字集合
2. 決定今天的**關聯模式**：`theme`（主題）→ `root`（字根字首字尾）→ `synonym`（相似字）→ `antonym`（反義字），依推播天數輪替
3. 依模式從單字庫中挑一個「種子字」，再找出跟它同主題 / 同字根 / 互為相似字 / 互為反義字、且尚未推播過的字，湊成 5 個一組（不夠 5 個時用同主題的字補滿）
4. 若單字庫已經完全用完（可用字不足 5 個），才會**呼叫 Gemini** 即時生成一組新的相關單字備援
5. 把這一組 5 個字 append 進 `history.json`（同一天 5 筆，共用同一個 `cluster_mode` / `cluster_key`）並 commit
6. 用 `LINE_CHANNEL_ID` + `LINE_CHANNEL_SECRET` 換一個短期 access token，把 5 個字合併成一則 LINE 訊息推播（若未設定 LINE 金鑰，僅在本機印出結果方便測試）

## 待辦檢查點

- [ ] 四組金鑰申請完成、存入 Secrets
- [ ] 本機執行 `python push.py` 能正確印出/推播今日單字
- [ ] GitHub Actions 手動觸發成功，且 `history.json` 有被 commit 回 repo
- [ ] GitHub Pages 網頁上線可回顧
- [ ] 觀察三天，確認 cron 自動推播無誤
