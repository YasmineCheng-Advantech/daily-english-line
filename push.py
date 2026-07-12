"""每日商用英文單字推播主程式。

流程：
1. 讀 words.json（單字庫，含 theme/root/synonyms/antonyms 標籤）與 history.json（推播紀錄）
2. 決定今天的「關聯模式」（主題 / 字根字首 / 相似字 / 反義字，四種輪替）
3. 依模式從單字庫挑出 5 個彼此相關、且尚未推播過的字組成一組
4. 若單字庫可用字不足 5 個，退回呼叫 Gemini 生成一組新字（極少數情況才會發生）
5. append 5 筆進 history.json
6. 用 LINE_CHANNEL_ID + LINE_CHANNEL_SECRET 換一個短期 access token，
   把 5 個字合併成一則訊息推播到 LINE（若未設定 LINE 金鑰，僅在本機印出結果方便測試）
"""

import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
WORDS_PATH = BASE_DIR / "words.json"
HISTORY_PATH = BASE_DIR / "history.json"
DOCS_HISTORY_PATH = BASE_DIR / "docs" / "history.json"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
LINE_CHANNEL_ID = os.environ.get("LINE_CHANNEL_ID")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
LINE_USER_ID = os.environ.get("LINE_USER_ID")

GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)
LINE_TOKEN_URL = "https://api.line.me/v2/oauth/accessToken"

REQUIRED_KEYS = {"word", "pos", "meaning", "example"}
CLUSTER_SIZE = 5
CLUSTER_MODES = ["theme", "root", "synonym", "antonym"]
MODE_LABELS = {
    "theme": "主題",
    "root": "字根字首字尾",
    "synonym": "相似字",
    "antonym": "反義字",
    "random": "精選",
}


