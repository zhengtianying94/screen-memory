"""screen-memory CLI: command-line interface for OpenClaw skill integration."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _get_registry(db_path: str | None = None):
    from screen_memory.storage.database import Database
    from screen_memory.storage.graph_repo import GraphRepo
    from screen_memory.storage.screenshot_repo import ScreenshotRepo
    from screen_memory.services.graph_service import GraphService
    from screen_memory.services.signal_service import SignalService, EntityPolicy
    from screen_memory.tools.registry import ToolRegistry

    if db_path is None:
        db_path = os.environ.get(
            "SCREEN_MEMORY_DB",
            str(Path.home() / ".screenmemory" / "screen-memory.db"),
        )
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    db = Database(db_path)
    db.initialize()
    repo = GraphRepo(db)
    ss_repo = ScreenshotRepo(db)
    graph_svc = GraphService(repo)
    policies = {
        "person": EntityPolicy("person", 3.0, 86400 * 7, ["seen_multiple_times"]),
        "topic": EntityPolicy("topic", 2.0, 86400 * 3, []),
        "location": EntityPolicy("location", 2.5, 86400 * 14, []),
        "event": EntityPolicy("event", 2.0, 86400 * 5, []),
    }
    signal_svc = SignalService(repo, policies)
    return ToolRegistry(graph_svc, signal_svc, ss_repo)


def _out(data):
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def cmd_write(args):
    reg = _get_registry(args.db)
    result = reg.call("memory_write", {"uri": args.uri, "content": args.content})
    _out(result)


def cmd_read(args):
    reg = _get_registry(args.db)
    result = reg.call("memory_read", {"uri": args.uri})
    _out(result)


def cmd_search(args):
    reg = _get_registry(args.db)
    result = reg.call("memory_search", {"query": args.query, "limit": args.limit})
    _out(result)


def cmd_delete(args):
    reg = _get_registry(args.db)
    result = reg.call("memory_delete", {"uri": args.uri})
    _out(result)


def cmd_subtree(args):
    reg = _get_registry(args.db)
    params = {"uri": args.uri}
    if args.max_depth is not None:
        params["max_depth"] = args.max_depth
    result = reg.call("graph_query_subtree", params)
    _out(result)


def cmd_signal_ingest(args):
    reg = _get_registry(args.db)
    params = {
        "entity_type": args.type,
        "entity_name": args.name,
        "source": args.source,
    }
    if args.evidence:
        params["evidence"] = args.evidence
    result = reg.call("signal_ingest", params)
    _out(result)


def cmd_signal_activate(args):
    reg = _get_registry(args.db)
    result = reg.call("signal_activate", {"entity_name": args.name})
    _out(result)


def cmd_screenshot_search(args):
    reg = _get_registry(args.db)
    result = reg.call("screenshot_search", {"query": args.query, "limit": args.limit})
    _out(result)


def cmd_capture(args):
    """Capture screen, run OCR, save to DB."""
    import sys as _sys
    import io as _io
    _sys.stdout = _io.TextIOWrapper(_sys.stdout.buffer, encoding="utf-8")

    from screen_memory.adapters.platform_factory import create_capture, create_ocr_chain
    from screen_memory.storage.screenshot_repo import ScreenshotRepo
    from screen_memory.storage.database import Database

    # Init DB
    db_path = args.db or os.environ.get(
        "SCREEN_MEMORY_DB",
        str(Path.home() / ".screenmemory" / "screen-memory.db"),
    )
    db = Database(db_path)
    db.initialize()
    ss_repo = ScreenshotRepo(db)

    # Capture
    capture = create_capture(screenshot_dir=args.screenshot_dir)
    quality = args.quality or 85
    result = capture.capture(quality=quality)

    # OCR
    ocr_text = ""
    ocr_engine = "none"
    if not args.no_ocr:
        ocr_chain = create_ocr_chain()
        ocr = ocr_chain.recognize(result.image_data)
        ocr_text = ocr.text
        ocr_engine = ocr.engine

    # Save to DB
    record = ss_repo.insert(file_path=result.file_path, ocr_text=ocr_text)

    _out({
        "ok": True,
        "screenshot_id": record["id"],
        "file_path": result.file_path,
        "size": f"{result.width}x{result.height}",
        "bytes": len(result.image_data),
        "capture_time_ms": result.capture_time_ms,
        "app_name": result.app_name,
        "ocr_engine": ocr_engine,
        "ocr_text_len": len(ocr_text),
        "ocr_text_preview": ocr_text[:500] if ocr_text else None,
    })


def main():
    parser = argparse.ArgumentParser(
        prog="screen-memory",
        description="Screen capture, OCR, and URI Graph memory for OpenClaw",
    )
    parser.add_argument("--db", default=None, help="Database file path")
    sub = parser.add_subparsers(dest="command", required=True)

    # write
    p = sub.add_parser("write", help="Write a memory to the URI Graph")
    p.add_argument("--uri", required=True)
    p.add_argument("--content", required=True)
    p.set_defaults(func=cmd_write)

    # read
    p = sub.add_parser("read", help="Read the latest memory at a URI")
    p.add_argument("--uri", required=True)
    p.set_defaults(func=cmd_read)

    # search
    p = sub.add_parser("search", help="Full-text search across all memories")
    p.add_argument("--query", required=True)
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_search)

    # delete
    p = sub.add_parser("delete", help="Delete a node and all its memories")
    p.add_argument("--uri", required=True)
    p.set_defaults(func=cmd_delete)

    # subtree
    p = sub.add_parser("subtree", help="Query the subtree rooted at a URI")
    p.add_argument("--uri", required=True)
    p.add_argument("--max-depth", type=int, default=None)
    p.set_defaults(func=cmd_subtree)

    # signal-ingest
    p = sub.add_parser("signal-ingest", help="Ingest a signal for entity tracking")
    p.add_argument("--type", required=True, dest="type")
    p.add_argument("--name", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--evidence", nargs="*", default=None)
    p.set_defaults(func=cmd_signal_ingest)

    # signal-activate
    p = sub.add_parser("signal-activate", help="Activate an entity into the graph")
    p.add_argument("--name", required=True)
    p.set_defaults(func=cmd_signal_activate)

    # screenshot-search
    p = sub.add_parser("screenshot-search", help="Search screenshots by OCR text")
    p.add_argument("--query", required=True)
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_screenshot_search)

    # capture
    p = sub.add_parser("capture", help="Capture screen, OCR, and save to DB")
    p.add_argument("--quality", type=int, default=85, help="JPEG quality 1-100")
    p.add_argument("--no-ocr", action="store_true", help="Skip OCR (save screenshot only)")
    p.add_argument("--screenshot-dir", default=None, help="Override screenshot save directory")
    p.set_defaults(func=cmd_capture)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
