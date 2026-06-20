from __future__ import annotations

import importlib.util
import html
import json
import os
import re
import secrets
import sys
import threading
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Queue
from datetime import datetime
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

from pypinyin import Style, pinyin
from runtime_paths import (
    AUTO_SUPPLEMENT_CACHE_PATH,
    PROJECT_ROOT as ROOT,
    TEXT_CACHE_DIR,
    TRANSLATION_CACHE_DIR,
    ensure_runtime_dirs,
)

LOOKUP_SCRIPT_CANDIDATES = [
    ROOT / "lookup_classical_text.py",
    Path.home() / ".codex" / "skills" / "classical-text-lookup" / "scripts" / "lookup_classical_text.py",
]
KNOWLEDGE_BASE_PATH = ROOT / "textbook_knowledge_base.json"
GENERAL_ANNOTATION_BASE_PATH = ROOT / "general_annotation_base.json"
TEXTBOOK_SOURCE_REGISTRY_PATH = ROOT / "textbook_source_registry.json"

EXTERNAL_TRANSLATION_SOURCES = {
    ("满江红", "岳飞"): "https://www.gushiwen.cn/gushiwen_1095efc612.aspx",
}

DEFAULT_USER_AGENT = "Mozilla/5.0 Codex Poem Reader"
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
SYNC_ENRICH_TIMEOUT_SECONDS = 9.5
SYNC_ENRICH_REQUEST_TIMEOUT_SECONDS = 3.0
HUMAN_VERIFICATION_COOKIE = "poem_human_verified"
HUMAN_VERIFICATION_TTL_SECONDS = int(os.getenv("POEM_HUMAN_VERIFICATION_TTL_SECONDS", "21600"))
AUTHOR_FAME_SCORES = {
    "李白": 120,
    "杜甫": 118,
    "苏轼": 116,
    "辛弃疾": 112,
    "李清照": 110,
    "白居易": 105,
    "王维": 102,
    "王安石": 100,
    "陆游": 100,
    "孟浩然": 98,
    "李煜": 98,
    "后主煜": 98,
    "岳飞": 96,
    "杜牧": 95,
    "李商隐": 95,
    "欧阳修": 94,
    "柳永": 92,
    "陶渊明": 90,
    "范仲淹": 88,
    "刘禹锡": 88,
    "韩愈": 88,
    "王昌龄": 86,
    "岑参": 84,
    "高适": 82,
    "温庭筠": 80,
    "秦观": 80,
    "晏殊": 78,
    "晏几道": 76,
    "纳兰性德": 92,
}
POPULAR_WORK_SCORES = {
    ("春晓", "孟浩然"): 220,
    ("静夜思", "李白"): 220,
    ("满江红", "岳飞"): 200,
    ("如梦令", "李清照"): 180,
    ("忆江南", "白居易"): 160,
    ("江城子", "苏轼"): 150,
    ("浪淘沙", "李煜"): 145,
    ("鹊桥仙", "秦观"): 140,
    ("钗头凤", "陆游"): 135,
    ("卜算子", "李之仪"): 125,
    ("清平乐", "辛弃疾"): 125,
}
verified_human_tokens: dict[str, float] = {}
verified_human_tokens_lock = threading.Lock()


def prune_verified_human_tokens(now: float | None = None) -> None:
    current_time = now if now is not None else time.time()
    with verified_human_tokens_lock:
        expired_tokens = [token for token, expires_at in verified_human_tokens.items() if expires_at <= current_time]
        for token in expired_tokens:
            verified_human_tokens.pop(token, None)


def issue_human_verification_token() -> tuple[str, int]:
    now = time.time()
    prune_verified_human_tokens(now)
    expires_at = now + HUMAN_VERIFICATION_TTL_SECONDS
    token = secrets.token_urlsafe(24)
    with verified_human_tokens_lock:
        verified_human_tokens[token] = expires_at
    return token, HUMAN_VERIFICATION_TTL_SECONDS


def is_human_verified(cookie_header: str | None) -> bool:
    if not cookie_header:
        return False
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header)
    except Exception:
        return False
    morsel = cookie.get(HUMAN_VERIFICATION_COOKIE)
    if not morsel:
        return False
    token = morsel.value
    now = time.time()
    with verified_human_tokens_lock:
        expires_at = verified_human_tokens.get(token)
        if not expires_at:
            return False
        if expires_at <= now:
            verified_human_tokens.pop(token, None)
            return False
    return True

