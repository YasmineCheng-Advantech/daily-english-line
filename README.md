# 每日商用英文單字 LINE 推播

全免費、無伺服器的每日英文單字推播系統。每天自動從單字庫挑 5 個「彼此相關」的中階到中高階商用英文單字推播到 LINE，並記錄歷史，可透過網頁回顧與複習。

詳細設計請見 [PROJECT_PLAN.md](./PROJECT_PLAN.md)。

## 專案結構

```
.
├── .github/workflows/daily.yml  # 每日 cron 排程
├── docs/
│   ├── index.html               # 回顧網頁（GitHub Pages 只發布這個資料夾）
│   ├── words.json               # words.json 的同步副本，網頁靠這份讀取
│   └── history.json             # history.json 的同步副本，網頁靠這份讀取
├── words.json                   # 中階～中高階商用英文單字庫（含主題/字根/相似字/反義字標籤，目前 3135 字）
├── history.json                 # 每日推播紀錄（= 資料庫）
├── push.py                      # 每日抽字 + 推播主程式
├── scripts/merge_words.py       # 把新一批單字合併進 words.json（驗證格式 + 去重）
├── PROMPT_TEMPLATE.md           # 給其他 LLM 生成單字用的固定格式提示詞
└── requirements.txt
```

> **注意**：GitHub Pages 設定成只發布 `/docs` 資料夾，所以根目錄的 `words.json`／`history.json` 不會被公開網站讀到。`push.py` 和 `scripts/merge_words.py` 都會在更新根目錄檔案的同時，自動把同一份內容也寫進 `docs/`，兩邊必須保持同步——如果手動修改了根目錄的 JSON，記得同時 `cp words.json docs/words.json`（history.json 同理），否則網頁看到的會是舊資料。

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

- `theme`：分類 slug，用來找同主題的字。清單是開放式的——目前常用的有 negotiation、finance、marketing、hr、semiconductor、tech_industry、creative、media 等，新主題可以隨時加入，不限定只能用固定清單裡的。`push.py` 聚類時會正規化大小寫/空白/連字號差異（見 `theme_key()`），盡量讓同一個主題不同寫法還是能歸在一起，但同一個概念建議沿用既有的 slug，避免拆成太多相近主題
- `root`：字根/字首/字尾標籤（例如 `"re- (再次)"`），沒有明顯字根則為 `null`。這個清單也是開放式的，不限定只能用某幾個固定詞綴——`push.py` 聚類時只比對括號前的詞綴本身（見 `root_key()`），忽略括號內中文解釋的寫法差異，所以新字根只要格式一致（`"詞綴 (解釋)"`），累積到 2 個以上就能被抽出來湊一組
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

- `cron: "17 0 * * *"`（UTC 00:17 = 台灣時間 08:17，刻意避開整點以降低 GitHub 排程壅塞延遲）
- `workflow_dispatch`：可在 GitHub Actions 頁面手動觸發測試
- `permissions: contents: write`：讓 Action 能把新的 `history.json`（含 `docs/history.json`）commit 回 repo

推送到 GitHub 後，到 **Actions** 分頁手動執行一次 `Daily English Word Push` 確認流程正常。

> GitHub Actions 的排程不保證準時，官方文件明講整點是最壅塞的時段。如果發現排程遲遲沒有自動觸發，先檢查 **Actions** 分頁的執行紀錄裡有沒有 `schedule` 觸發的紀錄（不是 `workflow_dispatch`），沒有的話可以手動觸發一次補推播，並考慮把 cron 時間再往後挪一點。

### 5. 開啟 GitHub Pages 回顧網頁

Repo → **Settings → Pages** → Source 選擇 `main` 分支、資料夾選 `/docs`，儲存後會拿到公開網址，例如：

```
https://<你的帳號>.github.io/<repo 名稱>/
```

網頁功能：
- **今日推播狀態卡片**：用台灣時間判斷今天推播過沒有；已推播會列出今天的字，還沒推播則顯示一個連到 GitHub Actions「Run workflow」頁面的按鈕，可手動觸發（一天仍然只會真的推播一次，防重複邏輯在 `push.py` 裡，跟手動/排程觸發無關）
- **瀏覽/搜尋**：預設只顯示最新 3 天的推播紀錄（同一天的 5 個字分組顯示，並標示當天的關聯模式）；輸入搜尋文字後改成搜尋全部歷史紀錄
- **隨機複習**：先隱藏意思與例句，按按鈕才顯示；分兩種來源：
  - 「已推播過的」：從最新 10 個推播過的字（約最近 2 天）隨機抽
  - 「整個單字庫」：切進來時隨機抽 10 個字當這輪複習範圍，可按「換一批新的 10 個」重新抽
- 手動切換淺色/深色主題（預設跟隨系統，選擇後存在瀏覽器 localStorage）

> 「手動觸發今日推播」刻意不做成網頁上一鍵直接觸發，因為那需要在網頁的 JavaScript 裡放一個能觸發 GitHub Actions 的權杖——這種公開靜態網頁沒有安全的方式藏密鑰，權杖會直接曝露在原始碼裡。改成連到 GitHub Actions 頁面，靠你自己（repo 擁有者）登入後按鈕確認，安全且不用額外架設服務。

## 抽字邏輯

`push.py` 每天執行時：

1. 讀取 `words.json` 與 `history.json`，算出已經推播過的單字集合
2. 決定今天的**關聯模式**：`theme`（主題）→ `root`（字根字首字尾）→ `synonym`（相似字）→ `antonym`（反義字），依推播天數輪替
3. 依模式從單字庫中挑一個「種子字」，再找出跟它同主題 / 同字根 / 互為相似字 / 互為反義字、且尚未推播過的字，湊成 5 個一組（不夠 5 個時用同主題的字補滿）
4. 若單字庫已經完全用完（可用字不足 5 個），才會**呼叫 Gemini** 即時生成一組新的相關單字備援
5. 把這一組 5 個字 append 進 `history.json`（同一天 5 筆，共用同一個 `cluster_mode` / `cluster_key`）並 commit
6. 用 `LINE_CHANNEL_ID` + `LINE_CHANNEL_SECRET` 換一個短期 access token，把 5 個字合併成一則 LINE 訊息推播（若未設定 LINE 金鑰，僅在本機印出結果方便測試）

## 待辦檢查點

- [x] 四組金鑰申請完成、存入 Secrets
- [x] 本機執行 `python push.py` 能正確印出/推播今日單字
- [x] GitHub Actions 手動觸發成功，且 `history.json`（含 `docs/history.json`）有被 commit 回 repo
- [x] GitHub Pages 網頁上線可回顧
- [ ] 觀察排程是否穩定準時自動觸發（cron 已從整點改到 00:17 UTC，持續觀察中）
