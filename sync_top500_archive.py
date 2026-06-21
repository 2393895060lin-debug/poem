from __future__ import annotations

import argparse
import json
import re
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from docx import Document

import server


ROOT = Path(__file__).resolve().parent
DEFAULT_DOCX_PATH = ROOT / "imports" / "500诗词歌赋.docx"
OUTPUT_PATH = ROOT / "top500_knowledge_base.json"
REPORT_PATH = ROOT / "top500_import_report.json"

ANONYMOUS_AUTHOR_LABELS = {
    "",
    "佚名",
    "诗经",
    "汉乐府",
    "南朝乐府",
    "北朝乐府",
    "乐府诗集",
    "郭茂倩",
}
COLLECTION_AUTHOR_OVERRIDES = {
    "楚辞": "屈原",
    "楚辞·九歌": "屈原",
}
COLLECTION_AUTHOR_PREFIXES = {
    "诗经",
    "古诗十九首",
    "汉乐府",
    "南朝乐府",
    "北朝乐府",
}
MANUAL_SEARCH_ALIASES = {
    "前赤壁赋": ["赤壁赋"],
    "滕王阁赋": ["滕王阁序"],
    "满江红·小住京华": ["满江红"],
    "木兰花·拟古决绝词": ["木兰花·拟古决绝词柬友"],
    "楚辞·天问": ["天问"],
    "古诗十九首·迢迢牵牛星": ["迢迢牵牛星"],
    "古诗十九首·行行重行行": ["行行重行行"],
    "出塞·秦时明月汉时关": ["出塞"],
    "从军行·黄沙百战穿金甲": ["从军行七首·其四"],
    "江城子·十年生死两茫茫": ["江城子·乙卯正月二十日夜记梦"],
    "破阵子·醉里挑灯看剑": ["破阵子·为陈同甫赋壮词以寄之"],
    "满江红·写怀": ["满江红", "满江红·怒发冲冠"],
    "渔歌子": ["渔歌子·西塞山前白鹭飞"],
    "赠从弟": ["赠从弟·其二"],
    "拟行路难": ["拟行路难·其四"],
    "六月二十七日望湖楼醉书": ["六月二十七日望湖楼醉书五绝 其一"],
    "书湖阴先生壁": ["书湖阴先生壁二首 其一"],
    "山园小梅": ["山园小梅二首 其一"],
    "虞美人·春花秋月何时了": ["虞美人（春花秋月何时了）"],
    "浪淘沙·帘外雨潺潺": ["浪淘沙令·帘外雨潺潺"],
    "凉州词·黄河远上白云间": ["凉州词二首·其一"],
    "咏怀·夜中不能寐": ["咏怀八十二首·其一"],
    "杂诗·人生无根蒂": ["杂诗十二首·其一"],
    "读山海经·其十": ["读山海经十三首·其十"],
    "玉楼春·东城渐觉风光好": ["玉楼春"],
    "渔家傲·天接云涛连晓雾": ["渔家傲·记梦"],
    "己亥杂诗·浩荡离愁白日斜": ["己亥杂诗·其五"],
}
MANUAL_ACCEPT_ALIASES = {
    "前赤壁赋": {"赤壁赋"},
    "滕王阁赋": {"滕王阁序"},
    "木兰花·拟古决绝词": {"木兰花·拟古决绝词柬友"},
    "楚辞·天问": {"天问"},
    "古诗十九首·迢迢牵牛星": {"迢迢牵牛星"},
    "古诗十九首·行行重行行": {"行行重行行"},
    "出塞·秦时明月汉时关": {"出塞"},
    "从军行·黄沙百战穿金甲": {"从军行七首·其四"},
    "江城子·十年生死两茫茫": {"江城子·乙卯正月二十日夜记梦"},
    "破阵子·醉里挑灯看剑": {"破阵子·为陈同甫赋壮词以寄之"},
    "满江红·写怀": {"满江红", "满江红·怒发冲冠"},
    "渔歌子": {"渔歌子·西塞山前白鹭飞"},
    "赠从弟": {"赠从弟·其二"},
    "拟行路难": {"拟行路难·其四"},
    "六月二十七日望湖楼醉书": {"六月二十七日望湖楼醉书五绝其一", "六月二十七日望湖楼醉书五绝 其一"},
    "书湖阴先生壁": {"书湖阴先生壁二首其一", "书湖阴先生壁二首 其一"},
    "山园小梅": {"山园小梅二首其一", "山园小梅二首 其一"},
    "虞美人·春花秋月何时了": {"虞美人（春花秋月何时了）", "虞美人·虞美人·春花秋月何时了"},
    "浪淘沙·帘外雨潺潺": {"浪淘沙令·帘外雨潺潺", "浪淘沙令·浪淘沙令·帘外雨潺潺"},
    "相见欢·无言独上西楼": {"相见欢·相见欢·无言独上西楼"},
    "凉州词·黄河远上白云间": {"凉州词二首·其一"},
    "咏怀·夜中不能寐": {"咏怀八十二首·其一"},
    "杂诗·人生无根蒂": {"杂诗十二首·其一"},
    "读山海经·其十": {"读山海经十三首·其十"},
    "玉楼春·东城渐觉风光好": {"玉楼春"},
    "渔家傲·天接云涛连晓雾": {"渔家傲·记梦"},
    "己亥杂诗·浩荡离愁白日斜": {"己亥杂诗·其五"},
}
MANUAL_AUTHOR_OVERRIDES = {
    "白头吟": ["卓文君"],
    "上邪": ["佚名"],
    "江南": ["佚名"],
    "迢迢牵牛星": ["佚名"],
    "行行重行行": ["佚名"],
    "古诗十九首·迢迢牵牛星": ["佚名"],
    "古诗十九首·行行重行行": ["佚名"],
    "木兰诗": ["佚名"],
    "木兰辞": ["佚名"],
    "满江红·小住京华": ["秋瑾"],
}