SUPPLEMENTS = {
    "岳阳楼记": {
        "translation": [
            "庆历四年春天，滕子京被贬到巴陵郡做太守。到了第二年，政事顺利，百姓和乐，许多荒废的事业都重新兴办起来，于是重修岳阳楼，扩充旧有规模，把唐代名家和当代人的诗赋刻在楼上，嘱托我写一篇文章来记述这件事。",
            "我看那巴陵郡的胜景，都集中在洞庭湖。它连接远山，吞纳长江，水势浩大，宽广无边，早晚阴晴变化万千，这就是岳阳楼的壮观景象，前人的描写已经很详尽了。",
            "在连月阴雨、阴风怒号时，人们登楼便会生出离京怀乡、担忧谗毁的悲伤；而在春和景明、皓月千里时，人们登楼又会感到心胸开阔、宠辱皆忘的喜悦。",
            "作者由景入情，最后提出古仁人应当不以外物和个人得失而悲喜，在朝忧民，在野忧君，以“先天下之忧而忧，后天下之乐而乐”收束全文。"
        ],
        "notes": [
            {"term": "谪守", "text": "因贬官而外任地方官。"},
            {"term": "百废具兴", "text": "许多已经荒废的事业都兴办起来。具，同“俱”。"},
            {"term": "胜状", "text": "胜景，好景象。"},
            {"term": "浩浩汤汤", "text": "水势浩大。汤汤，这里读 shāng shāng。"},
            {"term": "迁客骚人", "text": "被贬谪的官员和善于辞赋的文人。"},
            {"term": "不以物喜，不以己悲", "text": "不因为外物好坏和个人得失而或喜或悲。"},
            {"term": "微斯人，吾谁与归", "text": "如果没有这样的人，我同谁一道呢？"}
        ],
        "appreciation": [
            "这篇文章通过“悲景”与“喜景”的强烈对照，把作者的政治理想推向全文中心。它的名句之所以有力量，不仅因为判断铿锵，更因为前面已经积累了足够厚重的景与情。",
            "把古文拆成单字格并加上逐字拼音，会明显放大朗读节奏。这个界面因此既像阅读页面，又像诵读教具，适合课堂、打印和展示。"
        ],
        "recite": [
            "第一段：交代缘起。",
            "第二段：总写洞庭湖大观。",
            "第三段：霪雨霏霏，对应悲。",
            "第四段：春和景明，对应喜。",
            "第五段：升华主旨，重点背诵“先天下之忧而忧，后天下之乐而乐”。"
        ],
    },
    "桃花源记": {
        "translation": [
            "东晋太元年间，武陵有个渔人顺着溪水划船，忘记了路程远近。",
            "他忽然遇见一片桃花林，继续前行，发现山有小口，进入后豁然开朗，看见与外界隔绝而安乐自足的村落。",
            "村中人自称祖先为避秦乱来到这里，从此不再出去，因此不知汉魏晋。渔人离开后做了标记，再去寻找却迷失了。"
        ],
        "notes": [
            {"term": "缘溪行", "text": "沿着溪水前进。"},
            {"term": "落英缤纷", "text": "落花繁多的样子。"},
            {"term": "俨然", "text": "整齐的样子。"},
            {"term": "不足为外人道也", "text": "不值得对外面的人说。"}
        ],
        "appreciation": [
            "《桃花源记》把理想社会写得不靠口号，而是靠道路、房舍、耕作和人情去落地，所以后世读者会觉得这个世界既朴素又可信。"
        ],
        "recite": [
            "抓住三次转折：入林、入洞、出洞。",
            "重点句：阡陌交通，鸡犬相闻。",
            "结尾句：后遂无问津者。"
        ],
    },
    "陋室铭": {
        "translation": [
            "山不在于高，有仙人就出名；水不在于深，有龙就显灵。这是间简陋的屋子，只因为居住者品德高尚就显得香远益清。",
            "苔痕爬上台阶呈现绿意，草色映入帘内一片青翠。来往谈笑的都是博学之士，没有浅薄之人。",
            "可以弹奏素琴，浏览佛经，没有嘈杂音乐扰耳，也没有公文劳形。"
        ],
        "notes": [
            {"term": "馨", "text": "这里指品德高尚带来的芳香。"},
            {"term": "鸿儒", "text": "博学的人。"},
            {"term": "白丁", "text": "没有功名的人。"},
            {"term": "何陋之有", "text": "有什么简陋的呢。"}
        ],
        "appreciation": [
            "全文篇幅极短，却把环境、交游、情趣与精神格调都压缩进去，句式整齐，非常适合做格子排版和朗读展示。"
        ],
        "recite": [
            "开头两句类比起兴。",
            "中间三组对比突出陋室不陋。",
            "结尾借孔子语收束。"
        ],
    },
    "静夜思": {
        "translation": [
            "明亮的月光洒在床前，好像地上结了一层白霜。",
            "我抬头望着天上的明月，又低下头思念远方的故乡。"
        ],
        "notes": [
            {"term": "疑", "text": "好像。"},
            {"term": "举头", "text": "抬起头。"},
            {"term": "低头", "text": "低下头。"},
            {"term": "思故乡", "text": "思念自己的家乡。"}
        ],
    },
}


def load_json_database(path: Path, label: str):
    if not path.exists():
        return {"works": {}}

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError(f"{label}格式错误：顶层必须是对象。")
    works = raw.get("works", {})
    if not isinstance(works, dict):
        raise RuntimeError(f"{label}格式错误：works 必须是对象。")
    aliases = raw.get("aliases", {})
    if aliases and not isinstance(aliases, dict):
        raise RuntimeError(f"{label}格式错误：aliases 必须是对象。")
    global_notes = raw.get("globalNotes", [])
    if global_notes and not isinstance(global_notes, list):
        raise RuntimeError(f"{label}格式错误：globalNotes 必须是数组。")
    return {"works": works, "aliases": aliases, "globalNotes": global_notes}


def load_json_object(path: Path, default):
    if not path.exists():
        return default
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, type(default)) else default


