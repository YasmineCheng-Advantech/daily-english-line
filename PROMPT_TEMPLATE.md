# 英文單字生成 Prompt 範本

> 越南文的版本請看 `PROMPT_TEMPLATE_VI.md`。

拿去貼給任何 LLM（ChatGPT、Gemini、Claude.ai 等）都可以，請它輸出 JSON，存成一個新檔案（例如 `new_batch.json`），再用 `scripts/merge_words.py` 合併進 `data/en/words.json`。

不需要在 prompt 裡貼你現有的 3000 多字清單當排除名單——重複的字交給 `merge_words.py` 自動比對現有單字庫過濾掉即可，省事也不會受限於 LLM 的 context 長度。

---

## Prompt 內容（複製貼上，`{N}` 和 `{THEMES}` 換成你要的數量與主題）

```
請生成 {N} 個「中階到中高階」程度的商用英文單字/片語，主題涵蓋：{THEMES}
（例如：negotiation, finance, marketing... 或直接說「不限主題，涵蓋各種商用情境」）

避免過於基礎的字（不要 meeting、email、boss、job、money、price 這類）。

輸出一個 JSON 陣列，每個物件必須恰好包含這 9 個欄位
（不要自己加 "lang" 欄位，合併腳本會自動補上）：

- "word": 英文單字或片語（小寫，除非本來就需要大寫）
- "pos": 詞性縮寫，如 "n." "v." "adj." "adv." "phr."
- "meaning": 繁體中文意思，簡短（20 字以內）
- "example": 一句英文商用情境例句
- "level": "中階" 或 "中高階"
- "theme": 主題清單是開放式的，優先從這份清單選最貼切的（沿用現有主題，同一個概念不要一直發明新 slug）；如果都不合適，可以新增新的英文 slug（小寫、底線分隔，例如 `semiconductor`）：
negotiation, contracts_legal, finance, accounting, marketing, sales, management, leadership, hr, customer_service, operations, supply_chain, project_management, technology_it, strategy, compliance_risk, economics, trade, communication, presentations, semiconductor, tech_industry, creative, media

- "root": 如果這個字真的包含某個字根/字首/字尾（真的有語源關係，不要硬湊），格式固定寫成 `"詞綴 (中文解釋)"`，例如 `"-ary (性質的)"`；沒有明顯字根就設為 JSON null。
  常用字根優先從這份清單選（清單外的詞綴也可以用，只要格式一致就好，例如又遇到 "-ary" 的字，中文解釋盡量維持同一種寫法，這樣同字根的字才湊得成一組）：
"co-/con- (共同)", "counter- (相反/反制)", "over- (過度)", "under- (不足)", "re- (再次)", "de- (去除/相反)", "dis- (不/相反)", "sub- (次要/下)", "inter- (之間/相互)", "trans- (轉移/跨越)", "multi- (多)", "mono-/uni- (單一)", "pre- (事前)", "post- (事後)", "pro- (支持/向前)", "auto- (自動)", "-ize/-ise (使成為)", "-tion/-sion (名詞化:動作結果)", "-ment (名詞化:狀態結果)", "-able/-ible (可…的)", "-ship (身分狀態)", "-ance/-ence (性質狀態)"

- "synonyms": 1-3 個自然的英文同義字/片語組成的陣列（純字串，不需要保證在這批資料裡也找得到）。沒有的話給空陣列 []
- "antonyms": 0-2 個自然的英文反義字/片語組成的陣列。沒有自然反義字就給空陣列 []

請確保：
1. 這批資料裡面沒有重複的 "word"
2. 每個物件都恰好有這 9 個 key，不多不少
3. 直接輸出純 JSON 陣列，不要加任何說明文字或 markdown 的 ``` 標記
```

---

## 拿到結果之後

1. 把 LLM 回傳的 JSON 存成檔案，例如 `new_batch.json`（放在 repo 根目錄或任意路徑都可以）
2. 執行：
   ```bash
   python3 scripts/merge_words.py new_batch.json
   ```
   （`--lang` 預設就是 `en`，英文不用特別指定）
3. 腳本會自動：
   - 驗證格式（9 個 key、level 是否合法、theme/root 是否為非空字串）
   - 跟現有 `data/en/words.json` 比對，過濾掉重複的字（不分大小寫）
   - 補上 `"lang": "en"` 欄位
   - 印出「新增幾個、跳過幾個重複、跳過幾個格式錯誤」的統計
   - 把結果寫回 `data/en/words.json`，並同步一份到 `docs/words.json`（網頁用）

   `theme` 和 `root` 都是開放式清單——新主題、新字根都會直接被記錄下來，`push.py` 聚類時會正規化大小寫/空白/連字號差異（見 `theme_key()` / `root_key()`），所以同一個主題或字根即使不同批次寫法略有出入，累積到 2 個以上還是湊得起來。
4. 檢查一下統計數字合理後，先用 `python3 push.py --lang en --dry-run` 預覽排版，
   確認沒問題再 `git add data/en/words.json docs/words.json && git commit -m "..." && git push`

如果一次生成的量很大（例如你想要一次上千字），可以分成好幾個小檔案分次丟給腳本合併，或是把這個 prompt 拆成好幾次、每次指定不同主題子集，效果會比一次要求 LLM 生成太多字時品質更穩定（LLM 一次生成上百字容易開始重複或亂湊字根）。建議一次抓 100-300 字左右品質最穩定。