def normalize_key(text: str) -> str:
    return re.sub(r"\s+", "", text or "").strip()


def normalize_match(text: str) -> str:
    return re.sub(r"[\s\u3000《》〈〉「」『』【】()（）〔〕]", "", text or "")


def clean_text_lines(values: list[str]) -> list[str]:
    cleaned = []
    for item in values:
        text = str(item).replace("\u3000", " ").strip()
        text = re.sub(r"\s+", " ", text)
        if text:
            cleaned.append(text)
    return cleaned


def unique_ordered(values: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for value in values:
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def parse_rank_items(docx_path: Path) -> list[dict]:
    text = "\n".join(paragraph.text for paragraph in Document(str(docx_path)).paragraphs)
    start = text.index("1. 《诗经·关雎》")
    end = text.index("## 补充说明")
    body = text[start:end]

    items = []
    cursor = 0
    for rank in range(1, 501):
        marker = re.search(rf"(?<!\d){rank}[. ]+\s*(?=[^《]{{0,20}}《)", body[cursor:])
        if not marker:
            raise RuntimeError(f"未能在榜单文档中解析到第 {rank} 项。")
        start_index = cursor + marker.start()
        next_marker = (
            re.search(rf"(?<!\d){rank + 1}[. ]+\s*(?=[^《]{{0,20}}《)", body[start_index + len(marker.group(0)):])
            if rank < 500
            else None
        )
        end_index = start_index + len(marker.group(0)) + (
            next_marker.start() if next_marker else len(body[start_index + len(marker.group(0)):])
        )
        description = body[start_index + len(marker.group(0)):end_index].strip()
        items.append({"rank": rank, "description": description})
        cursor = end_index
    return items


def request_entries_from_items(items: list[dict]) -> list[dict]:
    requests = []
    seen = OrderedDict()
    for item in items:
        description = item["description"]
        titles = re.findall(r"《([^》]+)》", description)
        prefix = description.split("《", 1)[0].strip(" ：:;；，,。[]【】()（）*#-—")
        author = prefix if prefix and " " not in prefix and len(prefix) <= 12 else ""
        for title in titles:
            entry = {
                "rank": item["rank"],
                "rawTitle": title.strip(),
                "rawAuthor": author,
            }
            seen.setdefault((entry["rawTitle"], entry["rawAuthor"]), entry)
    requests.extend(seen.values())
    return requests


def base_title_variants(raw_title: str) -> list[str]:
    variants = [raw_title]
    if "·" in raw_title:
        parts = raw_title.split("·")
        variants.append("·".join(parts[1:]))
        variants.append(parts[-1])
    return unique_ordered(variants)


def title_variants(raw_title: str) -> list[str]:
    return unique_ordered(base_title_variants(raw_title) + MANUAL_SEARCH_ALIASES.get(raw_title, []))


def accepted_title_variants(raw_title: str) -> set[str]:
    accepted = set(base_title_variants(raw_title))
    accepted.update(MANUAL_ACCEPT_ALIASES.get(raw_title, set()))
    return {normalize_match(item) for item in accepted if item}


def expected_authors(raw_title: str, raw_author: str) -> list[str]:
    authors = []
    if raw_author and raw_author not in COLLECTION_AUTHOR_PREFIXES:
        authors.append(raw_author)
    authors.extend(MANUAL_AUTHOR_OVERRIDES.get(raw_title, []))
    for prefix, author in COLLECTION_AUTHOR_OVERRIDES.items():
        if raw_title == prefix or raw_title.startswith(f"{prefix}·"):
            authors.append(author)
    authors = unique_ordered(authors)
    return authors + [""] if authors else [""]


def accepted_author(raw_title: str, raw_author: str, resolved_author: str) -> bool:
    expected = normalize_key(raw_author)
    actual = normalize_key(resolved_author)
    if expected and raw_author not in COLLECTION_AUTHOR_PREFIXES:
        return expected in actual or actual in expected
    if raw_title.startswith("楚辞·"):
        return actual in {"", "屈原"}
    if raw_title.startswith("诗经·") or raw_title.startswith("古诗十九首·"):
        return actual in ANONYMOUS_AUTHOR_LABELS or "诗经" in actual or "古诗十九首" in actual
    if raw_title.startswith("汉乐府·") or raw_author == "汉乐府":
        return actual in ANONYMOUS_AUTHOR_LABELS
    if raw_title.startswith("南朝乐府·") or raw_title.startswith("北朝乐府·"):
        return actual in ANONYMOUS_AUTHOR_LABELS or "乐府" in actual
    return True


def accepted_payload(raw_title: str, raw_author: str, payload: dict) -> bool:
    resolved_title = normalize_match(payload.get("title", ""))
    if resolved_title not in accepted_title_variants(raw_title):
        return False
    if not accepted_author(raw_title, raw_author, payload.get("author", "")):
        return False
    return True


def build_work_entry(payload: dict, raw_title: str, rank: int) -> tuple[str, dict]:
    canonical_title = str(payload.get("title", "")).strip() or raw_title
    auto_entry = server.get_auto_supplement_entry(canonical_title, payload.get("author", ""))
    translation = clean_text_lines(payload.get("translation", []))
    notes = server.normalize_notes(payload.get("notes", []))
    entry = {
        "aliases": [],
        "author": str(payload.get("author", "")).strip(),
        "dynasty": str(payload.get("dynasty", "")).strip(),
        "translation": translation,
        "notes": notes,
        "archiveMeta": {
            "rank": rank,
            "rawTitle": raw_title,
            "textSource": str(payload.get("source", "")).strip(),
            "knowledgeSource": str(payload.get("knowledgeSource", "")).strip(),
            "translationCount": len(translation),
            "noteCount": len(notes),
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
        },
    }
    if auto_entry.get("source"):
        entry["archiveMeta"]["supplementSource"] = str(auto_entry.get("source", "")).strip()
    if auto_entry.get("sourceUrl"):
        entry["archiveMeta"]["supplementSourceUrl"] = str(auto_entry.get("sourceUrl", "")).strip()
    return canonical_title, entry


def merge_work_entry(existing: dict, incoming: dict, raw_title: str) -> dict:
    merged = dict(existing)
    aliases = unique_ordered([*existing.get("aliases", []), *incoming.get("aliases", []), raw_title])
    if raw_title and raw_title != merged.get("archiveMeta", {}).get("rawTitle") and raw_title not in aliases:
        aliases.append(raw_title)
    merged["aliases"] = aliases

    for field in ("author", "dynasty"):
        if not str(merged.get(field, "")).strip() and str(incoming.get(field, "")).strip():
            merged[field] = incoming[field]

    if not clean_text_lines(merged.get("translation", [])) and incoming.get("translation"):
        merged["translation"] = incoming["translation"]
    if not server.normalize_notes(merged.get("notes", [])) and incoming.get("notes"):
        merged["notes"] = incoming["notes"]

    meta = dict(merged.get("archiveMeta", {}))
    incoming_meta = incoming.get("archiveMeta", {})
    if incoming_meta:
        current_rank = int(meta.get("rank", 9999)) if str(meta.get("rank", "")).isdigit() else 9999
        incoming_rank = int(incoming_meta.get("rank", 9999)) if str(incoming_meta.get("rank", "")).isdigit() else 9999
        if incoming_rank < current_rank:
            meta["rank"] = incoming_rank
        meta.setdefault("rawTitle", incoming_meta.get("rawTitle", raw_title))
        meta["textSource"] = meta.get("textSource") or incoming_meta.get("textSource", "")
        meta["knowledgeSource"] = meta.get("knowledgeSource") or incoming_meta.get("knowledgeSource", "")
        meta["translationCount"] = len(clean_text_lines(merged.get("translation", [])))
        meta["noteCount"] = len(server.normalize_notes(merged.get("notes", [])))
        meta["updatedAt"] = incoming_meta.get("updatedAt", meta.get("updatedAt", ""))
        if incoming_meta.get("supplementSource"):
            meta["supplementSource"] = incoming_meta["supplementSource"]
        if incoming_meta.get("supplementSourceUrl"):
            meta["supplementSourceUrl"] = incoming_meta["supplementSourceUrl"]
    merged["archiveMeta"] = meta
    return merged


def attempt_lookup(raw_title: str, raw_author: str, delay_seconds: float = 0.0) -> dict:
    attempts = []
    for query_title in title_variants(raw_title):
        for query_author in expected_authors(raw_title, raw_author):
            try:
                payload = server.build_payload(
                    query_title,
                    query_author,
                    wait_for_enrichment=True,
                    force_refresh=True,
                )
                accepted = accepted_payload(raw_title, raw_author, payload)
                attempts.append(
                    {
                        "queryTitle": query_title,
                        "queryAuthor": query_author,
                        "resolvedTitle": str(payload.get("title", "")).strip(),
                        "resolvedAuthor": str(payload.get("author", "")).strip(),
                        "accepted": accepted,
                        "translationCount": len(clean_text_lines(payload.get("translation", []))),
                        "noteCount": len(server.normalize_notes(payload.get("notes", []))),
                        "textSource": str(payload.get("source", "")).strip(),
                    }
                )
                if accepted:
                    return {"ok": True, "payload": payload, "attempts": attempts}
            except Exception as exc:
                attempts.append(
                    {
                        "queryTitle": query_title,
                        "queryAuthor": query_author,
                        "error": str(exc),
                    }
                )
            if delay_seconds:
                time.sleep(delay_seconds)
    return {"ok": False, "attempts": attempts}


def load_json(path: Path, default):
    if not path.exists():
        return default
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, type(default)) else default


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sync_archive(docx_path: Path, output_path: Path, report_path: Path, delay_seconds: float) -> dict:
    requests = request_entries_from_items(parse_rank_items(docx_path))
    archive = load_json(output_path, {"aliases": {}, "works": {}})
    aliases = dict(archive.get("aliases", {}))
    works = dict(archive.get("works", {}))
    report_items = []

    for request in requests:
        lookup = attempt_lookup(request["rawTitle"], request["rawAuthor"], delay_seconds=delay_seconds)
        report_item = {
            "rank": request["rank"],
            "rawTitle": request["rawTitle"],
            "rawAuthor": request["rawAuthor"],
            "ok": lookup["ok"],
            "attempts": lookup["attempts"],
        }
        if lookup["ok"]:
            payload = lookup["payload"]
            canonical_title, incoming_entry = build_work_entry(payload, request["rawTitle"], request["rank"])
            current = works.get(canonical_title, {"aliases": []})
            current_aliases = list(current.get("aliases", []))
            if request["rawTitle"] != canonical_title and request["rawTitle"] not in current_aliases:
                current_aliases.append(request["rawTitle"])
            incoming_entry["aliases"] = unique_ordered(current_aliases + incoming_entry.get("aliases", []))
            works[canonical_title] = merge_work_entry(current, incoming_entry, request["rawTitle"])
            if request["rawTitle"] != canonical_title:
                aliases[request["rawTitle"]] = canonical_title
            report_item.update(
                {
                    "canonicalTitle": canonical_title,
                    "canonicalAuthor": str(payload.get("author", "")).strip(),
                    "translationCount": len(clean_text_lines(payload.get("translation", []))),
                    "noteCount": len(server.normalize_notes(payload.get("notes", []))),
                    "textSource": str(payload.get("source", "")).strip(),
                    "knowledgeSource": str(payload.get("knowledgeSource", "")).strip(),
                }
            )
        report_items.append(report_item)

    result = {"aliases": aliases, "works": works}
    write_json(output_path, result)

    summary = {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "sourceDocx": str(docx_path),
        "requestCount": len(requests),
        "workCount": len(works),
        "aliasCount": len(aliases),
        "resolvedCount": sum(1 for item in report_items if item["ok"]),
        "unresolvedCount": sum(1 for item in report_items if not item["ok"]),
        "translationReadyCount": sum(1 for item in report_items if item.get("translationCount", 0) > 0),
        "noteReadyCount": sum(1 for item in report_items if item.get("noteCount", 0) > 0),
        "fullyReadyCount": sum(
            1 for item in report_items if item.get("translationCount", 0) > 0 and item.get("noteCount", 0) > 0
        ),
    }
    write_json(report_path, {"summary": summary, "items": report_items})
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="将 500 诗词歌赋榜单同步到本地归档库。")
    parser.add_argument("--docx", default=str(DEFAULT_DOCX_PATH), help="转换后的榜单 docx 路径。")
    parser.add_argument("--output", default=str(OUTPUT_PATH), help="归档知识库输出路径。")
    parser.add_argument("--report", default=str(REPORT_PATH), help="导入报告输出路径。")
    parser.add_argument("--delay", type=float, default=0.1, help="每次网络尝试后的节流秒数。")
    args = parser.parse_args()

    summary = sync_archive(
        docx_path=Path(args.docx),
        output_path=Path(args.output),
        report_path=Path(args.report),
        delay_seconds=max(0.0, args.delay),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
