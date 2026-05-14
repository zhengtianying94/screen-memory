#!/usr/bin/env python3
"""Screen Memory MCP Server — full feature parity with Windows plugin.

Single-file implementation: URI Graph, signals, capture, MCP protocol.
Pure Python stdlib. No external dependencies.
"""
from __future__ import annotations

import base64
import json
import math
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.request
import urllib.error
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# ─── NocturneUri ──────────────────────────────────────────────────────────

_PATTERN = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)://(.*)$")


@dataclass(frozen=True)
class NocturneUri:
    """URI scheme: <domain>://<path> for the memory graph."""
    domain: str
    path: str

    @classmethod
    def parse(cls, raw: str) -> NocturneUri:
        if not raw or not raw.strip():
            raise ValueError("invalid: empty or whitespace")
        m = _PATTERN.match(raw)
        if m is None:
            raise ValueError(f"invalid: '{raw}' does not match domain://path")
        domain = m.group(1)
        path = m.group(2).rstrip("/") or ""
        return cls(domain=domain, path=path)

    @classmethod
    def make(cls, domain: str, path: str) -> NocturneUri:
        return cls(domain=domain, path=path.rstrip("/") or "")

    def parent(self) -> Optional[NocturneUri]:
        if not self.path:
            return None
        segments = self.path.rsplit("/", 1)
        return NocturneUri(domain=self.domain, path=segments[0] if len(segments) > 1 else "")

    @property
    def leaf(self) -> str:
        if not self.path:
            return ""
        return self.path.rsplit("/", 1)[-1]

    def is_child_of(self, parent: NocturneUri) -> bool:
        if self.domain != parent.domain:
            return False
        if self == parent:
            return False
        if not parent.path:
            return True
        return self.path.startswith(parent.path + "/")

    def __str__(self) -> str:
        return f"{self.domain}://{self.path}"

    def __repr__(self) -> str:
        return f"NocturneUri({self.domain!r}, {self.path!r})"
