"""Nocturne URI: <domain>://<path> routing for the memory graph."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_PATTERN = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)://(.*)$")


@dataclass(frozen=True, slots=True)
class NocturneUri:
    domain: str
    path: str

    # -- construction ----------------------------------------------------------

    @classmethod
    def parse(cls, raw: str) -> NocturneUri:
        """Parse a ``domain://path`` string into a NocturneUri.

        Raises ValueError on any invalid input.
        """
        if not raw or not raw.strip():
            raise ValueError("invalid: empty or whitespace")

        m = _PATTERN.match(raw)
        if m is None:
            raise ValueError(f"invalid: '{raw}' does not match domain://path")

        domain = m.group(1)
        # Strip trailing slash(es) from path, but keep empty path as ""
        path = m.group(2).rstrip("/") or ""
        return cls(domain=domain, path=path)

    @classmethod
    def make(cls, domain: str, path: str) -> NocturneUri:
        """Build a NocturneUri from components (path already normalized)."""
        return cls(domain=domain, path=path.rstrip("/") or "")

    # -- derived properties ----------------------------------------------------

    def parent(self) -> Optional[NocturneUri]:
        """Return the parent URI, or None if this is a root URI."""
        if not self.path:
            return None
        segments = self.path.rsplit("/", 1)
        return NocturneUri(domain=self.domain, path=segments[0] if len(segments) > 1 else "")

    @property
    def leaf(self) -> str:
        """Return the last path segment, or '' for root URIs."""
        if not self.path:
            return ""
        return self.path.rsplit("/", 1)[-1]

    def is_child_of(self, parent: NocturneUri) -> bool:
        """True if *self* is a strict descendant of *parent*."""
        if self.domain != parent.domain:
            return False
        if self == parent:
            return False
        if not parent.path:
            return True  # everything under domain root is a child
        return self.path.startswith(parent.path + "/")

    # -- dunder helpers --------------------------------------------------------

    def __str__(self) -> str:
        return f"{self.domain}://{self.path}"

    def __repr__(self) -> str:
        return f"NocturneUri({self.domain!r}, {self.path!r})"
