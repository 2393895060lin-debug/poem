from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import server

from sync_top500_archive import DEFAULT_DOCX_PATH, parse_rank_items, request_entries_from_items


ROOT = Path(__file__).resolve().parent
REPORT_PATH = ROOT / "top500_verify_report.json"


def verify(docx_path: Path, report_path: Path) -> dict:
    requests = request_entries_from_items(parse_rank_items(docx_path))
    items = []

    for request in requests:
        status = {
            "rank": request["rank"],
            "rawTitle": request["rawTitle"],
            "rawAuthor": request["rawAuthor"],
            "ok": False,
        }
        try:
            payload = server.build_payload(
                request["rawTitle"],
                request["rawAuthor"],
                wait_for_enrichment=False,
                force_refresh=False,
            )
            lines = payload.get("lines", [])
            translation = payload.get("translation", [])
            notes = payload.get("notes", [])
            status.update(
                {
                    "ok": bool(lines),
                    "canonicalTitle": str(payload.get("title", "")).strip(),
                    "canonicalAuthor": str(payload.get("author", "")).strip(),
                    "textSource": str(payload.get("source", "")).strip(),
                    "knowledgeSource": str(payload.get("knowledgeSource", "")).strip(),
                    "lineCount": len(lines),
                    "translationCount": len(translation),
                    "noteCount": len(notes),
                }
            )
        except Exception as exc:
            status["error"] = str(exc)
        items.append(status)

    missing_body = [item for item in items if not item["ok"]]
    missing_translation = [item for item in items if item.get("ok") and item.get("translationCount", 0) == 0]
    missing_notes = [item for item in items if item.get("ok") and item.get("noteCount", 0) == 0]

    summary = {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "requestCount": len(items),
        "bodyReadyCount": sum(1 for item in items if item["ok"]),
        "bodyMissingCount": len(missing_body),
        "translationReadyCount": sum(1 for item in items if item.get("translationCount", 0) > 0),
        "translationMissingCount": len(missing_translation),
        "noteReadyCount": sum(1 for item in items if item.get("noteCount", 0) > 0),
        "noteMissingCount": len(missing_notes),
        "fullyReadyCount": sum(
            1 for item in items if item.get("ok") and item.get("translationCount", 0) > 0 and item.get("noteCount", 0) > 0
        ),
        "sourceBreakdown": Counter(item.get("textSource", "") for item in items if item.get("ok")),
    }
    payload = {
        "summary": summary,
        "missingSamples": {
            "body": missing_body[:100],
            "translation": missing_translation[:100],
            "notes": missing_notes[:100],
        },
        "items": items,
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 TOP500 归档后的查询效果。")
    parser.add_argument("--docx", default=str(DEFAULT_DOCX_PATH), help="转换后的榜单 docx 路径。")
    parser.add_argument("--report", default=str(REPORT_PATH), help="校验报告输出路径。")
    args = parser.parse_args()

    summary = verify(Path(args.docx), Path(args.report))
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=lambda value: dict(value)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
