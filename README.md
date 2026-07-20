# 每日單字 LINE 推播（多語言）

全免費、無伺服器的每日單字推播系統。每天自動從單字庫挑 5 個「彼此相關」的單字推播到 LINE，並記錄歷史，可透過網頁回顧與複習。

目前支援 **英文**（中階～中高階商用英文，每天 08:17）與 **越南文**（北部／河內腔，每晚 21:00）。

詳細設計請見 [PROJECT_PLAN.md](./PROJECT_PLAN.md)。

## 專案結構

```
.
├── data/
│   ├── en/words.json            # 商用英文單字庫（主題/字根/相似字/反義字標籤，目前 3635 字）
│   ├── vi/words.json            # 越南文單字庫（北部音，含羅馬拼音與文法點）
│   └── history.json             # 每日推播紀錄（= 資料庫），各語言共用，靠 lang 欄位區分
├── push.py                      # 每日抽字 + 推播主程式（--lang en|vi、--dry-run）
├── formatters.py                # 各語言的推播訊息排版（format_message）
├── docs/
│   ├── index.html               # 回顧網頁（GitHub Pages 只發布這個資料夾）
│   ├── words.json               # data/en/words.json 的同步副本，網頁靠這份讀取
│   ├── history.json             # data/history.json 的同步副本，網頁靠這份讀取
│   └── notes.json               # notes.json 的同步副本
├── notes.json                   # 個人單字紀錄（從影片/Podcast/短影音等自己記錄的字）
├── scripts/
│   ├── merge_words.py           # 把新一批單字合併進單字庫（--lang en|vi，驗證格式 + 去重）
│   ├── process_note_issue.py    # 解析「個人單字紀錄」GitHub Issue，拆多字寫進 notes.json
│   └── enrich_notes.py          # 用 Gemini 把待補充的個人紀錄補齊成完整欄位
├── .github/workflows/
│   ├── daily.yml                # 英文每日 cron 排程（台灣時間 08:17）
│   ├── daily-vi.yml             # 越南文每日 cron 排程（台灣時間 21:00）
│   └── process-note.yml         # 偵測到新的 vocab-note issue 就自動處理
├── .github/ISSUE_TEMPLATE/vocab-note.yml  # 個人單字紀錄的 GitHub Issue Form 樣板
├── PROMPT_TEMPLATE.md           # 給其他 LLM 生成英文單字用的固定格式提示詞
├── PROMPT_TEMPLATE_VI.md        # 同上，越南文版
└── requirements.txt
```

> **注意**：GitHub Pages 設定成只發布 `/docs` 資料夾，所以 `data/` 底下的檔案不會被公開網站讀到。`push.py`、`scripts/merge_words.py`、`scripts/process_note_issue.py` 都會在更新來源檔案的同時，自動把同一份內容也寫進 `docs/`，兩邊必須保持同步——如果手動修改了 `data/` 裡的 JSON，記得同時 `cp data/en/words.json docs/words.json`（`data/history.json` → `docs/history.json`、`notes.json` → `docs/notes.json` 同理），否則網頁看到的會是舊資料。
>
> 越南文單字庫**不會**同步到 `docs/words.json`——那份是英文 schema，混進不同結構的資料網頁會解析不出來。越南文的推播紀錄則照常寫進 `data/history.json` 與 `docs/history.json`。

## 執行方式

```bash
python3 push.py                        # 等同 --lang en
python3 push.py --lang vi              # 推越南文
python3 push.py --lang vi --dry-run    # 只印出排版結果，不寫紀錄也不發送
```

`--dry-run` 完全不會讀取 LINE 金鑰、不呼叫發送函式、不寫入 `data/history.json`，所以在沒設定任何環境變數的機器上也能安全預覽。

## 單字庫資料格式

### 英文（`data/en/words.json`）

