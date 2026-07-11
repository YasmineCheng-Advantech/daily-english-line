"""每日商用英文單字推播主程式。

流程：
1. 讀 words.json（單字庫）與 history.json（推播紀錄）
2. 優先呼叫 Gemini 即時生成一個「未推播過」的中高階商用英文新字
3. 若 Gemini 失敗（無金鑰、額度用盡、格式錯誤等），退回從 words.json 抽一個未推播過的字
4. append 進 history.json
5. 呼叫 LINE Messaging API 推播（若未設定 LINE 金鑰，僅在本機印出結果，方便測試）
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

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
LINE_CHANNEL_ID = os.environ.get("LINE_CHANNEL_ID")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
LINE_USER_ID = os.environ.get("LINE_USER_ID")

LINE_TOKEN_URL = "https://api.line.me/v2/oauth/accessToken"

GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)

REQUIRED_KEYS = {"word", "pos", "meaning", "example"}


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


def generate_word_with_gemini(used_words: set[str]):
    if not GEMINI_API_KEY:
        return None

    prompt = (
        "你是商用英文教材編輯。請生成一個「中高階」程度的商用英文單字或片語"
        "（不要過於基礎，例如不要 meeting、email 這類簡單字），"
        "且不可以是以下已經使用過的單字："
        + ", ".join(sorted(used_words))
        + "。"
        "只回傳一個 JSON 物件，不要加任何說明文字或 markdown 標記，格式為："
        '{"word": "英文單字", "pos": "詞性縮寫，如 n./v./adj./adv./phr.", '
        '"meaning": "繁體中文意思（簡短）", "example": "一句英文商用情境例句"}'
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

        word_entry = json.loads(text)

        if not REQUIRED_KEYS.issubset(word_entry.keys()):
            print(f"[warn] Gemini 回傳缺少必要欄位: {word_entry}")
            return None

        if word_entry["word"].strip().lower() in used_words:
            print(f"[warn] Gemini 生成了重複單字: {word_entry['word']}")
            return None

        return word_entry
    except Exception as e:  # noqa: BLE001 - 任何失敗都應該安全退回單字庫
        print(f"[warn] Gemini 生成失敗，改用單字庫: {e}")
        return None


def pick_from_bank(words: list[dict], used_words: set[str]):
    candidates = [w for w in words if w["word"].strip().lower() not in used_words]
    if not candidates:
        return None
    return random.choice(candidates)


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


def push_line(word_entry: dict) -> None:
    if not LINE_USER_ID:
        print("[info] 尚未設定 LINE_USER_ID，略過推播（本機測試模式）")
        return

    access_token = get_line_access_token()
    if not access_token:
        print("[info] 尚未設定 LINE 金鑰或換取 token 失敗，略過推播（本機測試模式）")
        return

    message = (
        "📘 今日商用英文單字\n\n"
        f"{word_entry['word']} ({word_entry['pos']})\n"
        f"意思：{word_entry['meaning']}\n"
        f"例句：{word_entry['example']}"
    )

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


def main() -> None:
    words = load_json(WORDS_PATH, [])
    history = load_json(HISTORY_PATH, [])
    used_words = {h["word"].strip().lower() for h in history}

    date_str = today_taiwan()
    if any(h["date"] == date_str for h in history):
        print(f"[info] {date_str} 已經推播過，略過重複執行。")
        return

    word_entry = generate_word_with_gemini(used_words)
    source = "gemini"

    if word_entry is None:
        word_entry = pick_from_bank(words, used_words)
        source = "bank"

    if word_entry is None:
        print("[error] 單字庫已用完且 Gemini 生成失敗，請補充 words.json 或檢查 API 金鑰。")
        sys.exit(1)

    history.append(
        {
            "date": date_str,
            "word": word_entry["word"],
            "pos": word_entry["pos"],
            "meaning": word_entry["meaning"],
            "example": word_entry["example"],
            "source": source,
        }
    )
    save_json(HISTORY_PATH, history)

    print(f"[info] 今日單字（來源: {source}）: {word_entry['word']} - {word_entry['meaning']}")
    push_line(word_entry)


if __name__ == "__main__":
    main()