def load_json(path: Path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def today_taiwan() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


def norm(w: str) -> str:
    return w.strip().lower()


def root_key(root: str | None) -> str | None:
    """字根標籤只比對詞綴本身（括號前的部分），忽略中文解釋文字的出入。

    例如 "-ary (性質)" 和 "-ary (與…有關)" 視為同一個字根，
    這樣即使不同批次生成時解釋寫法不一致，也還是能湊成同一組。
    """
    if not root:
        return None
    return root.split("(")[0].strip().lower()


def theme_key(theme: str | None) -> str | None:
    """主題標籤正規化：大小寫、空白、連字號的差異都視為同一個主題。

    主題清單是開放式的（不限定在 PROMPT_TEMPLATE.md 建議的清單裡），
    不同批次/不同 LLM 可能會用 "media" 或 "Media Industry" 這種寫法上的差異，
    正規化後才能穩定湊成同一組。
    """
    if not theme:
        return None
    return theme.strip().lower().replace("-", "_").replace(" ", "_")


# ---------------------------------------------------------------------------
# 單字庫聚類挑選
# ---------------------------------------------------------------------------


def determine_mode(history: list[dict]) -> str:
    day_count = len({h["date"] for h in history})
    return CLUSTER_MODES[day_count % len(CLUSTER_MODES)]


def fill_cluster(cluster: list[dict], available: list[dict], prefer_theme: str | None) -> list[dict]:
    have = {w["word"] for w in cluster}
    pool = [w for w in available if w["word"] not in have]
    prefer_key = theme_key(prefer_theme)
    if prefer_key:
        pool.sort(key=lambda w: 0 if theme_key(w.get("theme")) == prefer_key else 1)
    for w in pool:
        if len(cluster) >= CLUSTER_SIZE:
            break
        cluster.append(w)
    return cluster


def pick_cluster(words: list[dict], used_words: set[str], mode: str):
    index = {norm(w["word"]): w for w in words}
    available = [w for w in words if norm(w["word"]) not in used_words]
    if not available:
        return None, (None, None)

    shuffled = available[:]
    random.shuffle(shuffled)

    if mode == "theme":
        for seed in shuffled:
            key = theme_key(seed.get("theme"))
            if not key:
                continue
            group = [w for w in available if theme_key(w.get("theme")) == key]
            if group:
                cluster = fill_cluster(group[:CLUSTER_SIZE], available, seed.get("theme"))
                return cluster, ("theme", seed.get("theme"))

    elif mode == "root":
        for seed in shuffled:
            key = root_key(seed.get("root"))
            if not key:
                continue
            group = [w for w in available if root_key(w.get("root")) == key]
            if group:
                cluster = fill_cluster(group[:CLUSTER_SIZE], available, seed.get("theme"))
                return cluster, ("root", seed.get("root"))

    elif mode == "synonym":
        for seed in shuffled:
            related = [
                index[norm(s)]
                for s in seed.get("synonyms", [])
                if norm(s) in index and norm(s) not in used_words
            ]
            group = [seed] + [w for w in related if w["word"] != seed["word"]]
            if len(group) >= 2:
                cluster = fill_cluster(group[:CLUSTER_SIZE], available, seed.get("theme"))
                return cluster, ("synonym", seed["word"])

    elif mode == "antonym":
        for seed in shuffled:
            related = [
                index[norm(s)]
                for s in seed.get("antonyms", [])
                if norm(s) in index and norm(s) not in used_words
            ]
            group = [seed] + [w for w in related if w["word"] != seed["word"]]
            if len(group) >= 2:
                cluster = fill_cluster(group[:CLUSTER_SIZE], available, seed.get("theme"))
                return cluster, ("antonym", seed["word"])

    # 找不到符合當天模式的關聯組合（例如標籤資料不足），退回隨機挑選但仍優先同主題
    seed = shuffled[0]
    cluster = fill_cluster([seed], available, seed.get("theme"))
    return cluster, ("random", None)


# ---------------------------------------------------------------------------
# Gemini 備援（單字庫完全用完時才會觸發）
# ---------------------------------------------------------------------------


def generate_cluster_with_gemini(used_words: set[str]):
    if not GEMINI_API_KEY:
        return None

    prompt = (
        "你是商用英文教材編輯。請生成 5 個「中階到中高階」程度、彼此主題相關的商用英文單字或片語"
        "（不要過於基礎，例如不要 meeting、email 這類簡單字），"
        "且不可以是以下已經使用過的單字："
        + ", ".join(sorted(used_words))
        + "。"
        "只回傳一個 JSON 陣列，不要加任何說明文字或 markdown 標記，陣列中每個物件格式為："
        '{"word": "英文單字", "pos": "詞性縮寫，如 n./v./adj./adv./phr.", '
        '"meaning": "繁體中文意思（簡短）", "example": "一句英文商用情境例句", '
        '"theme": "這 5 個字共通的主題（英文 slug）"}'
    )

    try:
        resp = requests.post(
            GEMINI_URL,
            params={"key": GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()

        cluster = json.loads(text)
        cluster = [w for w in cluster if REQUIRED_KEYS.issubset(w.keys())]
        cluster = [w for w in cluster if norm(w["word"]) not in used_words]

        if not cluster:
            return None
        theme = cluster[0].get("theme")
        return cluster[:CLUSTER_SIZE], ("theme", theme)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] Gemini 生成失敗: {e}")
        return None


# ---------------------------------------------------------------------------
# LINE 推播
# ---------------------------------------------------------------------------


def get_line_access_token() -> str | None:
    """用 Channel ID + Channel Secret 換一個短期（30 天）channel access token。

    比起在 LINE Developers Console 手動 Issue 長效 token，這個方式完全靠 API，
    每次執行都重新換發，永遠不會過期失效，也不用手動更新。
    """
    if not LINE_CHANNEL_ID or not LINE_CHANNEL_SECRET:
        return None

    try:
        resp = requests.post(
            LINE_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": LINE_CHANNEL_ID,
                "client_secret": LINE_CHANNEL_SECRET,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 換取 LINE access token 失敗: {e}")
        return None


def build_message(cluster: list[dict], mode: str, key: str | None) -> str:
    label = MODE_LABELS.get(mode, "精選")
    header = f"📘 今日 5 個商用英文單字（關聯：{label}"
    header += f" - {key}）" if key else "）"

    lines = [header, ""]
    for i, w in enumerate(cluster, start=1):
        lines.append(f"{i}. {w['word']} ({w['pos']})")
        lines.append(f"   意思：{w['meaning']}")
        lines.append(f"   例句：{w['example']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def push_line(message: str) -> None:
    if not LINE_USER_ID:
        print("[info] 尚未設定 LINE_USER_ID，略過推播（本機測試模式）")
        print(message)
        return

    access_token = get_line_access_token()
    if not access_token:
        print("[info] 尚未設定 LINE 金鑰或換取 token 失敗，略過推播（本機測試模式）")
        print(message)
        return

    resp = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
        json={"to": LINE_USER_ID, "messages": [{"type": "text", "text": message}]},
        timeout=15,
    )
    resp.raise_for_status()
    print("[info] LINE 推播成功")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main() -> None:
    words = load_json(WORDS_PATH, [])
    history = load_json(HISTORY_PATH, [])
    used_words = {norm(h["word"]) for h in history}

    date_str = today_taiwan()
    if any(h["date"] == date_str for h in history):
        print(f"[info] {date_str} 已經推播過，略過重複執行。")
        return

    mode = determine_mode(history)
    cluster, (cluster_mode, cluster_key) = pick_cluster(words, used_words, mode)
    source = "bank"

    if not cluster or len(cluster) < CLUSTER_SIZE:
        gemini_result = generate_cluster_with_gemini(used_words)
        if gemini_result:
            cluster, (cluster_mode, cluster_key) = gemini_result
            source = "gemini"

    if not cluster:
        print("[error] 單字庫已用完且 Gemini 生成失敗，請補充 words.json 或檢查 API 金鑰。")
        sys.exit(1)

    for w in cluster:
        history.append(
            {
                "date": date_str,
                "word": w["word"],
                "pos": w["pos"],
                "meaning": w["meaning"],
                "example": w["example"],
                "source": source,
                "cluster_mode": cluster_mode,
                "cluster_key": cluster_key,
            }
        )
    save_json(HISTORY_PATH, history)
    save_json(DOCS_HISTORY_PATH, history)  # docs/ 是 GitHub Pages 實際發布的內容，需同步一份

    words_summary = "、".join(w["word"] for w in cluster)
    print(f"[info] 今日單字組（來源: {source}, 模式: {cluster_mode}/{cluster_key}）: {words_summary}")

    message = build_message(cluster, cluster_mode, cluster_key)
    push_line(message)


if __name__ == "__main__":
    main()
