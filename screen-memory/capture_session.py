"""Timed screen capture: capture + OCR + save to DB on interval.

Usage:
  python capture_session.py [--interval 10] [--duration 3600] [--quality 80]

Signals:
  Ctrl+C or SIGINT → graceful stop after current capture.
"""
import sys, io, time, os, threading, signal, argparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from screen_memory.adapters.platform_factory import create_capture, create_ocr_chain
from screen_memory.storage.database import Database
from screen_memory.storage.screenshot_repo import ScreenshotRepo

DB_PATH = r"D:\ScreenMemo\screen-memory\screen-memory.db"

stop_event = threading.Event()

def handler(sig, frame):
    print("\nStopping...")
    stop_event.set()

signal.signal(signal.SIGINT, handler)


def main():
    parser = argparse.ArgumentParser(description="Timed screen capture session")
    parser.add_argument("--interval", type=int, default=10, help="Seconds between captures (default: 10)")
    parser.add_argument("--duration", type=int, default=3600, help="Total duration in seconds, 0=unlimited (default: 3600)")
    parser.add_argument("--quality", type=int, default=80, help="JPEG quality 1-100 (default: 80)")
    args = parser.parse_args()

    db = Database(DB_PATH)
    db.initialize()
    ss_repo = ScreenshotRepo(db)
    capture = create_capture()
    ocr_chain = create_ocr_chain()

    interval = max(3, args.interval)  # minimum 3s
    quality = args.quality

    if args.duration > 0:
        max_captures = args.duration // interval
        print(f"Starting: interval={interval}s, duration={args.duration}s (~{max_captures} captures), quality={quality}")
    else:
        max_captures = 0  # unlimited
        print(f"Starting: interval={interval}s, unlimited, quality={quality}. Ctrl+C to stop.")

    count = 0
    while not stop_event.is_set():
        if max_captures > 0 and count >= max_captures:
            break
        count += 1
        t0 = time.monotonic()
        try:
            result = capture.capture(quality=quality)
            ocr = ocr_chain.recognize(result.image_data)
            record = ss_repo.insert(file_path=result.file_path, ocr_text=ocr.text)
            elapsed = time.monotonic() - t0
            label = f"{count}" if max_captures == 0 else f"{count}/{max_captures}"
            print(f"[{label}] {result.file_path} | OCR:{ocr.engine} {len(ocr.text)}chars | {elapsed:.1f}s | app: {result.app_name}")
        except Exception as e:
            print(f"[{count}] ERROR: {e}")

        if not stop_event.is_set():
            stop_event.wait(interval)

    print(f"Done. Total captures: {count}")


if __name__ == "__main__":
    main()