每個單字物件包含：

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
  "antonyms": ["disadvantage"],
  "lang": "en"
}
```

- `theme`：分類 slug，用來找同主題的字。清單是開放式的——目前常用的有 negotiation、finance、marketing、hr、semiconductor、tech_industry、creative、media 等，新主題可以隨時加入，不限定只能用固定清單裡的。`push.py` 聚類時會正規化大小寫/空白/連字號差異（見 `theme_key()`），盡量讓同一個主題不同寫法還是能歸在一起，但同一個概念建議沿用既有的 slug，避免拆成太多相近主題
- `root`：字根/字首/字尾標籤（例如 `"re- (再次)"`），沒有明顯字根則為 `null`。這個清單也是開放式的，不限定只能用某幾個固定詞綴——`push.py` 聚類時只比對括號前的詞綴本身（見 `root_key()`），忽略括號內中文解釋的寫法差異，所以新字根只要格式一致（`"詞綴 (解釋)"`），累積到 2 個以上就能被抽出來湊一組
- `synonyms` / `antonyms`：純英文字串，不需要保證在單字庫裡也找得到，推播時程式會自動比對是否存在
- `lang`：固定 `"en"`，由 `merge_words.py` 自動補上，不用 LLM 產生

### 越南文（`data/vi/words.json`）

```json
{
  "id": "vi-0001",
  "lang": "vi",
  "region": "north",
  "type": "phrase",
  "topic": "打招呼",
  "text": "xin chào",
  "meaning_zh": "你好（較正式）",
  "romanization": "sin chow",
  "tone_note": "chào 尾音往下降；日常也常只說「chào」+ 稱謂，不加 xin",
  "example": "Xin chào, rất vui được gặp bạn.",
  "example_zh": "你好，很高興認識你。",
  "example_rom": "sin chow, zut vui duoc gap ban",
  "grammar_point": "xin 是禮貌前綴，讓招呼更客氣"
}
```

- `region`：音系標籤，目前全部是 `"north"`（北部／河內腔）
- `romanization` / `example_rom`：**英文式近似拼音，不是 IPA**，給看不懂音標的人直接照著唸
- `topic`：主題分類（繁體中文）。越南文標籤只有 topic，沒有字根/相似字/反義字，所以 `push.py` 對越南文統一依 topic 分組，不做模式輪替
- `id` / `lang` / `region` 三個欄位都由 `merge_words.py` 自動補上，不用 LLM 產生

> **關於音系**：專案原本規劃南部音，但當初規格把「r 發 z 音」寫成南部特徵，實際上那是**北部**音；南部音的 `r` 保留捲舌、近英文 r，只有 `d`／`gi` 才發 y 音。兩者不能混用，所以整批統一成北部音。日後要做南部音版本，請另外開一批 `--region south` 的資料。

## 擴充單字庫

想自己去其他 LLM（ChatGPT、Gemini…）生成更多單字補進來，用現成的提示詞範本：

| 語言 | 範本 | 合併指令 |
|---|---|---|
| 英文 | [PROMPT_TEMPLATE.md](./PROMPT_TEMPLATE.md) | `python3 scripts/merge_words.py new_batch.json` |
| 越南文 | [PROMPT_TEMPLATE_VI.md](./PROMPT_TEMPLATE_VI.md) | `python3 scripts/merge_words.py --lang vi vi_batch.json` |

這支腳本會驗證格式、自動去除跟現有單字庫重複的字、補上 `lang`（越南文還會自動編 `id` 與補 `region`），並印出新增/跳過的統計。

> **越南文單字庫目前只有 10 筆**，而 `daily-vi.yml` 每晚推 5 筆，所以第 3 天起就會開始重複第一輪內容（`source` 會標成 `bank-recycled`）。建議先擴充到 50 筆以上再讓排程長期跑。

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

# 只想看排版結果、不寫紀錄也不發送（不需要任何環境變數）
python push.py --lang en --dry-run
python push.py --lang vi --dry-run

# 不設定 LINE_* 環境變數時，push.py 會照常寫入紀錄，但只印出訊息不真的推播
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
- `workflow_dispatch`：可在 GitHub Actions 頁面手動觸發
- `permissions: contents: write`：讓 Action 能把新的 `history.json`（含 `docs/history.json`）commit 回 repo
- `concurrency: daily-push`：讓多次快速的手動加推排隊依序執行，避免同時 git push 撞車

推送到 GitHub 後，到 **Actions** 分頁手動執行一次 `Daily English Word Push` 確認流程正常。

**一天可以推播幾次？**

- **排程（cron）觸發**：保證一天一次。就算 cron 偶發重複觸發，也不會重複推（`push.py` 會檢查今天是否已經有「排程」推播）。
- **手動（workflow_dispatch）觸發**：想多學就多按。每次手動觸發都會**額外加推一組新的字**（不受「一天一次」限制），選字會排除已推過的字、關聯模式也會每組輪替（主題→字根→相似→反義）。網頁「今日推播狀態卡片」上永遠有一顆按鈕連到這裡。
- 每筆推播紀錄會標上 `trigger`（schedule/manual）與 `pushed_at`（精確到微秒），網頁靠這個把同一天的多組推播分開顯示。

> 提醒：LINE 免費方案每月訊息量有限（約 200–500 則），每推一次用掉一則，狂加推會消耗較快。
>
> GitHub Actions 的排程不保證準時，官方文件明講整點是最壅塞的時段。如果發現排程遲遲沒有自動觸發，先檢查 **Actions** 分頁有沒有 `schedule` 觸發的紀錄，沒有的話可以手動觸發一次補推播。

### 5. 開啟 GitHub Pages 回顧網頁

Repo → **Settings → Pages** → Source 選擇 `main` 分支、資料夾選 `/docs`，儲存後會拿到公開網址，例如：

```
https://<你的帳號>.github.io/<repo 名稱>/
```

網頁功能：
- **今日推播狀態卡片**：用台灣時間判斷今天推播了幾組；已推播會列出今天的字並顯示「➕ 再加推一組」按鈕，還沒推播則顯示「🚀 手動觸發推播」按鈕——兩者都連到 GitHub Actions「Run workflow」頁面，手動觸發即可加推（見上面「一天可以推播幾次？」）
- **瀏覽/搜尋**：預設只顯示最新 3 天的推播紀錄（每一「組」推播是一張卡片，標示日期／時間與該組的關聯模式；同一天多組加推會分開成多張卡）；輸入搜尋文字後改成搜尋全部歷史紀錄
- **隨機複習**：先隱藏意思與例句，按按鈕才顯示；分兩種來源：
  - 「已推播過的」：從最新 10 個推播過的字（約最近 2 天）隨機抽
  - 「整個單字庫」：切進來時隨機抽 10 個字當這輪複習範圍，可按「換一批新的 10 個」重新抽
- 手動切換淺色/深色主題（預設跟隨系統，選擇後存在瀏覽器 localStorage）

> 「手動觸發今日推播」刻意不做成網頁上一鍵直接觸發，因為那需要在網頁的 JavaScript 裡放一個能觸發 GitHub Actions 的權杖——這種公開靜態網頁沒有安全的方式藏密鑰，權杖會直接曝露在原始碼裡。改成連到 GitHub Actions 頁面，靠你自己（repo 擁有者）登入後按鈕確認，安全且不用額外架設服務。

## 個人單字紀錄（從影片/Podcast/短影音記錄單字）

網頁「個人紀錄」分頁可以記錄自己在 YouTube 影片、Podcast、短影音（Reels/Shorts/TikTok）等地方看到的單字。設計上把「捕捉」和「補充」分開，讓記錄門檻盡量低：**你只要填英文單字（可一次貼多個，一行一個）+ 一個共用來源**，其他資訊之後自動補。

**運作方式**（全程免費、沒有額外伺服器）：

1. 網頁表單送出後，會組合出一個**預先填好內容的 GitHub Issue 網址**並開新分頁，不會把任何金鑰放進網頁的 JavaScript 裡
2. 你（repo 擁有者，已登入 GitHub）確認後按「Submit new issue」，issue 自動帶上 `vocab-note` 標籤
3. `.github/workflows/process-note.yml` 偵測到新 issue，用 `scripts/process_note_issue.py` 把多個單字拆成多筆（去重），各自先標記 `enriched: false`（意思等欄位先留空）
4. 接著 `scripts/enrich_notes.py` 嘗試用 Gemini 把每筆補齊成跟單字庫一樣的完整欄位（詞性/意思/例句/難度/主題/字根/相似字/反義字），補成功就標記 `enriched: true`
5. 結果 commit（同步 `docs/notes.json`），在 issue 上留言並自動關閉
6. 網頁重新整理後，「個人紀錄」分頁能看到紀錄（還沒補完的顯示「⏳ 資訊補充中」）；「隨機複習」的「整個單字庫」模式也會把個人紀錄納入抽樣

**補充失敗時的備援**：這專案的 Gemini 常回 429，補不出來的字會維持「待補充」，`enrich_notes.py` 在每天的排程裡會自動重試（`daily.yml` 有一步專門重試待補充的字）。若長期補不動，可以直接請 Claude 在對話裡批次補——讀 `notes.json`、填好未補的字、`enriched` 設成 `true`、寫回 `notes.json` 與 `docs/notes.json` 再 commit（跟當初建 3135 字單字庫同一套做法，可靠且免費）。

**依來源檢視 / 聽力複習**：個人紀錄分頁有「依單字 / 依來源」切換，「依來源」會把單字按來源影片/Podcast 分組，每個來源顯示你從它記過哪些字 + 一個「🎧 回去重聽」連結。每天的 LINE 推播也會在 5 個新單字之後，**輪流附上一個你以前記過字的舊來源連結**提醒你回去重聽，多練聽力。

> 個人紀錄會出現在網頁的隨機複習與每日 LINE 的聽力複習提醒，但**單字本身不會被排進每天 LINE 推播的 5 字關聯聚類**——那個聚類需要靠整個單字庫的 theme/root 標籤去湊關聯組，跟個人紀錄的性質不同。如果之後想讓個人紀錄的單字也能被排進每日推播，可以再擴充。

`.github/ISSUE_TEMPLATE/vocab-note.yml` 定義了表單欄位順序（單字 → 意思 → 來源類型 → 來源名稱 → 連結 → 備註），`scripts/process_note_issue.py` 是依照這個順序解析 issue 內容，**如果之後要調整表單欄位，兩邊要一起改**，不然解析會錯位。

## 抽字邏輯

`push.py` 每次執行時：

1. 依 `--lang` 讀取 `data/{lang}/words.json` 與 `data/history.json`，從 history 篩出**該語言**已推播過的集合
   （英文比對 `word`，越南文比對 `id`；各語言進度互不影響）
2. 決定這次的**關聯模式**：
   - 英文：`theme`（主題）→ `root`（字根字首字尾）→ `synonym`（相似字）→ `antonym`（反義字），依推播組數輪替
   - 越南文：標籤只有 `topic`，統一依主題分組，不做輪替
3. 從單字庫挑一個「種子字」，找出跟它同組、且尚未推播過的字，湊成 5 個一組（不夠 5 個時用其他組的字補滿）
4. 單字庫用完時：英文會**呼叫 Gemini** 即時生成一組備援；越南文則直接重新循環（`source` 標成 `bank-recycled`）
5. 把這一組 5 個字 append 進 `data/history.json`（同一次推播共用同一個 `pushed_at` / `cluster_mode` / `cluster_key`），同步一份到 `docs/history.json` 並 commit
6. 交給 `formatters.format_message(lang, items, meta)` 排版，再用 `LINE_CHANNEL_ID` + `LINE_CHANNEL_SECRET` 換一個短期 access token 推播
   （若未設定 LINE 金鑰，僅在本機印出結果方便測試）

加上 `--dry-run` 時，流程走到第 5 步之前就停住並印出排版結果：不寫任何檔案、不讀 LINE 金鑰、不呼叫發送函式。

> **已知取捨**：history 是**先寫入再推播**。若 LINE 發送失敗，那 5 個字仍會被記為已推播。這是為了避免推播成功但寫檔失敗時重複推同一組字。

## 待辦檢查點

- [x] 四組金鑰申請完成、存入 Secrets
- [x] 本機執行 `python push.py` 能正確印出/推播今日單字
- [x] GitHub Actions 手動觸發成功，且 `data/history.json`（含 `docs/history.json`）有被 commit 回 repo
- [x] GitHub Pages 網頁上線可回顧
- [ ] 觀察排程是否穩定準時自動觸發（cron 已從整點改到 00:17 UTC，持續觀察中）
- [ ] 越南文單字庫擴充到 50 筆以上（目前 10 筆，第 3 天起會開始重複）
- [ ] 手動觸發 `daily-vi.yml` 確認越南文推播能實際送達 LINE
- [ ] 回顧網頁加語言切換（目前越南文紀錄會跟英文混在同一個列表）
