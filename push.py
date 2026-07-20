"""每日單字推播主程式（多語言）。

用 --lang 決定推哪一種語言，預設 en：

    python push.py            # 等同 --lang en
    python push.py --lang vi

流程：
1. 讀 data/{lang}/words.json（單字庫）與 data/history.json（推播紀錄，靠 lang 欄位區分語言）
2. 決定這次的「關聯模式」；英文是主題 / 字根字首 / 相似字 / 反義字四種輪替，
   越南文標籤較少，統一依 topic 分組
3. 依模式挑出 5 個彼此相關、且該語言尚未推播過的字組成一組
4. 單字庫用完時：英文退回呼叫 Gemini 生成（極少數情況）；越南文則重新循環
5. append 5 筆進 data/history.json（每筆都帶 lang）
6. 用 LINE_CHANNEL_ID + LINE_CHANNEL_SECRET 換一個短期 access token，
   把 5 個字交給 formatters.format_message 排版後推播到 LINE
   （若未設定 LINE 金鑰，僅在本機印出結果方便測試）
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from formatters import format_message

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
HISTORY_PATH = DATA_DIR / "history.json"
DOCS_HISTORY_PATH = BASE_DIR / "docs" / "history.json"
NOTES_PATH = BASE_DIR / "notes.json"

SUPPORTED_LANGS = ["en", "vi"]


def words_path(lang: str) -> Path:
    return DATA_DIR / lang / "words.json"


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# LINE 相關的環境變數刻意不在這裡讀，改在 get_line_access_token() / push_line() 內部讀。
# 這樣 --dry-run 這種「只排版不發送」的路徑，結構上就不會碰到任何金鑰。

# GitHub Actions 會帶 github.event_name（schedule / workflow_dispatch）進來。
# 手動觸發（workflow_dispatch）視為「使用者想加推一組」，略過「一天一次」的防重複保護；
# 排程觸發（schedule）維持保證一天一次、不重複。本機執行沒帶這個變數時當作排程。
PUSH_TRIGGER = os.environ.get("PUSH_TRIGGER", "").strip()
IS_MANUAL_PUSH = PUSH_TRIGGER == "workflow_dispatch"
TRIGGER_LABEL = "manual" if IS_MANUAL_PUSH else ("schedule" if PUSH_TRIGGER == "schedule" else "local")

GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)
LINE_TOKEN_URL = "https://api.line.me/v2/oauth/accessToken"

REQUIRED_KEYS = {"word", "pos", "meaning", "example"}
CLUSTER_SIZE = 5
CLUSTER_MODES = ["theme", "root", "synonym", "antonym"]
# 越南文的標籤只有 topic，沒有字根/相似字/反義字，所以不做模式輪替
VI_CLUSTER_MODES = ["topic"]


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


def now_taiwan_iso() -> str:
    """這次推播的時間戳（台灣時間），同一次推播的 5 個字共用，用來分辨同一天的不同組推播。

    帶到微秒，確保同一秒內的連續推播也有唯一的 pushed_at（否則會被誤當成同一組、
    模式輪替也會算錯）。網頁顯示時只取到分鐘即可。
    """
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S.%f")


def push_instance_count(history: list[dict]) -> int:
    """歷史上總共推播過幾「組」。

    新資料每筆有 pushed_at（同一組共用），舊資料沒有就用 date 當代表（過去是一天一組）。
    用來讓關聯模式「每推一組就輪替」，而不是「每天才輪替」。
    """
    return len({h.get("pushed_at") or h["date"] for h in history})


def norm(w: str) -> str:
    return w.strip().lower()


def entries_for_lang(history: list[dict], lang: str) -> list[dict]:
    """只取該語言的推播紀錄。

    早期資料（多語言化之前）沒有 lang 欄位，一律視為英文。
    """
    return [h for h in history if h.get("lang", "en") == lang]


def history_key(entry: dict, lang: str) -> str | None:
    """紀錄在「推過沒」比對時的識別值。

    英文單字庫沒有 id，從一開始就是拿單字本身比對，沿用；
    越南文每筆都有 id，用 id 比對（同一個字可能有不同語境的多筆）。
    """
    if lang == "vi":
        return entry.get("id")
    word = entry.get("word")
    return norm(word) if word else None


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
    # 依「已推播組數」輪替，這樣同一天多推幾組也會換不同關聯模式
    return CLUSTER_MODES[push_instance_count(history) % len(CLUSTER_MODES)]


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
# 越南文挑選（標籤只有 topic，不做模式輪替）
# ---------------------------------------------------------------------------


def fill_cluster_vi(cluster: list[dict], available: list[dict], prefer_topic: str | None) -> list[dict]:
    have = {w["id"] for w in cluster}
    pool = [w for w in available if w["id"] not in have]
    prefer_key = theme_key(prefer_topic)
    if prefer_key:
        pool.sort(key=lambda w: 0 if theme_key(w.get("topic")) == prefer_key else 1)
    for w in pool:
        if len(cluster) >= CLUSTER_SIZE:
            break
        cluster.append(w)
    return cluster


def pick_cluster_vi(words: list[dict], used_keys: set[str]):
    """挑一組同 topic 的越南文，湊不滿 5 個就用其他 topic 補齊。"""
    available = [w for w in words if w["id"] not in used_keys]
    if not available:
        return None, (None, None)

    shuffled = available[:]
    random.shuffle(shuffled)

    for seed in shuffled:
        key = theme_key(seed.get("topic"))
        if not key:
            continue
        group = [w for w in available if theme_key(w.get("topic")) == key]
        if group:
            cluster = fill_cluster_vi(group[:CLUSTER_SIZE], available, seed.get("topic"))
            return cluster, ("topic", seed.get("topic"))

    seed = shuffled[0]
    cluster = fill_cluster_vi([seed], available, seed.get("topic"))
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
    channel_id = os.environ.get("LINE_CHANNEL_ID")
    channel_secret = os.environ.get("LINE_CHANNEL_SECRET")
    if not channel_id or not channel_secret:
        return None

    try:
        resp = requests.post(
            LINE_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": channel_id,
                "client_secret": channel_secret,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 換取 LINE access token 失敗: {e}")
        return None


def make_history_entry(item: dict, lang: str, base: dict, tail: dict) -> dict:
    """把單字庫項目轉成一筆 history 紀錄（base 在前、tail 在後，維持既有欄位順序）。

    回顧網頁（docs/index.html）是靠 word / pos / meaning / example 四個欄位渲染卡片的，
    所以越南文也要填這四個欄位（用 text / type / meaning_zh / example 對應），
    否則新推的越南文在網頁上會變成空白卡。拼音等越南文專屬欄位另外附在後面。
    """
    if lang == "vi":
        return {
            **base,
            "id": item["id"],
            "word": item["text"],
            "pos": item.get("type", ""),
            "meaning": item["meaning_zh"],
            "example": item["example"],
            **tail,
            "romanization": item.get("romanization", ""),
            "example_rom": item.get("example_rom", ""),
            "example_zh": item.get("example_zh", ""),
            "grammar_point": item.get("grammar_point", ""),
        }
    return {
        **base,
        "word": item["word"],
        "pos": item["pos"],
        "meaning": item["meaning"],
        "example": item["example"],
        **tail,
    }


def pick_listening_reminder(history: list[dict]):
    """從個人紀錄裡挑一個「有連結的來源」提醒回去重聽，每天輪流換一個。

    以「不重複的來源」為單位（同一支影片記了很多字算一個），依推播天數輪替，
    這樣每天提醒不同的舊來源，做聽力複習。沒有任何帶連結的個人紀錄時回傳 None。
    """
    notes = load_json(NOTES_PATH, [])
    sources = {}  # link -> {name, count}
    for n in notes:
        link = (n.get("link") or "").strip()
        if not link:
            continue
        entry = sources.setdefault(link, {"name": n.get("source_name") or "", "count": 0})
        entry["count"] += 1

    if not sources:
        return None

    ordered = sorted(sources.items(), key=lambda kv: kv[0])
    day_count = len({h["date"] for h in history})
    link, info = ordered[day_count % len(ordered)]
    return {"link": link, "name": info["name"], "count": info["count"]}


def append_listening_reminder(message: str, reminder: dict | None) -> str:
    if not reminder:
        return message
    name = reminder["name"] or "之前記過單字的影片"
    return (
        message
        + "\n\n🎧 聽力複習：回去聽聽\n"
        + f"{name}（你從這裡記過 {reminder['count']} 個字）\n"
        + reminder["link"]
    )


def push_line(message: str) -> None:
    line_user_id = os.environ.get("LINE_USER_ID")
    if not line_user_id:
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
        json={"to": line_user_id, "messages": [{"type": "text", "text": message}]},
        timeout=15,
    )
    resp.raise_for_status()
    print("[info] LINE 推播成功")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="每日單字 LINE 推播（多語言）")
    parser.add_argument(
        "--lang",
        choices=SUPPORTED_LANGS,
        default="en",
        help="要推播的語言（預設 en）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只印出排版後的推播內容，不寫入 history、不發送 LINE",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    lang = args.lang

    words = load_json(words_path(lang), [])
    if not words:
        rel = words_path(lang).relative_to(BASE_DIR)
        print(f"[error] {rel} 不存在或是空的，請先建立 {lang} 的單字庫。")
        sys.exit(1)

    history = load_json(HISTORY_PATH, [])
    # 各語言各自算「推過沒」與模式輪替，推了英文不會影響越南文的進度
    lang_history = entries_for_lang(history, lang)
    used_keys = {k for k in (history_key(h, lang) for h in lang_history) if k}

    date_str = today_taiwan()
    # 排程觸發：保證一天一次，若今天該語言已經有「排程推播」就略過
    #（避免 cron 偶發重複觸發時重複推）。
    # 手動觸發（workflow_dispatch）：使用者主動加推，不受此限，每次都會推一組新的字。
    if not IS_MANUAL_PUSH:
        scheduled_today = any(
            h["date"] == date_str and h.get("trigger", "schedule") == "schedule"
            for h in lang_history
        )
        if scheduled_today:
            print(f"[info] {date_str} 今日 {lang} 排程推播已完成，略過重複執行。")
            return

    source = "bank"

    if lang == "vi":
        cluster, (cluster_mode, cluster_key) = pick_cluster_vi(words, used_keys)
        if not cluster:
            # 越南文單字庫小，用完就從頭再循環一輪（不呼叫 Gemini）
            print("[info] 越南文單字庫已整輪推播過，重新循環。")
            cluster, (cluster_mode, cluster_key) = pick_cluster_vi(words, set())
            source = "bank-recycled"
    else:
        mode = determine_mode(lang_history)
        cluster, (cluster_mode, cluster_key) = pick_cluster(words, used_keys, mode)

        if not cluster or len(cluster) < CLUSTER_SIZE:
            gemini_result = generate_cluster_with_gemini(used_keys)
            if gemini_result:
                cluster, (cluster_mode, cluster_key) = gemini_result
                source = "gemini"

    if not cluster:
        print("[error] 單字庫已用完且 Gemini 生成失敗，請補充 data/en/words.json 或檢查 API 金鑰。")
        sys.exit(1)

    pushed_at = now_taiwan_iso()
    base = {
        "date": date_str,
        "pushed_at": pushed_at,
        "trigger": TRIGGER_LABEL,
        "lang": lang,
    }
    tail = {
        "source": source,
        "cluster_mode": cluster_mode,
        "cluster_key": cluster_key,
    }
    new_entries = [make_history_entry(w, lang, base, tail) for w in cluster]

    words_summary = "、".join(w["text"] if lang == "vi" else w["word"] for w in cluster)
    action = "選出（dry-run）" if args.dry_run else "推播"
    print(
        f"[info] {action} {lang} 單字組（來源: {source}, 觸發: {TRIGGER_LABEL}, "
        f"模式: {cluster_mode}/{cluster_key}）: {words_summary}"
    )

    message = format_message(lang, cluster, {"cluster_mode": cluster_mode, "cluster_key": cluster_key})
    if lang == "en":
        # 聽力複習提醒來自英文的個人單字紀錄（notes.json），只在英文推播帶上。
        # 它的輪替是看「含這次在內」的推播天數，所以要用 history + new_entries 算，
        # dry-run 才會印出跟實際推播一字不差的內容。
        message = append_listening_reminder(
            message, pick_listening_reminder(entries_for_lang(history + new_entries, lang))
        )

    if args.dry_run:
        print("[dry-run] 以下為排版結果，不會寫入 history，也不會發送 LINE：")
        print("-" * 50)
        print(message)
        print("-" * 50)
        return

    history.extend(new_entries)
    save_json(HISTORY_PATH, history)
    save_json(DOCS_HISTORY_PATH, history)  # docs/ 是 GitHub Pages 實際發布的內容，需同步一份

    push_line(message)


if __name__ == "__main__":
    main()
