# 每日商用英文單字 LINE 推播

全免費、無伺服器的每日英文單字推播系統。每天自動從單字庫（或即時透過 Gemini 生成）挑一個中高階商用英文單字推播到 LINE，並記錄歷史，可透過網頁回顧與複習。

詳細設計請見 [PROJECT_PLAN.md](./PROJECT_PLAN.md)。

## 專案結構

```
.
├── .github/workflows/daily.yml  # 每日 cron 排程
├── docs/index.html              # 回顧網頁（GitHub Pages）
├── words.json                   # 中高階商用英文單字庫（300 字起步）
├── history.json                 # 每日推播紀錄（= 資料庫）
├── push.py                      # 每日抽字 + 推播主程式
└── requirements.txt
```

## 設定步驟

### 1. 申請三組金鑰

| 金鑰 | 用途 | 申請位置 |
|------|------|----------|
| `LINE_CHANNEL_ACCESS_TOKEN` | 推播用的頻道存取權杖 | [LINE Developers Console](https://developers.line.biz/) → Messaging API channel |
| `LINE_USER_ID` | 你自己的 LINE User ID（推播對象） | LINE Developers Console → 你的 Bot 加好友後，用 webhook 或官方工具取得 |
| `GEMINI_API_KEY` | 即時生成新單字用 | [Google AI Studio](https://aistudio.google.com/apikey) |

### 2. 存進 GitHub Secrets

到 GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**，新增：

- `GEMINI_API_KEY`
- `LINE_CHANNEL_ACCESS_TOKEN`
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

若要本機測試完整推播，先 `export` 三個環境變數再執行：

```bash
export GEMINI_API_KEY=xxx
export LINE_CHANNEL_ACCESS_TOKEN=xxx
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
- 依日期瀏覽所有推播過的單字
- 搜尋單字或中文意思
- 隨機複習模式（先隱藏意思與例句，按按鈕才顯示）

## 抽字邏輯

`push.py` 每天執行時：

1. 讀取 `words.json` 與 `history.json`，算出已經推播過的單字集合
2. **優先呼叫 Gemini** 即時生成一個尚未推播過的中高階商用英文新字
3. 若 Gemini 呼叫失敗（未設定金鑰、額度用盡、格式錯誤等），**自動退回**從 `words.json` 單字庫中隨機抽一個尚未推播過的字
4. 將結果 append 進 `history.json` 並 commit
5. 呼叫 LINE Messaging API 推播（若未設定 LINE 金鑰，僅在本機印出結果方便測試）

## 待辦檢查點

- [ ] 三組金鑰申請完成、存入 Secrets
- [ ] 本機執行 `python push.py` 能正確印出/推播今日單字
- [ ] GitHub Actions 手動觸發成功，且 `history.json` 有被 commit 回 repo
- [ ] GitHub Pages 網頁上線可回顧
- [ ] 觀察三天，確認 cron 自動推播無誤
