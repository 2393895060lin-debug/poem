from __future__ import annotations

import html
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "textbook_source_registry.json"
KNOWLEDGE_BASE_PATH = ROOT / "textbook_knowledge_base.json"


def fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 Codex Textbook Sync"})
    with urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", "ignore")


def clean_html_fragment(fragment: str) -> list[str]:
    text = fragment
    text = re.sub(r"<br ?/?>", "\n", text)
    text = re.sub(r"</p>\s*<p[^>]*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    lines = []
    for raw in text.splitlines():
        cleaned = raw.replace("\u3000", " ").strip()
        cleaned = re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩]\s*", "", cleaned)
        cleaned = re.sub(r"^\d+[.、]\s*", "", cleaned)
        if cleaned:
            lines.append(cleaned)
    return lines


def extract_section(html_text: str, headings: list[str]) -> list[str]:
    start = -1
    marker = ""
    for heading in headings:
        candidate = html_text.find(heading)
        if candidate != -1 and (start == -1 or candidate < start):
            start = candidate
            marker = heading

    if start == -1:
        return []

    paragraph_start = html_text.rfind("<p", 0, start)
    if paragraph_start == -1:
        paragraph_start = start

    next_heading = len(html_text)
    for pattern in ["<p><strong>", "<strong>赏析", "<strong>创作背景", "<div class=\"tool\">", "</div>\n</div>"]:
        candidate = html_text.find(pattern, start + len(marker))
        if candidate != -1:
            next_heading = min(next_heading, candidate)

    block = html_text[paragraph_start:next_heading]
    for heading in headings:
        block = block.replace(heading, "")
    return clean_html_fragment(block)


def normalize_translation(lines: list[str]) -> list[str]:
    normalized = []
    for line in lines:
        if line in {"译文", "译文及注释", "注释", "注解"}:
            continue
        if line in {"特点", "创作背景", "赏析"}:
            break
        if any(marker in line for marker in ["文章托物言志", "最突出的艺术手法", "写作背景", "作者简介"]):
            break
        normalized.append(line)
    return normalized


def normalize_notes(lines: list[str]) -> list[dict]:
    notes: list[dict] = []
    for line in lines:
        if line in {"注释", "注解", "译文及注释", "译文"}:
            continue
        if "：" in line:
            term, text = line.split("：", 1)
        elif ":" in line:
            term, text = line.split(":", 1)
        else:
            term, text = "", line
        term = term.strip(" []【】()（）")
        text = text.strip()
        if not term and text and notes:
            notes[-1]["text"] = f'{notes[-1]["text"]}{text}'
            continue
        if term or text:
            notes.append({"term": term, "text": text})
    return notes


def extract_translation_and_notes(url: str) -> tuple[list[str], list[dict]]:
    html_text = fetch_text(url)
    translation_lines = extract_section(
        html_text,
        [
            "<strong>译文及注释<br /></strong>",
            "<strong>译文及注释<br/></strong>",
            "<strong>译文<br /></strong>",
            "<strong>译文<br/></strong>",
            "<strong>译文</strong><br />",
            "<strong>译文</strong><br/>"
        ],
    )
    note_lines = extract_section(
        html_text,
        [
            "<strong>注释<br /></strong>",
            "<strong>注释<br/></strong>",
            "<strong>注解<br /></strong>",
            "<strong>注解<br/></strong>",
            "<strong>注释</strong><br />",
            "<strong>注释</strong><br/>",
            "<strong>注解</strong><br />",
            "<strong>注解</strong><br/>"
        ],
    )
    return normalize_translation(translation_lines), normalize_notes(note_lines)


def load_json(path: Path) -> dict:
    if not path.exists():
        return {"works": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    registry = load_json(REGISTRY_PATH)
    kb = load_json(KNOWLEDGE_BASE_PATH)
    works = kb.setdefault("works", {})

    updated = []
    for item in registry.get("works", []):
        title = str(item.get("title", "")).strip()
        author = str(item.get("author", "")).strip()
        url = str(item.get("source_url", "")).strip()
        if not title or not url:
            continue

        translation, notes = extract_translation_and_notes(url)
        entry = works.setdefault(title, {})
        entry.setdefault("aliases", [])
        if author:
            entry["author"] = author
        if translation:
            entry["translation"] = translation
        if notes:
            entry["notes"] = notes
        updated.append((title, len(translation), len(notes)))

    KNOWLEDGE_BASE_PATH.write_text(json.dumps(kb, ensure_ascii=False, indent=2), encoding="utf-8")

    for title, translation_count, note_count in updated:
        print(f"{title}: translation={translation_count}, notes={note_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
