"""ScreenshotRepo: CRUD for captured screenshot metadata."""

from __future__ import annotations

from typing import Optional

from screen_memory.models.uri import NocturneUri
from screen_memory.storage.database import Database


class ScreenshotRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def insert(
        self,
        file_path: str,
        ocr_text: Optional[str] = None,
        uri: Optional[NocturneUri] = None,
    ) -> dict:
        uri_str = str(uri) if uri else None
        cur = self._db.execute(
            "INSERT INTO screenshots (file_path, ocr_text, uri) VALUES (?, ?, ?)",
            (file_path, ocr_text, uri_str),
        )
        return self.get_by_id(cur.lastrowid)  # type: ignore[arg-type]

    def get_by_id(self, screenshot_id: int) -> Optional[dict]:
        row = self._db.execute(
            "SELECT id, file_path, ocr_text, captured_at, uri FROM screenshots WHERE id=?",
            (screenshot_id,),
        ).fetchone()
        if row is None:
            return None
        keys = ["id", "file_path", "ocr_text", "captured_at", "uri"]
        return dict(zip(keys, row))

    def list_all(
        self,
        after: Optional[str] = None,
        before: Optional[str] = None,
    ) -> list[dict]:
        sql = "SELECT id, file_path, ocr_text, captured_at, uri FROM screenshots WHERE 1=1"
        params: list = []
        if after:
            sql += " AND captured_at >= ?"
            params.append(after)
        if before:
            sql += " AND captured_at <= ?"
            params.append(before)
        sql += " ORDER BY captured_at DESC"
        rows = self._db.execute(sql, tuple(params)).fetchall()
        keys = ["id", "file_path", "ocr_text", "captured_at", "uri"]
        return [dict(zip(keys, r)) for r in rows]

    def update_ocr(self, screenshot_id: int, ocr_text: str) -> None:
        self._db.execute(
            "UPDATE screenshots SET ocr_text=? WHERE id=?",
            (ocr_text, screenshot_id),
        )

    def link_uri(self, screenshot_id: int, uri: NocturneUri) -> None:
        self._db.execute(
            "UPDATE screenshots SET uri=? WHERE id=?",
            (str(uri), screenshot_id),
        )

    def search(self, query: str, limit: int = 20) -> list[dict]:
        rows = self._db.execute(
            "SELECT id, file_path, ocr_text, captured_at, uri FROM screenshots "
            "WHERE ocr_text LIKE ? ORDER BY captured_at DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        keys = ["id", "file_path", "ocr_text", "captured_at", "uri"]
        return [dict(zip(keys, r)) for r in rows]
