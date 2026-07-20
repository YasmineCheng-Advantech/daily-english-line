"""各語言的推播訊息排版。

push.py 只負責挑字與寫紀錄，「長什麼樣子」全部集中在這裡，
之後要加泰文等新語言，只要在 FORMATTERS 註冊一個新的 formatter 就好。

對外只有一個進入點：

    format_message(lang, items, meta) -> str

- `lang`  語言碼（"en" / "vi"）
- `items` 這次要推的一組單字（list[dict]，元素就是 data/{lang}/words.json 裡的原始物件）
- `meta`  這組的關聯資訊，目前有 {"cluster_mode": str, "cluster_key": str | None}
"""

MODE_LABELS_EN = {
    "theme": "主題",
    "root": "字根字首字尾",
    "synonym": "相似字",
    "antonym": "反義字",
    "random": "精選",
}

MODE_LABELS_VI = {
    "topic": "主題",
    "random": "精選",
}


def format_message_en(items: list[dict], meta: dict) -> str:
    label = MODE_LABELS_EN.get(meta.get("cluster_mode"), "精選")
    key = meta.get("cluster_key")

    header = f"📘 今日 {len(items)} 個商用英文單字（關聯：{label}"
    header += f" - {key}）" if key else "）"

    lines = [header, ""]
    for i, w in enumerate(items, start=1):
        lines.append(f"{i}. {w['word']} ({w['pos']})")
        lines.append(f"   意思：{w['meaning']}")
        lines.append(f"   例句：{w['example']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_message_vi(items: list[dict], meta: dict) -> str:
    """越南文排版：比英文多一行羅馬拼音，例句附拼音與中文，最後帶文法點。

    越南文的難處在「看得懂字也唸不出來」，所以拼音跟聲調提醒要放在顯眼位置。
    """
    label = MODE_LABELS_VI.get(meta.get("cluster_mode"), "精選")
    key = meta.get("cluster_key")

    header = f"🇻🇳 今日 {len(items)} 個越南文（{label}"
    header += f"：{key}）" if key else "）"

    lines = [header, ""]
    for i, w in enumerate(items, start=1):
        lines.append(f"{i}. {w['text']}")
        lines.append(f"   唸法：{w['romanization']}")
        lines.append(f"   意思：{w['meaning_zh']}")
        if w.get("tone_note"):
            lines.append(f"   發音提醒：{w['tone_note']}")
        lines.append(f"   例句：{w['example']}")
        if w.get("example_rom"):
            lines.append(f"         （{w['example_rom']}）")
        lines.append(f"         {w['example_zh']}")
        if w.get("grammar_point"):
            lines.append(f"   文法：{w['grammar_point']}")
        lines.append("")
    return "\n".join(lines).rstrip()


FORMATTERS = {
    "en": format_message_en,
    "vi": format_message_vi,
}


def format_message(lang: str, items: list[dict], meta: dict | None = None) -> str:
    formatter = FORMATTERS.get(lang)
    if formatter is None:
        raise ValueError(f"沒有對應 {lang} 的排版器，請在 formatters.FORMATTERS 註冊")
    return formatter(items, meta or {})