def write_json_file(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


TEXTBOOK_KNOWLEDGE_BASE = load_json_database(KNOWLEDGE_BASE_PATH, "教材知识库")
GENERAL_ANNOTATION_BASE = load_json_database(GENERAL_ANNOTATION_BASE_PATH, "补充注释库")
TEXTBOOK_SOURCE_REGISTRY = json.loads(TEXTBOOK_SOURCE_REGISTRY_PATH.read_text(encoding="utf-8")) if TEXTBOOK_SOURCE_REGISTRY_PATH.exists() else {"works": []}
ensure_runtime_dirs()
AUTO_SUPPLEMENT_CACHE = load_json_object(AUTO_SUPPLEMENT_CACHE_PATH, {"works": {}})
AUTO_SUPPLEMENT_LOCK = threading.Lock()
ENRICHMENT_QUEUE = Queue()
ENRICHMENT_STATE = {}
ENRICHMENT_WORKER_STARTED = False


def load_lookup_module():
    for script_path in LOOKUP_SCRIPT_CANDIDATES:
        if not script_path.exists():
            continue
        spec = importlib.util.spec_from_file_location("classical_lookup_runtime", script_path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    candidates = " / ".join(str(path) for path in LOOKUP_SCRIPT_CANDIDATES)
    raise RuntimeError(f"无法加载查询脚本，已检查：{candidates}")


LOOKUP_MODULE = load_lookup_module()


def normalize_key(text: str) -> str:
    return re.sub(r"\s+", "", text or "").strip()


def resolve_known_title_alias(title: str) -> str:
    normalized_title = normalize_key(title)
    if not normalized_title:
        return title

    alias_map = TEXTBOOK_KNOWLEDGE_BASE.get("aliases", {})
    for alias, canonical in alias_map.items():
        if normalize_key(alias) == normalized_title and str(canonical).strip():
            return str(canonical).strip()

    for canonical_title, entry in TEXTBOOK_KNOWLEDGE_BASE.get("works", {}).items():
        if normalize_key(canonical_title) == normalized_title:
            return canonical_title
        if not isinstance(entry, dict):
            continue
        for alias in entry.get("aliases", []):
            if normalize_key(str(alias)) == normalized_title:
                return canonical_title

    return title


def normalized_name_variants(text: str) -> set[str]:
    cleaned = normalize_key(text)
    if not cleaned:
        return set()
    variants = {
        cleaned,
        cleaned.removesuffix("撰"),
        cleaned.removesuffix("著"),
        cleaned.removesuffix("作"),
    }
    return {item for item in variants if item}


def work_cache_key(title: str, author: str) -> str:
    return f"{normalize_key(title)}::{normalize_key(author)}"


def fetch_url_text(url: str, user_agent: str = DEFAULT_USER_AGENT, timeout: float = 20):
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "ignore")


def fetch_json_url(url: str, timeout: float = 20):
    return json.loads(fetch_url_text(url, timeout=timeout))


def get_auto_supplement_entry(title: str, author: str):
    with AUTO_SUPPLEMENT_LOCK:
        return dict(AUTO_SUPPLEMENT_CACHE.get("works", {}).get(work_cache_key(title, author), {}))


def store_auto_supplement_entry(title: str, author: str, entry: dict):
    key = work_cache_key(title, author)
    with AUTO_SUPPLEMENT_LOCK:
        works = AUTO_SUPPLEMENT_CACHE.setdefault("works", {})
        current = works.get(key, {})
        merged = {
            "title": title,
            "author": author,
            "translation": normalize_text_list(current.get("translation", [])) or normalize_text_list(entry.get("translation", [])),
            "notes": normalize_notes(current.get("notes", [])) or normalize_notes(entry.get("notes", [])),
            "source": entry.get("source") or current.get("source", ""),
            "sourceUrl": entry.get("sourceUrl") or current.get("sourceUrl", ""),
            "fetchedAt": entry.get("fetchedAt") or current.get("fetchedAt", ""),
            "attemptedTranslation": bool(current.get("attemptedTranslation")) or bool(entry.get("attemptedTranslation")),
            "attemptedNotes": bool(current.get("attemptedNotes")) or bool(entry.get("attemptedNotes")),
        }
        if entry.get("translation"):
            merged["translation"] = normalize_text_list(entry.get("translation", []))
        if entry.get("notes"):
            merged["notes"] = normalize_notes(entry.get("notes", []))
        works[key] = merged
        write_json_file(AUTO_SUPPLEMENT_CACHE_PATH, AUTO_SUPPLEMENT_CACHE)


PHONETIC_LATIN_PATTERN = r"A-Za-zāáǎàōóǒòēéěèīíǐìūúǔùǖǘǚǜüḿńňǹêɡ"
CONTENT_STOP_MARKERS = [
    "【译文】",
    "【注释】",
    "【注解】",
    "【赏析】",
    "【创作背景】",
    "【写作背景】",
    "【相关问题解答】",
    "【相关成语】",
    "【木兰生世】",
    "A.字音：",
    "通假字",
    "古今异义",
    "一词多义",
    "词语活用",
    "特殊句式",
    "教授建议",
    "注：《",
]
SOURCE_STOP_MARKERS = [
    "——选自",
    "——节选自",
    "选自《",
    "节选自《",
]
AUTHOR_METADATA_PATTERN = re.compile(
    r"^(?:作者[:：]\s*)?(?:(?:〔[^〕]{1,12}〕|【[^】]{1,12}】|（[^）]{1,12}）|\([^) ]{1,12}\))\s*)?[\u4e00-\u9fff·]{1,16}$"
)


def strip_inline_phonetic_annotations(text: str):
    pattern = rf"[（(]\s*[{PHONETIC_LATIN_PATTERN}0-9,\-·. ]+\s*[)）]"
    return re.sub(pattern, "", text)


def is_author_metadata_line(text: str) -> bool:
    return bool(AUTHOR_METADATA_PATTERN.fullmatch(text))


def sanitize_content_lines(lines: list[str]) -> list[str]:
    sanitized = []
    for raw_line in lines:
        cleaned = str(raw_line).replace("\u3000", " ").strip()
        if not cleaned or cleaned in {"【原文】", "原文"}:
            continue
        if any(cleaned.startswith(marker) for marker in CONTENT_STOP_MARKERS):
            break
        if any(cleaned.startswith(marker) for marker in SOURCE_STOP_MARKERS):
            break
        if is_author_metadata_line(cleaned):
            continue
        cleaned = strip_inline_phonetic_annotations(cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            sanitized.append(cleaned)
    return sanitized


def extract_content_from_guwendao(html_text: str):
    match = re.search(r'<div class="contson"[^>]*>(.*?)</div>', html_text, re.S)
    if not match:
        return []
    block = match.group(1)
    for stopper in ["<p><strong>注释", "<p><strong>注解", "<p><strong>译文", "<p><strong>赏析", "<p><strong>创作背景", "<p><strong>写作背景"]:
        candidate = block.find(stopper)
        if candidate != -1:
            block = block[:candidate]
            break
    block = re.sub(r"<br ?/?>", "\n", block)
    block = re.sub(r"</p>\s*<p[^>]*>", "\n", block)
    block = re.sub(r"<[^>]+>", "", block)
    block = html.unescape(block)
    return sanitize_content_lines(block.splitlines())


def extract_translation_from_gushiwen(html_text: str):
    marker = "<strong>译文"
    start = html_text.find(marker)
    if start == -1:
        return []

    paragraph_start = html_text.rfind("<p", 0, start)
    if paragraph_start == -1:
        paragraph_start = start

    next_heading = html_text.find("<p><strong>", start + len(marker))
    if next_heading == -1:
        next_heading = html_text.find("</div>", start)
    if next_heading == -1:
        next_heading = min(len(html_text), start + 4000)

    block = html_text[paragraph_start:next_heading]
    block = re.sub(r"<strong>译文(?:及注释)?<br ?/?></strong>", "", block)
    block = re.sub(r"<br ?/?>", "\n", block)
    block = re.sub(r"</p>\s*<p>", "\n", block)
    block = re.sub(r"<[^>]+>", "", block)
    block = html.unescape(block)
    lines = []
    for raw_line in block.splitlines():
        cleaned = raw_line.replace("\u3000", " ").strip()
        if not cleaned or cleaned == "译文":
            continue
        lines.append(cleaned)
    return lines


def load_external_translation(title: str, author: str):
    source_url = EXTERNAL_TRANSLATION_SOURCES.get((normalize_key(title), normalize_key(author)))
    if not source_url:
        return []

    TRANSLATION_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_name = f"{normalize_key(title)}__{normalize_key(author)}.json"
    cache_path = TRANSLATION_CACHE_DIR / cache_name

    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(cached, list) and cached:
                return cached
        except Exception:
            pass

    html_text = fetch_url_text(source_url)
    lines = extract_translation_from_gushiwen(html_text)
    if lines:
        cache_path.write_text(json.dumps(lines, ensure_ascii=False, indent=2), encoding="utf-8")
    return lines


def normalize_for_match(text: str) -> str:
    return re.sub(r"[\s\u3000《》〈〉「」『』【】()（）〔〕]", "", text or "")


def title_match_score(candidate_title: str, requested_title: str) -> int:
    candidate_norm = normalize_for_match(candidate_title)
    requested_norm = normalize_for_match(requested_title)
    if not candidate_norm or not requested_norm:
        return 0
    if candidate_norm == requested_norm:
        return 1000
    if len(requested_norm) < 2:
        return 0
    if candidate_norm.startswith(requested_norm):
        return 780 - max(len(candidate_norm) - len(requested_norm), 0) * 12
    if requested_norm in candidate_norm:
        return 720 - candidate_norm.find(requested_norm) * 8 - max(len(candidate_norm) - len(requested_norm), 0) * 10
    if len(candidate_norm) >= 2 and requested_norm.startswith(candidate_norm):
        return 560 - max(len(requested_norm) - len(candidate_norm), 0) * 14
    return 0


def extract_source_text(html_text: str):
    match = re.search(r'<p class="source"[^>]*>(.*?)</p>', html_text, re.S)
    if not match:
        return ""
    block = re.sub(r"<br ?/?>", "\n", match.group(1))
    block = re.sub(r"<[^>]+>", "", block)
    return html.unescape(re.sub(r"\s+", " ", block)).strip()


def extract_title_from_detail_page(html_text: str):
    match = re.search(r"<title>\s*([^<]+?)原文", html_text, re.S)
    if match:
        return html.unescape(match.group(1)).strip()
    match = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, re.S)
    if not match:
        return ""
    title_text = re.sub(r"<[^>]+>", "", match.group(1))
    return html.unescape(re.sub(r"\s+", " ", title_text)).strip()


def extract_author_from_detail_page(html_text: str):
    source_text = extract_source_text(html_text)
    if not source_text:
        return ""
    return source_text.split("〔", 1)[0].strip()


def extract_guwendao_candidate_paths(title: str, author: str, timeout: float = 20):
    if not author:
        return []

    url = f"https://m.guwendao.net/shiwens/default.aspx?astr={quote(author)}"
    html_text = fetch_url_text(url, user_agent=MOBILE_USER_AGENT, timeout=timeout)
    candidates = []
    seen = set()

    for href, anchor_text in re.findall(r'href="(/shiwenv_[a-z0-9]+\.aspx)"[^>]*>([^<]+)</a>', html_text):
        if title_match_score(anchor_text, title) <= 0:
            continue
        if href in seen:
            continue
        seen.add(href)
        candidates.append(href)
    return candidates


def extract_guwendao_search_paths(title: str, timeout: float = 20):
    query = normalize_key(title)
    if not query:
        return []

    url = f"https://www.guwendao.net/search.aspx?value={quote(title)}"
    html_text = fetch_url_text(url, timeout=timeout)
    candidates = []
    seen = set()

    for href, anchor_text in re.findall(r'href="(/shiwenv_[a-z0-9]+\.aspx)"[^>]*>(.*?)</a>', html_text, re.S):
        clean_text = re.sub(r"<[^>]+>", "", anchor_text).strip()
        if title_match_score(clean_text, title) <= 0:
            continue
        if href in seen:
            continue
        seen.add(href)
        candidates.append(href)
    return candidates


def detail_page_match_score(html_text: str, title: str, author: str, content_lines: list[str]):
    page_title = extract_title_from_detail_page(html_text)
    page_author = extract_author_from_detail_page(html_text)
    score = 0
    score += min(title_match_score(page_title, title) // 100, 10)
    if author and normalize_for_match(author) and normalize_for_match(author) in normalize_for_match(page_author):
        score += 5
    if not author:
        preferred_authors = preferred_authors_for_title(title)
        if preferred_authors and author_matches_any_preferred(page_author, preferred_authors):
            score += 8
        score += min(author_fame_score(page_author) // 20, 6)

    page_lines = extract_content_from_guwendao(html_text)
    if content_lines and page_lines and normalize_for_match(page_lines[0]) == normalize_for_match(content_lines[0]):
        score += 20
    elif content_lines and page_lines and normalize_for_match("".join(page_lines[:2])) == normalize_for_match("".join(content_lines[:2])):
        score += 15

    return score


def resolve_guwendao_detail_page(title: str, author: str, content_lines: list[str], timeout: float = 20):
    best_match = None
    best_score = -1
    candidate_paths = []
    seen = set()
    for path in [*extract_guwendao_candidate_paths(title, author, timeout=timeout), *extract_guwendao_search_paths(title, timeout=timeout)]:
        if path in seen:
            continue
        seen.add(path)
        candidate_paths.append(path)

    for path in candidate_paths[:12]:
        url = f"https://www.guwendao.net{path}"
        html_text = fetch_url_text(url, timeout=timeout)
        score = detail_page_match_score(html_text, title, author, content_lines)
        if score > best_score:
            best_score = score
            best_match = {"url": url, "html": html_text}

    return best_match if best_score >= 10 else None


def lookup_from_guwendao_search(title: str, author: str):
    detail_page = resolve_guwendao_detail_page(title, author, [])
    if not detail_page:
        return None

    content = extract_content_from_guwendao(detail_page["html"])
    if not content:
        return None

    return RegistryLookupResult(
        extract_title_from_detail_page(detail_page["html"]) or title,
        extract_author_from_detail_page(detail_page["html"]) or author,
        "",
        content,
        "古文岛检索抓取",
    )


def title_matches_exact(candidate_title: str, requested_title: str) -> bool:
    return normalize_for_match(candidate_title) == normalize_for_match(requested_title)


def author_matches_requested(candidate_author: str, requested_author: str) -> bool:
    if not requested_author:
        return True
    candidate_variants = normalized_name_variants(candidate_author)
    requested_variants = normalized_name_variants(requested_author)
    return any(
        requested in candidate or candidate in requested
        for requested in requested_variants
        for candidate in candidate_variants
    )


def author_matches_any_preferred(candidate_author: str, preferred_authors: set[str]) -> bool:
    candidate_variants = normalized_name_variants(candidate_author)
    return any(
        preferred in current or current in preferred
        for preferred in preferred_authors
        for current in candidate_variants
    )


def preferred_authors_for_title(title: str) -> set[str]:
    authors = set()
    title_entry = database_entry_for(TEXTBOOK_KNOWLEDGE_BASE, title)
    author = str(title_entry.get("author", "")).strip()
    if author:
        authors.update(normalized_name_variants(author))
    for item in TEXTBOOK_SOURCE_REGISTRY.get("works", []):
        if normalize_key(item.get("title", "")) != normalize_key(title):
            continue
        candidate_author = str(item.get("author", "")).strip()
        if candidate_author:
            authors.update(normalized_name_variants(candidate_author))
    return authors


def author_fame_score(author: str) -> int:
    author_variants = normalized_name_variants(author)
    best = 0
    for candidate, score in AUTHOR_FAME_SCORES.items():
        candidate_variants = normalized_name_variants(candidate)
        if any(
            known in current or current in known
            for known in candidate_variants
            for current in author_variants
        ):
            best = max(best, score)
    return best


def popular_work_score(title: str, author: str) -> int:
    title_norm = normalize_key(title)
    author_variants = normalized_name_variants(author)
    best = 0
    for (known_title, known_author), score in POPULAR_WORK_SCORES.items():
        if normalize_key(known_title) != title_norm:
            continue
        known_author_variants = normalized_name_variants(known_author)
        if any(
            known in current or current in known
            for known in known_author_variants
            for current in author_variants
        ):
            best = max(best, score)
    return best


def candidate_source_score(source: str) -> int:
    if "教材页" in source:
        return 140
    if "内置古文库" in source:
        return 120
    if "gaokao" in source:
        return 110
    if "诗泉 API" in source:
        return 80
    if "古文岛" in source:
        return 60
    return 0


def same_title_candidate_score(candidate, requested_title: str, preferred_authors: set[str]) -> int:
    author_variants = normalized_name_variants(candidate.author)
    score = candidate_source_score(candidate.source)
    score += title_match_score(candidate.title, requested_title)
    if preferred_authors and any(
        preferred in current or current in preferred
        for preferred in preferred_authors
        for current in author_variants
    ):
        score += 260
    score += author_fame_score(candidate.author)
    score += popular_work_score(candidate.title, candidate.author)
    if candidate.dynasty:
        score += 10
    if candidate.content:
        score += min(len(candidate.content), 12)
    return score


def collect_priority_candidates_from_lookup_sources(title: str, author: str):
    candidates = []
    seen = set()

    for item in getattr(LOOKUP_MODULE, "LOCAL_TEXT_LIBRARY", []):
        if title_match_score(item.get("title", ""), title) <= 0:
            continue
        if not author_matches_requested(item.get("author", ""), author):
            continue
        result = RegistryLookupResult(
            item.get("title", title),
            item.get("author", ""),
            item.get("dynasty", ""),
            item.get("content", []),
            item.get("source", "内置古文库"),
        )
        signature = (normalize_key(result.title), normalize_key(result.author), result.source)
        if signature in seen:
            continue
        seen.add(signature)
        candidates.append(result)

    try:
        for item in LOOKUP_MODULE.load_gaokao_dataset():
            if title_match_score(item.get("title", ""), title) <= 0:
                continue
            if not author_matches_requested(item.get("author", ""), author):
                continue
            result = RegistryLookupResult(
                item.get("title", title),
                item.get("author", ""),
                item.get("dynasty", ""),
                item.get("content", []),
                "gaokao-poetry 补充古文库",
            )
            signature = (normalize_key(result.title), normalize_key(result.author), result.source)
            if signature in seen:
                continue
            seen.add(signature)
            candidates.append(result)
    except Exception:
        pass

    try:
        query = (
            f"{LOOKUP_MODULE.POETRY_SEARCH_URL}?"
            f"q={quote(title)}&type=title&page=1&pageSize=100"
        )
        payload = fetch_json_url(query)
        if isinstance(payload, dict):
            for item in payload.get("data", []):
                item_title = item.get("title", "")
                item_author = ((item.get("author") or {}).get("name")) or ""
                if title_match_score(item_title, title) <= 0:
                    continue
                if not author_matches_requested(item_author, author):
                    continue
                result = RegistryLookupResult(
                    item_title or title,
                    item_author,
                    ((item.get("dynasty") or {}).get("name")) or "",
                    item.get("content", []),
                    "诗泉 API（基于 chinese-poetry）",
                )
                signature = (normalize_key(result.title), normalize_key(result.author), result.source)
                if signature in seen:
                    continue
                seen.add(signature)
                candidates.append(result)
    except Exception:
        pass

    return candidates


def lookup_preferred_same_title_result(title: str, author: str):
    candidates = []

    registry_match = lookup_from_registry(title, author)
    if registry_match:
        candidates.append(registry_match)

    candidates.extend(collect_priority_candidates_from_lookup_sources(title, author))
    if not candidates:
        return None

    preferred_authors = preferred_authors_for_title(title)
    ranked = sorted(
        enumerate(candidates),
        key=lambda item: (
            -same_title_candidate_score(item[1], title, preferred_authors),
            item[0],
        ),
    )
    return ranked[0][1]


def extract_fanyi_request_params(html_text: str):
    match = re.search(r"fanyiShow\((\d+),'([A-Z0-9]+)','([a-z0-9]+)'\)", html_text)
    if not match:
        return None
    return {
        "id": match.group(1),
        "idjm": match.group(2),
        "idStr": match.group(3),
    }


def html_fragment_to_lines(fragment: str):
    fragment = re.sub(r"<br ?/?>", "\n", fragment)
    fragment = re.sub(r"</p>\s*<p[^>]*>", "\n", fragment)
    fragment = re.sub(r"<a[^>]*>.*?</a>", "", fragment, flags=re.S)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    fragment = html.unescape(fragment)
    lines = []
    for raw_line in fragment.splitlines():
        cleaned = raw_line.replace("\u3000", " ").strip()
        if cleaned:
            lines.append(re.sub(r"\s+", " ", cleaned))
    return lines


def extract_translation_and_notes_from_fanyi(html_text: str):
    match = re.search(r'<div class="contyishang"[^>]*>(.*?)</div>\s*<div class="cankao">', html_text, re.S)
    if not match:
        return {"translation": [], "notes": []}

    block = match.group(1)
    translation_heading = re.search(
        r"<strong>\s*译文(?:及注释)?\s*(?:<br ?/?>)?\s*</strong>",
        block,
        re.S,
    )
    notes_heading = re.search(
        r"<strong>\s*注释\s*(?:<br ?/?>)?\s*</strong>",
        block,
        re.S,
    )

    translation_fragment = ""
    notes_fragment = ""

    if translation_heading:
        translation_start = translation_heading.end()
        translation_end = notes_heading.start() if notes_heading else len(block)
        translation_fragment = block[translation_start:translation_end]

    if notes_heading:
        notes_fragment = block[notes_heading.end():]

    return {
        "translation": html_fragment_to_lines(translation_fragment),
        "notes": normalize_notes(html_fragment_to_lines(notes_fragment)),
    }


def fetch_auto_supplement(title: str, author: str, content_lines: list[str], timeout: float = 20):
    detail_page = resolve_guwendao_detail_page(title, author, content_lines, timeout=timeout)
    if not detail_page:
        return {}

    params = extract_fanyi_request_params(detail_page["html"])
    if not params:
        return {}

    ajax_url = (
        "https://www.guwendao.net/nocdn/ajaxfanyi.aspx"
        f"?id={params['id']}&idjm={params['idjm']}&idStr={params['idStr']}"
    )
    ajax_html = fetch_url_text(ajax_url, timeout=timeout)
    parsed = extract_translation_and_notes_from_fanyi(ajax_html)
    if not parsed["translation"] and not parsed["notes"]:
        return {}

    return {
        "title": title,
        "author": author,
        "translation": parsed["translation"],
        "notes": parsed["notes"],
        "attemptedTranslation": True,
        "attemptedNotes": True,
        "source": "古文岛自动补全",
        "sourceUrl": detail_page["url"],
        "fetchedAt": datetime.now().isoformat(timespec="seconds"),
    }


def registry_lookup_entry(title: str, author: str):
    title_key = normalize_key(title)
    author_key = normalize_key(author)
    matches = []
    preferred_authors = preferred_authors_for_title(title)
    for index, item in enumerate(TEXTBOOK_SOURCE_REGISTRY.get("works", [])):
        if title_match_score(item.get("title", ""), title) <= 0:
            continue
        candidate_author = normalize_key(item.get("author", ""))
        if author_key and candidate_author and author_key not in candidate_author:
            continue
        pseudo = RegistryLookupResult(
            item.get("title", title),
            item.get("author", ""),
            item.get("dynasty", ""),
            [],
            "教材页来源表",
        )
        matches.append((same_title_candidate_score(pseudo, title, preferred_authors), index, item))
    if not matches:
        return None
    matches.sort(key=lambda entry: (-entry[0], entry[1]))
    return matches[0][2]


class RegistryLookupResult:
    def __init__(self, title: str, author: str, dynasty: str, content: list[str], source: str):
        self.title = title
        self.author = author
        self.dynasty = dynasty
        self.content = content
        self.source = source


def lookup_from_registry(title: str, author: str):
    entry = registry_lookup_entry(title, author)
    if not entry:
        return None

    TEXT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_name = f'{normalize_key(entry.get("title",""))}__{normalize_key(entry.get("author",""))}.json'
    cache_path = TEXT_CACHE_DIR / cache_name

    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(cached, list) and cached:
                sanitized = sanitize_content_lines(cached)
                if sanitized != cached:
                    cache_path.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding="utf-8")
                if sanitized:
                    return RegistryLookupResult(entry["title"], entry.get("author", ""), entry.get("dynasty", ""), sanitized, "教材页本地缓存")
        except Exception:
            pass

    html_text = fetch_url_text(entry["source_url"])
    content = extract_content_from_guwendao(html_text)
    if not content:
        return None
    cache_path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    return RegistryLookupResult(entry["title"], entry.get("author", ""), entry.get("dynasty", ""), content, "教材页抓取")


def tokens_for_text(text: str):
    values = pinyin(text, style=Style.TONE, heteronym=False, errors=lambda raw: list(raw))
    return [{"char": char, "pinyin": item[0] if item else char, "noteNumbers": []} for char, item in zip(text, values)]


def normalize_notes(notes):
    normalized = []
    for item in notes:
        if isinstance(item, dict):
            term = str(item.get("term", "")).strip()
            text = str(item.get("text", "")).strip()
            source = str(item.get("source", "")).strip()
            source_label = str(item.get("sourceLabel", "")).strip()
            note_index = item.get("index")
        else:
            raw = str(item).strip()
            if "：" in raw:
                term, text = raw.split("：", 1)
            elif ":" in raw:
                term, text = raw.split(":", 1)
            else:
                term, text = "", raw
            term = term.strip()
            text = text.strip()
            source = ""
            source_label = ""
            note_index = None
        entry = {"term": term, "text": text}
        if source:
            entry["source"] = source
        if source_label:
            entry["sourceLabel"] = source_label
        if note_index is not None:
            entry["index"] = note_index
        normalized.append(entry)
    return normalized


def normalize_text_list(values):
    if not values:
        return []
    if not isinstance(values, list):
        return [str(values).strip()]
    return [str(item).strip() for item in values if str(item).strip()]


def ensure_enrichment_worker():
    global ENRICHMENT_WORKER_STARTED
    with AUTO_SUPPLEMENT_LOCK:
        if ENRICHMENT_WORKER_STARTED:
            return
        worker = threading.Thread(target=enrichment_worker_loop, name="poem-enrichment", daemon=True)
        worker.start()
        ENRICHMENT_WORKER_STARTED = True


def update_enrichment_state(key: str, status: str, **extra):
    with AUTO_SUPPLEMENT_LOCK:
        ENRICHMENT_STATE[key] = {
            "status": status,
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
            **extra,
        }


def get_enrichment_state(title: str, author: str):
    key = work_cache_key(title, author)
    with AUTO_SUPPLEMENT_LOCK:
        state = ENRICHMENT_STATE.get(key, {})
    if state:
        return dict(state)
    auto_entry = get_auto_supplement_entry(title, author)
    if auto_entry.get("translation") or auto_entry.get("notes"):
        return {
            "status": "ready",
            "message": "这篇作品的补充资料已缓存，下次查询会直接显示。",
            "updatedAt": auto_entry.get("fetchedAt", ""),
        }
    if auto_entry.get("attemptedTranslation") or auto_entry.get("attemptedNotes"):
        return {
            "status": "settled",
            "message": "后台已尝试补全，但当前来源提供的资料仍然有限。",
            "updatedAt": auto_entry.get("fetchedAt", ""),
        }
    return {"status": "idle", "message": ""}


def schedule_enrichment(title: str, author: str, content_lines: list[str], needs_translation: bool, needs_notes: bool):
    if not needs_translation and not needs_notes:
        return {"status": "not_needed", "message": ""}

    auto_entry = get_auto_supplement_entry(title, author)
    translation_satisfied = (
        not needs_translation
        or bool(auto_entry.get("translation"))
        or bool(auto_entry.get("attemptedTranslation"))
    )
    notes_satisfied = (
        not needs_notes
        or bool(auto_entry.get("notes"))
        or bool(auto_entry.get("attemptedNotes"))
    )

    if translation_satisfied and notes_satisfied:
        return {
            "status": "ready" if (auto_entry.get("translation") or auto_entry.get("notes")) else "settled",
            "message": "这篇作品的补充资料已缓存，下次查询会直接显示。"
            if (auto_entry.get("translation") or auto_entry.get("notes"))
            else "后台已尝试补全，但当前来源提供的资料仍然有限。",
            "updatedAt": auto_entry.get("fetchedAt", ""),
        }

    ensure_enrichment_worker()
    key = work_cache_key(title, author)
    state = get_enrichment_state(title, author)
    if state["status"] in {"queued", "running"}:
        return state

    update_enrichment_state(
        key,
        "queued",
        message="当前缺少译文或注释，已加入后台补全队列。",
        needsTranslation=needs_translation,
        needsNotes=needs_notes,
    )
    ENRICHMENT_QUEUE.put(
        {
            "key": key,
            "title": title,
            "author": author,
            "contentLines": list(content_lines),
            "needsTranslation": needs_translation,
            "needsNotes": needs_notes,
        }
    )
    return get_enrichment_state(title, author)


def refresh_enrichment_now(title: str, author: str, content_lines: list[str], needs_translation: bool, needs_notes: bool, force_refresh: bool = False):
    if not needs_translation and not needs_notes:
        return get_enrichment_state(title, author)

    key = work_cache_key(title, author)
    auto_entry = get_auto_supplement_entry(title, author)
    if not force_refresh:
        translation_satisfied = (
            not needs_translation
            or bool(auto_entry.get("translation"))
            or bool(auto_entry.get("attemptedTranslation"))
        )
        notes_satisfied = (
            not needs_notes
            or bool(auto_entry.get("notes"))
            or bool(auto_entry.get("attemptedNotes"))
        )
        if translation_satisfied and notes_satisfied:
            return get_enrichment_state(title, author)

    update_enrichment_state(
        key,
        "running",
        message=f"正在抓取补充资料，最多等待约 {int(SYNC_ENRICH_TIMEOUT_SECONDS)} 秒。",
        needsTranslation=needs_translation,
        needsNotes=needs_notes,
        mode="sync",
    )

    started_at = time.monotonic()
    try:
        fetched = fetch_auto_supplement(
            title,
            author,
            content_lines,
            timeout=SYNC_ENRICH_REQUEST_TIMEOUT_SECONDS,
        )
        elapsed = time.monotonic() - started_at
        if fetched:
            store_auto_supplement_entry(title, author, fetched)
            update_enrichment_state(
                key,
                "ready",
                message="补充资料已抓取并写入本地缓存。",
                source=fetched.get("source", ""),
                elapsedSeconds=round(elapsed, 2),
            )
        else:
            store_auto_supplement_entry(
                title,
                author,
                {
                    "title": title,
                    "author": author,
                    "attemptedTranslation": needs_translation,
                    "attemptedNotes": needs_notes,
                    "fetchedAt": datetime.now().isoformat(timespec="seconds"),
                },
            )
            update_enrichment_state(
                key,
                "settled",
                message="本次已尝试抓取，但当前来源没有更多可用资料。",
                elapsedSeconds=round(elapsed, 2),
            )
    except Exception as exc:
        elapsed = time.monotonic() - started_at
        update_enrichment_state(
            key,
            "failed",
            message="本次抓取失败，可稍后再次刷新重试。",
            error=str(exc),
            elapsedSeconds=round(elapsed, 2),
        )

    return get_enrichment_state(title, author)


def enrichment_worker_loop():
    while True:
        job = ENRICHMENT_QUEUE.get()
        key = job["key"]
        try:
            update_enrichment_state(
                key,
                "running",
                message="正在后台补全这篇作品的译文与注释。",
                needsTranslation=job.get("needsTranslation", False),
                needsNotes=job.get("needsNotes", False),
            )
            fetched = fetch_auto_supplement(job["title"], job["author"], job["contentLines"])
            if fetched:
                store_auto_supplement_entry(job["title"], job["author"], fetched)
                update_enrichment_state(
                    key,
                    "ready",
                    message="后台补全完成，重新搜索即可看到新增译文和注释。",
                    source=fetched.get("source", ""),
                )
            else:
                store_auto_supplement_entry(
                    job["title"],
                    job["author"],
                    {
                        "title": job["title"],
                        "author": job["author"],
                        "attemptedTranslation": job.get("needsTranslation", False),
                        "attemptedNotes": job.get("needsNotes", False),
                        "fetchedAt": datetime.now().isoformat(timespec="seconds"),
                    },
                )
                update_enrichment_state(
                    key,
                    "settled",
                    message="后台已尝试补全，但当前来源没有更多可用资料。",
                )
        except Exception as exc:
            update_enrichment_state(
                key,
                "failed",
                message="后台补全过程失败，稍后可再次尝试。",
                error=str(exc),
            )
        finally:
            ENRICHMENT_QUEUE.task_done()


def database_entry_for(database, title: str):
    aliases = database.get("aliases", {})
    resolved_title = aliases.get(title, title)
    works = database.get("works", {})
    direct = works.get(resolved_title)
    if isinstance(direct, dict):
        return direct

    direct = works.get(title)
    if isinstance(direct, dict):
        return direct

    for entry in works.values():
        if not isinstance(entry, dict):
            continue
        aliases = entry.get("aliases", [])
        if any(str(alias).strip() == title for alias in aliases):
            return entry
    return {}


def note_applicable_to_title(item, title: str):
    titles = item.get("titles") if isinstance(item, dict) else None
    if not titles:
        return True
    return any(str(candidate).strip() == title for candidate in titles)


def collect_global_notes(database, title: str, content_lines):
    plain_text = "\n".join(content_lines)
    matches = []
    for item in database.get("globalNotes", []):
        if not isinstance(item, dict):
            continue
        term = str(item.get("term", "")).strip()
        text = str(item.get("text", "")).strip()
        if not term or not text:
            continue
        if not note_applicable_to_title(item, title):
            continue
        if term not in plain_text:
            continue
        matches.append({"term": term, "text": text})
    return matches


def merge_note_buckets(note_buckets):
    merged = []
    groups = []
    seen = set()

    for label, source, bucket in note_buckets:
        group_items = []
        for item in normalize_notes(bucket):
            term = item.get("term", "")
            text = item.get("text", "")
            signature = term or text
            if not text or signature in seen:
                continue
            seen.add(signature)
            index = len(merged) + 1
            note = {
                "index": index,
                "term": term,
                "text": text,
                "source": source,
                "sourceLabel": label,
            }
            merged.append(note)
            group_items.append(note)
        if group_items:
            groups.append({"label": label, "source": source, "items": group_items})

    return merged, groups


def build_annotated_lines(content_lines, notes):
    token_lines = [tokens_for_text(line) for line in content_lines]
    plain_lines = ["".join(unit["char"] for unit in line) for line in token_lines]

    sorted_notes = sorted(
        notes,
        key=lambda item: (-len(item.get("term", "")), int(item.get("index", 0) or 0)),
    )

    for fallback_index, note in enumerate(sorted_notes, start=1):
        term = note["term"]
        if not term:
            continue
        note_index = int(note.get("index") or fallback_index)
        for line_index, plain in enumerate(plain_lines):
            start = plain.find(term)
            if start == -1:
                continue
            end = start + len(term) - 1
            token_lines[line_index][end]["noteNumbers"].append(note_index)
            break

    return token_lines


def author_views(author: str, dynasty: str):
    author_text = author or "佚名"
    dynasty_text = dynasty.strip()
    display = list(author_text)
    if dynasty_text:
        display.extend(["〔", *list(dynasty_text), "〕"])
    pinyin_values = [item[0] for item in pinyin("".join(display), style=Style.TONE, heteronym=False, errors=lambda raw: list(raw))]
    normalized = ["" if char in {"〔", "〕"} else py for char, py in zip(display, pinyin_values)]
    normalized = ["〔" if char == "〔" else "〕" if char == "〕" else py for char, py in zip(display, normalized)]
    return display, normalized


def build_recitation_references(title: str, author: str):
    display_query = f"{title} {author} 朗诵".strip()
    plain_query = f"{title} 朗诵".strip()

    return [
        {
            "label": "B站朗诵检索",
            "description": "适合找学生作品、名家朗诵和课堂示范。",
            "url": f"https://search.bilibili.com/all?keyword={quote(display_query)}",
        },
        {
            "label": "央视频检索",
            "description": "适合找更规范、更接近教材风格的朗读示范。",
            "url": f"https://search.cctv.com/search.php?qtext={quote(plain_query)}",
        },
    ]


def build_translation_references(title: str, author: str):
    display_query = f"{title} {author} 译文".strip()
    plain_query = f"{title} 译文".strip()
    compare_query = f"{title} {author} 白话翻译".strip()

    return [
        {
            "label": "古诗文网译文检索",
            "description": "优先查看教材常见篇目的白话译文与背景说明。",
            "url": f"https://so.gushiwen.cn/search.aspx?value={quote(display_query)}",
        },
        {
            "label": "诗词名句译文检索",
            "description": "适合查看诗词白话译文、句意和简要赏析。",
            "url": f"https://www.shicimingju.com/chaxun/all/{quote(plain_query)}",
        },
        {
            "label": "百度译文检索",
            "description": "作为补充入口，适合快速比对不同版本的白话翻译。",
            "url": f"https://www.baidu.com/s?wd={quote(compare_query)}",
        },
    ]


def build_payload(title: str, author: str = "", wait_for_enrichment: bool = False, force_refresh: bool = False, _sync_attempted: bool = False):
    resolved_title = resolve_known_title_alias(title)
    try:
        result = lookup_preferred_same_title_result(resolved_title, author or "")
        if not result:
            result = LOOKUP_MODULE.lookup(resolved_title, author or "")
    except Exception as exc:
        result = lookup_from_registry(resolved_title, author or "")
        if not result:
            result = lookup_from_guwendao_search(resolved_title, author or "")
        if not result:
            if author:
                raise LookupError(f"未找到作者为“{author}”的《{resolved_title}》。请检查作者写法，或留空作者后重新查询。") from exc
            raise
    supplements = SUPPLEMENTS.get(result.title, {})
    textbook_entry = database_entry_for(TEXTBOOK_KNOWLEDGE_BASE, result.title)
    general_entry = database_entry_for(GENERAL_ANNOTATION_BASE, result.title)
    auto_entry = get_auto_supplement_entry(result.title, result.author)
    dynasty = (
        result.dynasty
        or str(textbook_entry.get("dynasty", "")).strip()
        or str(general_entry.get("dynasty", "")).strip()
        or str(supplements.get("dynasty", "")).strip()
    )
    author_display, author_pinyin = author_views(result.author, dynasty)
    translation = normalize_text_list(textbook_entry.get("translation") or supplements.get("translation", []))
    if not translation:
        translation = normalize_text_list(auto_entry.get("translation", []))
    if not translation:
        translation = normalize_text_list(load_external_translation(result.title, result.author))
    appreciation = normalize_text_list(textbook_entry.get("appreciation") or supplements.get("appreciation", []))
    recite = normalize_text_list(textbook_entry.get("recite") or supplements.get("recite", []))
    textbook_notes = textbook_entry.get("notes", [])
    supplemental_notes = list(general_entry.get("notes", []))
    supplemental_notes.extend(collect_global_notes(GENERAL_ANNOTATION_BASE, result.title, result.content))
    if not textbook_notes and not supplemental_notes:
        supplemental_notes.extend(supplements.get("notes", []))
    auto_notes = []
    if not textbook_notes and not supplemental_notes:
        auto_notes = auto_entry.get("notes", [])
    notes, note_groups = merge_note_buckets(
        [
            ("课本注释", "textbook", textbook_notes),
            ("补充注释", "supplemental", supplemental_notes),
            ("后台补全注释", "auto", auto_notes),
        ]
    )
    needs_translation = not bool(translation)
    needs_notes = not bool(notes)
    if wait_for_enrichment and not _sync_attempted and (needs_translation or needs_notes):
        refresh_enrichment_now(
            result.title,
            result.author,
            result.content,
            needs_translation=needs_translation,
            needs_notes=needs_notes,
            force_refresh=force_refresh,
        )
        return build_payload(
            result.title,
            result.author,
            wait_for_enrichment=False,
            force_refresh=False,
            _sync_attempted=True,
        )
    annotated_lines = build_annotated_lines(result.content, notes)
    translation_references = build_translation_references(result.title, result.author)
    recitation_references = build_recitation_references(result.title, result.author)
    enrichment = schedule_enrichment(
        result.title,
        result.author,
        result.content,
        needs_translation=needs_translation,
        needs_notes=needs_notes,
    )
    note_source = "built_in"
    if textbook_notes and supplemental_notes:
        note_source = "textbook+supplemental"
    elif textbook_notes:
        note_source = "textbook"
    elif supplemental_notes:
        note_source = "supplemental"
    elif auto_notes:
        note_source = "auto"

    return {
        "title": result.title,
        "author": result.author,
        "dynasty": dynasty,
        "source": result.source,
        "authorDisplay": author_display,
        "authorPinyin": author_pinyin,
        "lines": annotated_lines,
        "translation": translation,
        "translationReferences": translation_references,
        "notes": notes,
        "noteGroups": note_groups,
        "recitationReferences": recitation_references,
        "appreciation": appreciation,
        "recite": recite,
        "knowledgeSource": note_source,
        "enrichment": enrichment,
        "availability": {
            "translation": bool(translation),
            "notes": bool(notes),
            "recitationReferences": bool(recitation_references),
            "appreciation": bool(appreciation),
            "recite": bool(recite),
        },
    }


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/human-status":
            self.handle_human_status()
            return
        if parsed.path == "/api/lookup":
            if not self.request_is_human_verified():
                self.write_json({"error": "请先完成人机验证。"}, HTTPStatus.FORBIDDEN)
                return
            self.handle_lookup(parsed)
            return
        if parsed.path == "/reader.html" and not self.request_is_human_verified():
            self.redirect("/index.html")
            return
        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/human-verify":
            self.handle_human_verify()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def request_is_human_verified(self) -> bool:
        return is_human_verified(self.headers.get("Cookie"))

    def handle_human_status(self):
        self.write_json({"verified": self.request_is_human_verified()}, HTTPStatus.OK)

    def handle_human_verify(self):
        token, max_age = issue_human_verification_token()
        self.write_json(
            {"verified": True, "maxAge": max_age},
            HTTPStatus.OK,
            extra_headers={
                "Set-Cookie": f"{HUMAN_VERIFICATION_COOKIE}={token}; Max-Age={max_age}; Path=/; HttpOnly; SameSite=Lax"
            },
        )

    def handle_lookup(self, parsed):
        params = parse_qs(parsed.query)
        title = params.get("title", [""])[0].strip()
        author = params.get("author", [""])[0].strip()
        wait_for_enrichment = params.get("waitForEnrichment", ["0"])[0].strip() in {"1", "true", "yes"}
        force_refresh = params.get("forceRefresh", ["0"])[0].strip() in {"1", "true", "yes"}

        if not title:
            self.write_json({"error": "请输入题目。"}, HTTPStatus.BAD_REQUEST)
            return

        try:
            payload = build_payload(title, author, wait_for_enrichment=wait_for_enrichment, force_refresh=force_refresh)
        except Exception as exc:
            self.write_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
            return

        self.write_json(payload, HTTPStatus.OK)

    def write_json(self, payload, status, extra_headers=None):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def redirect(self, location: str):
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.end_headers()


def main():
    host = os.getenv("POEM_UI_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.getenv("PORT") or os.getenv("POEM_UI_PORT", "8765"))
    ensure_enrichment_worker()
    server = ThreadingHTTPServer((host, port), AppHandler)
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    print(f"http://{display_host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
