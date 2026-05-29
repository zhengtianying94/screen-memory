# OpenClaw ScreenMemory Plugin Design Spec

> Python cross-platform plugin providing screen capture → OCR → indexing → Nocturne URI Graph memory for OpenClaw agents.

## 1. Overview

### 1.1 Goal

Convert ScreenMemo's core capabilities into a Python OpenClaw plugin that:
- Captures screenshots via platform-adaptive layer (Android/Windows/macOS/Linux)
- Performs OCR (system OCR primary, AI multimodal fallback)
- Builds FTS5 full-text search index
- Stores memories in Nocturne URI Graph with signal accumulation
- Exposes tools to OpenClaw agent for on-demand screen memory operations

### 1.2 Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | Python 3.10+ | Cross-platform, sqlite3 in stdlib |
| AI calls | Delegated to OpenClaw | No need to port HTTP gateway |
| Signal accumulation | Plan C: auto + query tools | Internal automatic, exposed review/query |
| Screen capture | Built-in, platform adapters | Accessibility/adb on Android, native APIs on desktop |
| OCR | System OCR + AI fallback | ML Kit / WinRT OCR / Vision → LLM multimodal |
| Memory model | Nocturne URI Graph internally | Adapted to OpenClaw standard tool interface |
| Plugin type | Regular tool plugin | Coexists with memory-core, not replacing |
| Dev methodology | TDD + SDD | Test-driven, spec-driven |

### 1.3 Architecture (Layered)

```
┌─────────────────────────────────────────────┐
│          OpenClaw Agent (LLM)                │
│     Invokes plugin tools on demand           │
├─────────────────────────────────────────────┤
│  Tools Layer (registered to OpenClaw)        │
│  ┌──────────┐ ┌───────────┐ ┌────────────┐  │
│  │Capture   │ │Search     │ │Entity      │  │
│  │Tools     │ │Tools      │ │Tools       │  │
│  └──────────┘ └───────────┘ └────────────┘  │
├─────────────────────────────────────────────┤
│  Service Layer (internal Python)             │
│  ┌──────────┐ ┌───────────┐ ┌────────────┐  │
│  │Capture   │ │OcrService │ │Signal      │  │
│  │Service   │ │           │ │Accumulator │  │
│  ├──────────┤ ├───────────┤ ├────────────┤  │
│  │IndexSvc  │ │EntityLife │ │UriGraph    │  │
│  │          │ │cycle      │ │Service     │  │
│  └──────────┘ └───────────┘ └────────────┘  │
├─────────────────────────────────────────────┤
│  Storage Layer (SQLite)                      │
│  ┌──────────┐ ┌───────────┐ ┌────────────┐  │
│  │URI Graph │ │Signal     │ │FTS5 Index  │  │
│  │Tables    │ │Tables     │ │            │  │
│  └──────────┘ └───────────┘ └────────────┘  │
├─────────────────────────────────────────────┤
│  Platform Adapter Layer                      │
│  ┌──────────┐ ┌───────────┐ ┌────────────┐  │
│  │Android   │ │Windows    │ │macOS/Linux │  │
│  │Capture   │ │Capture    │ │Capture     │  │
│  ├──────────┤ ├───────────┤ ├────────────┤  │
│  │ML Kit OCR│ │WinRT OCR  │ │Vision/Tess │  │
│  └──────────┘ └───────────┘ └────────────┘  │
└─────────────────────────────────────────────┘
```

---

## 2. Tools Interface Definition

### 2.1 Capture Tools

#### `screen_capture`

Capture a screenshot from the device.

```json
{
  "name": "screen_capture",
  "description": "Capture a screenshot from the current device screen. Returns image metadata (path, dimensions, timestamp). The image is stored locally and indexed for search.",
  "parameters": {
    "type": "object",
    "properties": {
      "quality": {
        "type": "integer",
        "description": "JPEG quality 1-100 (default 80)."
      },
      "region": {
        "type": "object",
        "description": "Optional capture region. If omitted, full screen.",
        "properties": {
          "x": {"type": "integer"},
          "y": {"type": "integer"},
          "width": {"type": "integer"},
          "height": {"type": "integer"}
        }
      }
    },
    "required": []
  }
}
```

**Returns:**
```json
{
  "success": true,
  "screenshot": {
    "id": "sc_20260428_143022",
    "file_path": "/data/screenmemory/screenshots/2026/04/28/143022.jpg",
    "width": 1080,
    "height": 2400,
    "capture_time": "2026-04-28T14:30:22+08:00",
    "file_size": 245760,
    "app_name": "WeChat",
    "ocr_text": "Hello, how are you?"
  }
}
```

#### `screen_capture_timed`

Start/stop timed automatic screenshot capture.

```json
{
  "name": "screen_capture_timed",
  "description": "Start or stop periodic automatic screenshot capture. While active, screenshots are captured at the specified interval and processed through OCR + indexing pipeline.",
  "parameters": {
    "type": "object",
    "properties": {
      "action": {
        "type": "string",
        "enum": ["start", "stop", "status"],
        "description": "Start, stop, or query status of timed capture."
      },
      "interval_seconds": {
        "type": "integer",
        "description": "Capture interval in seconds (minimum 5, default 30). Only for 'start'."
      },
      "quality": {
        "type": "integer",
        "description": "JPEG quality (default 80)."
      }
    },
    "required": ["action"]
  }
}
```

**Returns:**
```json
{
  "status": "running",
  "interval_seconds": 30,
  "captures_count": 42,
  "started_at": "2026-04-28T14:00:00+08:00"
}
```

### 2.2 Search Tools

#### `search_screen_memory`

Search captured screen content by keywords.

```json
{
  "name": "search_screen_memory",
  "description": "Search screen memory by OCR text or AI-generated tags within a time range. Uses FTS5 full-text search with CJK support.",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Plain text keyword query."
      },
      "start_time": {
        "type": "string",
        "description": "Start datetime (YYYY-MM-DD or YYYY-MM-DD HH:mm)."
      },
      "end_time": {
        "type": "string",
        "description": "End datetime (YYYY-MM-DD or YYYY-MM-DD HH:mm)."
      },
      "app_name": {
        "type": "string",
        "description": "Filter by application name."
      },
      "limit": {
        "type": "integer",
        "description": "Max results (1-50, default 20)."
      },
      "offset": {
        "type": "integer",
        "description": "Pagination offset."
      }
    },
    "required": ["query"]
  }
}
```

**Returns:**
```json
{
  "total": 15,
  "results": [
    {
      "screenshot_id": "sc_20260428_143022",
      "capture_time": "2026-04-28T14:30:22+08:00",
      "app_name": "WeChat",
      "ocr_snippet": "...matched text context...",
      "relevance_score": 0.92
    }
  ],
  "has_more": false
}
```

### 2.3 Memory Tools

#### `read_memory`

```json
{
  "name": "read_memory",
  "description": "Read a Nocturne URI Graph memory node by URI. Supports system URIs: system://boot (startup context), system://index (domain overview).",
  "parameters": {
    "type": "object",
    "properties": {
      "uri": {
        "type": "string",
        "description": "Memory URI (e.g. core://my_user/identity, dynamic://2026/04/28)."
      }
    },
    "required": ["uri"]
  }
}
```

**Returns:**
```json
{
  "uri": "core://my_user/identity",
  "content": "User is a software engineer...",
  "children": [
    {"uri": "core://my_user/identity/name", "title": "name", "priority": 0},
    {"uri": "core://my_user/identity/role", "title": "role", "priority": 1}
  ],
  "created_at": "2026-04-28T14:00:00+08:00",
  "updated_at": "2026-04-28T14:30:00+08:00"
}
```

#### `create_memory`

```json
{
  "name": "create_memory",
  "description": "Create a new memory node under a parent URI. Parent must exist. Domain roots (e.g. core://) accept children directly.",
  "parameters": {
    "type": "object",
    "properties": {
      "parent_uri": {
        "type": "string",
        "description": "Parent URI (e.g. core://my_user/people)."
      },
      "content": {
        "type": "string",
        "description": "Memory content in Markdown."
      },
      "title": {
        "type": "string",
        "description": "Child node name (a-z0-9_- only). Auto-assigned if omitted."
      },
      "priority": {
        "type": "integer",
        "description": "Edge priority (lower = higher priority, default 0)."
      },
      "disclosure": {
        "type": "string",
        "description": "When to recall this memory."
      }
    },
    "required": ["parent_uri", "content"]
  }
}
```

#### `update_memory`

```json
{
  "name": "update_memory",
  "description": "Update memory content. Mutually exclusive modes: patch (old_string→new_string) or append. Read before update recommended.",
  "parameters": {
    "type": "object",
    "properties": {
      "uri": {"type": "string", "description": "Memory URI to update."},
      "old_string": {"type": "string", "description": "Patch mode: exact text to replace."},
      "new_string": {"type": "string", "description": "Patch mode: replacement text. Empty string to delete."},
      "append": {"type": "string", "description": "Append mode: text to append."},
      "priority": {"type": "integer", "description": "New edge priority."},
      "disclosure": {"type": "string", "description": "New disclosure condition."}
    },
    "required": ["uri"]
  }
}
```

#### `delete_memory`

```json
{
  "name": "delete_memory",
  "description": "Delete a memory URI path and descendants. Historical content versions preserved for recovery.",
  "parameters": {
    "type": "object",
    "properties": {
      "uri": {"type": "string", "description": "Memory URI to delete."}
    },
    "required": ["uri"]
  }
}
```

#### `add_alias`

```json
{
  "name": "add_alias",
  "description": "Create an alias URI pointing to the same content as target_uri (not a copy). Cascades descendant paths.",
  "parameters": {
    "type": "object",
    "properties": {
      "new_uri": {"type": "string", "description": "New alias URI."},
      "target_uri": {"type": "string", "description": "Existing URI to alias."},
      "priority": {"type": "integer", "description": "Alias edge priority."},
      "disclosure": {"type": "string", "description": "Alias disclosure condition."}
    },
    "required": ["new_uri", "target_uri"]
  }
}
```

#### `search_memory`

```json
{
  "name": "search_memory",
  "description": "Search memories by keyword match on URI path and content (not semantic search).",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "Keyword to search."},
      "domain": {"type": "string", "description": "Optional domain filter (core, dynamic)."},
      "limit": {"type": "integer", "description": "Max results (1-100, default 10)."}
    },
    "required": ["query"]
  }
}
```

### 2.4 Entity & Signal Tools

#### `query_signals`

Query signal accumulation status for memory entities.

```json
{
  "name": "query_signals",
  "description": "Query the signal accumulation status of memory entities. Shows candidates approaching activation, active entities, and review queue.",
  "parameters": {
    "type": "object",
    "properties": {
      "status": {
        "type": "string",
        "enum": ["candidate", "active", "archived", "all"],
        "description": "Filter by entity status (default 'all')."
      },
      "entity_type": {
        "type": "string",
        "description": "Filter by entity type (identity, people, places, organizations, preferences, interests, projects, goals, habits, other)."
      },
      "limit": {
        "type": "integer",
        "description": "Max results (1-50, default 20)."
      }
    },
    "required": []
  }
}
```

**Returns:**
```json
{
  "entities": [
    {
      "entity_id": "ent_abc123",
      "uri": "core://my_user/people/zhang_san",
      "status": "candidate",
      "scores": {
        "raw": 1.5,
        "decayed": 1.2,
        "activation_threshold": 2.0,
        "missing_score": 0.8
      },
      "evidence": {
        "distinct_days": 1,
        "required_days": 2,
        "missing_days": 1,
        "segment_count": 3,
        "strong_signal_count": 1
      },
      "first_seen": "2026-04-27T10:00:00+08:00",
      "last_seen": "2026-04-28T14:00:00+08:00",
      "summary": "Colleague in engineering team"
    }
  ],
  "counts": {"candidate": 15, "active": 42, "archived": 3}
}
```

#### `review_entity`

Approve or dismiss a candidate entity from the review queue.

```json
{
  "name": "review_entity",
  "description": "Approve or dismiss a candidate memory entity. Approved entities are materialized into the URI Graph as long-term memories.",
  "parameters": {
    "type": "object",
    "properties": {
      "entity_id": {
        "type": "string",
        "description": "Entity ID from query_signals."
      },
      "action": {
        "type": "string",
        "enum": ["approve", "dismiss"],
        "description": "Approve (materialize) or dismiss (drop candidate)."
      }
    },
    "required": ["entity_id", "action"]
  }
}
```

#### `get_screenshot_detail`

Get full details of a specific screenshot including OCR text and AI tags.

```json
{
  "name": "get_screenshot_detail",
  "description": "Get detailed information about a specific captured screenshot, including full OCR text, AI-generated tags, and associated memory entities.",
  "parameters": {
    "type": "object",
    "properties": {
      "screenshot_id": {
        "type": "string",
        "description": "Screenshot ID from search results."
      }
    },
    "required": ["screenshot_id"]
  }
}
```

---

## 3. Database Schema

### 3.1 URI Graph Tables

```sql
-- Core graph: stable nodes
CREATE TABLE IF NOT EXISTS nodes (
  uuid TEXT PRIMARY KEY,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now') * 1000)
);

-- Content versions: append-only, newest non-deprecated is current
CREATE TABLE IF NOT EXISTS memories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  node_uuid TEXT NOT NULL,
  content TEXT NOT NULL,
  deprecated INTEGER NOT NULL DEFAULT 0,
  migrated_to INTEGER,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now') * 1000),
  FOREIGN KEY(node_uuid) REFERENCES nodes(uuid)
);
CREATE INDEX IF NOT EXISTS idx_memories_node_active
  ON memories(node_uuid, deprecated, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_created
  ON memories(created_at DESC);

-- Parent→child edges with priority and disclosure
CREATE TABLE IF NOT EXISTS edges (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  parent_uuid TEXT NOT NULL,
  child_uuid TEXT NOT NULL,
  name TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 0,
  disclosure TEXT,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now') * 1000),
  FOREIGN KEY(parent_uuid) REFERENCES nodes(uuid),
  FOREIGN KEY(child_uuid) REFERENCES nodes(uuid),
  UNIQUE(parent_uuid, child_uuid)
);
CREATE INDEX IF NOT EXISTS idx_edges_parent
  ON edges(parent_uuid, priority ASC, name);
CREATE INDEX IF NOT EXISTS idx_edges_child
  ON edges(child_uuid);

-- URI routing cache: domain://path → edge
CREATE TABLE IF NOT EXISTS paths (
  domain TEXT NOT NULL,
  path TEXT NOT NULL,
  edge_id INTEGER,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now') * 1000),
  PRIMARY KEY (domain, path),
  FOREIGN KEY(edge_id) REFERENCES edges(id)
);
CREATE INDEX IF NOT EXISTS idx_paths_edge ON paths(edge_id);
```

### 3.2 Signal Accumulation Tables

```sql
-- Entity records with scoring
CREATE TABLE IF NOT EXISTS memory_entities (
  entity_id TEXT PRIMARY KEY,
  root_uri TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  preferred_name TEXT NOT NULL,
  preferred_name_norm TEXT NOT NULL,
  canonical_key TEXT NOT NULL,
  display_uri TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'candidate',
  current_summary TEXT NOT NULL DEFAULT '',
  latest_content TEXT NOT NULL DEFAULT '',
  visual_signature_summary TEXT NOT NULL DEFAULT '',
  raw_score REAL NOT NULL DEFAULT 0,
  decayed_score REAL NOT NULL DEFAULT 0,
  activation_score REAL NOT NULL DEFAULT 0,
  evidence_count INTEGER NOT NULL DEFAULT 0,
  distinct_segment_count INTEGER NOT NULL DEFAULT 0,
  distinct_day_count INTEGER NOT NULL DEFAULT 0,
  strong_signal_count INTEGER NOT NULL DEFAULT 0,
  min_distinct_days INTEGER NOT NULL DEFAULT 1,
  allow_single_strong_activation INTEGER NOT NULL DEFAULT 0,
  allow_root_materialization INTEGER NOT NULL DEFAULT 0,
  evidence_satisfied INTEGER NOT NULL DEFAULT 0,
  ready_to_activate INTEGER NOT NULL DEFAULT 0,
  root_materialization_blocked INTEGER NOT NULL DEFAULT 0,
  missing_activation_score REAL NOT NULL DEFAULT 0,
  missing_distinct_days INTEGER NOT NULL DEFAULT 0,
  needs_review INTEGER NOT NULL DEFAULT 0,
  review_reason TEXT,
  first_seen_at INTEGER,
  last_seen_at INTEGER,
  activated_at INTEGER,
  archived_at INTEGER,
  last_materialized_at INTEGER,
  last_evidence_summary TEXT,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now') * 1000),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now') * 1000),
  UNIQUE(root_uri, entity_type, canonical_key),
  UNIQUE(display_uri)
);
CREATE INDEX IF NOT EXISTS idx_entities_root_status
  ON memory_entities(root_uri, status, decayed_score DESC, last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_entities_status_seen
  ON memory_entities(status, last_seen_at DESC);

-- Per-episode evidence records
CREATE TABLE IF NOT EXISTS memory_signal_episodes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id TEXT NOT NULL,
  root_uri TEXT NOT NULL,
  uri TEXT NOT NULL,
  segment_id INTEGER NOT NULL,
  batch_index INTEGER NOT NULL DEFAULT 0,
  first_seen_at INTEGER NOT NULL,
  last_seen_at INTEGER NOT NULL,
  score REAL NOT NULL DEFAULT 0,
  strong_signal INTEGER NOT NULL DEFAULT 0,
  action_kind TEXT NOT NULL DEFAULT '',
  evidence_summary TEXT,
  app_names_json TEXT,
  content_snapshot TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now') * 1000),
  UNIQUE(entity_id, segment_id, batch_index)
);
CREATE INDEX IF NOT EXISTS idx_episodes_entity_seen
  ON memory_signal_episodes(entity_id, last_seen_at DESC);

-- Entity aliases
CREATE TABLE IF NOT EXISTS memory_entity_aliases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id TEXT NOT NULL,
  alias TEXT NOT NULL,
  alias_text TEXT,
  alias_norm TEXT NOT NULL,
  alias_type TEXT NOT NULL DEFAULT 'semantic',
  confidence REAL NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now') * 1000),
  UNIQUE(entity_id, alias_norm)
);
CREATE INDEX IF NOT EXISTS idx_aliases_norm ON memory_entity_aliases(alias_norm);

-- Entity claims (facts)
CREATE TABLE IF NOT EXISTS memory_entity_claims (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  claim_id TEXT,
  entity_id TEXT NOT NULL,
  fact_type TEXT NOT NULL,
  slot_key TEXT,
  value TEXT NOT NULL,
  value_text TEXT,
  value_norm TEXT NOT NULL,
  cardinality TEXT NOT NULL DEFAULT 'multi',
  status TEXT NOT NULL DEFAULT 'active',
  confidence REAL NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  valid_from INTEGER,
  valid_to INTEGER,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now') * 1000),
  UNIQUE(entity_id, fact_type, slot_key, value_norm)
);

-- Review queue
CREATE TABLE IF NOT EXISTS memory_entity_reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  reason TEXT,
  suggested_action TEXT,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now') * 1000),
  resolved_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_reviews_status ON memory_entity_reviews(status, created_at DESC);
```

### 3.3 Screenshot & Index Tables

```sql
-- Screenshots
CREATE TABLE IF NOT EXISTS screenshots (
  id TEXT PRIMARY KEY,
  file_path TEXT NOT NULL UNIQUE,
  capture_time INTEGER NOT NULL,
  file_size INTEGER NOT NULL DEFAULT 0,
  width INTEGER,
  height INTEGER,
  app_name TEXT,
  app_package TEXT,
  ocr_text TEXT,
  is_deleted INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now') * 1000)
);
CREATE INDEX IF NOT EXISTS idx_screenshots_capture
  ON screenshots(capture_time DESC);
CREATE INDEX IF NOT EXISTS idx_screenshots_app
  ON screenshots(app_name, capture_time DESC);

-- FTS5 full-text index on OCR text
CREATE VIRTUAL TABLE IF NOT EXISTS screenshots_fts USING fts5(
  ocr_text,
  app_name,
  content='screenshots',
  content_rowid='rowid',
  prefix='2 3 4'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS screenshots_fts_ai AFTER INSERT ON screenshots
  BEGIN
    INSERT INTO screenshots_fts(rowid, ocr_text, app_name)
    VALUES (new.rowid, new.ocr_text, new.app_name);
  END;
CREATE TRIGGER IF NOT EXISTS screenshots_fts_ad AFTER DELETE ON screenshots
  BEGIN
    INSERT INTO screenshots_fts(screenshots_fts, rowid, ocr_text, app_name)
    VALUES ('delete', old.rowid, old.ocr_text, old.app_name);
  END;
CREATE TRIGGER IF NOT EXISTS screenshots_fts_au AFTER UPDATE ON screenshots
  BEGIN
    INSERT INTO screenshots_fts(screenshots_fts, rowid, ocr_text, app_name)
    VALUES ('delete', old.rowid, old.ocr_text, old.app_name);
    INSERT INTO screenshots_fts(rowid, ocr_text, app_name)
    VALUES (new.rowid, new.ocr_text, new.app_name);
  END;
```

---

## 4. Signal Accumulation Algorithm Specification

### 4.1 Decay Formula

For each entity, `decayed_score` is recomputed by iterating all episodes:

```
decayed_score = Σ ( episode_score × e^( -age_days / τ ) )
```

Where:
- `episode_score` = individual episode's score (typically 1.0)
- `age_days` = `(now_ms - episode.last_seen_at_ms) / 86400000`
- `τ` (tau) = `policy.decay_tau_days` (entity-type-specific)

### 4.2 Evidence Satisfaction

```
evidence_satisfied = (
    distinct_day_count >= policy.min_distinct_days
    OR (strong_signal_count > 0 AND policy.allow_single_strong_activation)
)
```

### 4.3 Activation Decision

```
ready_to_activate = (
    decayed_score >= policy.activation_score
    AND evidence_satisfied == True
    AND root_materialization_blocked == False
    AND needs_review == False
)
```

When `ready_to_activate` transitions from `False` to `True`:
1. Entity status changes: `candidate` → `active`
2. `activated_at` set to current timestamp
3. Materialization service writes entity content into URI Graph

### 4.4 Archival Decision

```
should_archive = (
    raw_score >= 1.2
    AND days_since_last_seen >= policy.archive_after_days
)
```

When archived:
1. Entity status changes: `active` → `archived`
2. `archived_at` set to current timestamp
3. URI Graph materialization updated (content marked as historical)

### 4.5 Policy Table

| entity_type | activation_score | min_distinct_days | allow_single_strong | decay_tau_days | archive_after_days | allow_root_materialization |
|-------------|-----------------|-------------------|---------------------|---------------|-------------------|---------------------------|
| identity | 1.4 | 1 | true | 180 | 240 | true |
| people | 2.0 | 2 | true | 150 | 180 | false |
| places | 2.0 | 2 | true | 90 | 120 | false |
| organizations | 2.0 | 2 | true | 150 | 180 | false |
| preferences | 1.4 | 1 | true | 120 | 180 | true |
| interests | 2.6 | 2 | false | 30 | 45 | false |
| projects | 1.8 | 2 | true | 90 | 120 | false |
| goals | 1.8 | 1 | true | 90 | 120 | false |
| habits | 2.8 | 3 | false | 60 | 90 | false |
| other | 3.0 | 2 | false | 60 | 90 | false |

### 4.6 Strong Signal Detection

An episode is a strong signal if its evidence text contains keywords from the entity type's `strong_keywords` list:

| entity_type | strong_keywords |
|-------------|----------------|
| identity | 职业, 身份, 擅长, 设备, 长期, 使用, 工作 |
| people | 朋友, 同事, 家人, 导师, 对象, 联系人, 客户, 长期 |
| places | 住在, 常去, 经常去, 公司, 学校, 家, 住所, 长期 |
| organizations | 公司, 学校, 团队, 社区, 品牌, 平台, 长期 |
| preferences | 喜欢, 偏好, 常用, 默认, 不喜欢, 讨厌, 倾向 |
| interests | 持续, 长期, 经常, 常看, 关注, 研究, 学习, 搜索, 收藏, 订阅, 反复 |
| projects | 项目, 开发, 维护, 版本, 需求, 计划, 正在 |
| goals | 目标, 计划, 打算, 准备, 想要, 希望 |
| habits | 每天, 每周, 习惯, 总是, 通常, 固定, 经常 |
| other | 长期, 持续, 反复, 稳定 |

---

## 5. Platform Adapter Interface

### 5.1 Abstract Interfaces

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class CaptureResult:
    file_path: str
    width: int
    height: int
    capture_time_ms: int
    app_name: Optional[str] = None
    app_package: Optional[str] = None

@dataclass
class OcrResult:
    text: str
    confidence: float
    blocks: list[dict]  # [{text, bbox, confidence}]
    source: str  # "system" | "ai"

class ScreenCaptureAdapter(ABC):
    @abstractmethod
    def capture(self, quality: int = 80,
                region: Optional[dict] = None) -> CaptureResult:
        ...

    @abstractmethod
    def start_timed_capture(self, interval_seconds: int = 30,
                            quality: int = 80) -> None:
        ...

    @abstractmethod
    def stop_timed_capture(self) -> None:
        ...

    @abstractmethod
    def is_capturing(self) -> bool:
        ...

class OcrAdapter(ABC):
    @abstractmethod
    def recognize(self, image_path: str) -> OcrResult:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...
```

### 5.2 Platform Implementations

| Platform | Capture | OCR |
|----------|---------|-----|
| Android | `AndroidAdbCapture` (adb screencap) or `AndroidAccessibilityCapture` (accessibility service) | `MlKitOcr` (via ML Kit) or `AiFallbackOcr` |
| Windows | `WinDwmCapture` (PIL ImageGrab + Win32 API for active window) | `WinRtOcr` (winrtocr) or `TesseractOcr` |
| macOS | `MacScreencaptureCapture` (screencapture CLI) | `VisionOcr` (pyobjc Vision framework) |
| Linux | `LinuxScrotCapture` (scrot/PIL) | `TesseractOcr` (pytesseract) |

### 5.3 AI Fallback OCR

```python
class AiFallbackOcr(OcrAdapter):
    """Delegates OCR to OpenClaw's LLM via multimodal input."""

    def __init__(self, openclaw_api):
        self._api = openclaw_api

    def recognize(self, image_path: str) -> OcrResult:
        response = self._api.ask(
            prompt="Extract all text from this image. Return only the text content.",
            image=image_path
        )
        return OcrResult(
            text=response.content,
            confidence=0.7,
            blocks=[],
            source="ai"
        )
```

---

## 6. Error Handling Strategy

### 6.1 Error Categories

| Category | Examples | Strategy |
|----------|----------|----------|
| **Platform unavailable** | No accessibility service, OCR not installed | Graceful degradation, return error with install instructions |
| **Storage** | SQLite locked, disk full | Retry with backoff (3 attempts), then fail with clear message |
| **AI call failure** | LLM timeout, rate limit | Exponential backoff, fall back to simpler processing |
| **Invalid input** | Bad URI format, missing required params | Immediate error with validation message |
| **Concurrency** | Simultaneous writes, capture conflicts | File locks on SQLite, queue-based serialization |

### 6.2 OCR Fallback Chain

```
1. Try system OCR (ML Kit / WinRT / Vision)
   ↓ if unavailable or confidence < 0.5
2. Try Tesseract (if installed)
   ↓ if unavailable or confidence < 0.3
3. Try AI multimodal (OpenClaw LLM)
   ↓ if unavailable
4. Store screenshot without OCR, mark for later processing
```

### 6.3 Tool Error Response Format

```json
{
  "success": false,
  "error": {
    "code": "CAPTURE_PLATFORM_UNAVAILABLE",
    "message": "Screen capture requires Android Accessibility Service or ADB. Enable Accessibility in Settings.",
    "details": {"platform": "android", "required": "accessibility_service"}
  }
}
```

Error codes:
- `CAPTURE_PLATFORM_UNAVAILABLE` - capture not supported on this platform/config
- `CAPTURE_PERMISSION_DENIED` - missing screen capture permission
- `OCR_NO_ENGINE` - no OCR engine available (system, tesseract, or AI)
- `MEMORY_URI_INVALID` - malformed URI
- `MEMORY_PARENT_NOT_FOUND` - parent URI does not exist
- `MEMORY_ENTITY_MANAGED` - attempted write on entity-managed URI
- `STORAGE_ERROR` - SQLite operation failed
- `SEARCH_NO_QUERY` - empty query provided

---

## 7. Plugin Registration

### 7.1 `openclaw.plugin.json`

```json
{
  "name": "screen-memory",
  "version": "0.1.0",
  "description": "Screen capture, OCR, and Nocturne URI Graph memory for OpenClaw",
  "runtime": "python",
  "entry": "screen_memory.plugin:register",
  "tools": [
    "screen_capture",
    "screen_capture_timed",
    "search_screen_memory",
    "read_memory",
    "create_memory",
    "update_memory",
    "delete_memory",
    "add_alias",
    "search_memory",
    "query_signals",
    "review_entity",
    "get_screenshot_detail"
  ],
  "permissions": [
    "screen_capture",
    "filesystem.read",
    "filesystem.write"
  ]
}
```

### 7.2 Python Entry Module

```python
# screen_memory/plugin.py

def register(api):
    """OpenClaw plugin registration entry point."""
    from .tools import register_all_tools
    register_all_tools(api)
```

---

## 8. Project Directory Structure

```
screen-memory/
├── openclaw.plugin.json
├── pyproject.toml
├── README.md
├── screen_memory/
│   ├── __init__.py
│   ├── plugin.py                    # register(api) entry point
│   ├── tools/
│   │   ├── __init__.py              # register_all_tools(api)
│   │   ├── capture_tools.py         # screen_capture, screen_capture_timed
│   │   ├── search_tools.py          # search_screen_memory, get_screenshot_detail
│   │   ├── memory_tools.py          # read/create/update/delete/add_alias/search_memory
│   │   └── entity_tools.py          # query_signals, review_entity
│   ├── services/
│   │   ├── __init__.py
│   │   ├── capture_service.py       # screenshot capture coordination
│   │   ├── ocr_service.py           # OCR fallback chain
│   │   ├── index_service.py         # FTS5 index management
│   │   ├── uri_graph_service.py     # Nocturne URI Graph CRUD
│   │   ├── signal_accumulator.py    # signal scoring + lifecycle
│   │   ├── entity_lifecycle.py      # candidate→active→archived
│   │   └── materialization.py       # entity → URI Graph materialization
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py              # SQLite connection + migrations
│   │   ├── graph_repo.py            # nodes/memories/edges/paths CRUD
│   │   ├── screenshot_repo.py       # screenshots table CRUD
│   │   ├── entity_repo.py           # memory_entities CRUD
│   │   └── signal_repo.py           # episodes + scoring queries
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py                  # abstract CaptureAdapter, OcrAdapter
│   │   ├── android_capture.py
│   │   ├── windows_capture.py
│   │   ├── macos_capture.py
│   │   ├── linux_capture.py
│   │   ├── mlkit_ocr.py
│   │   ├── winrt_ocr.py
│   │   ├── vision_ocr.py
│   │   ├── tesseract_ocr.py
│   │   └── ai_fallback_ocr.py
│   └── models/
│       ├── __init__.py
│       ├── uri.py                   # NocturneUri parsing/validation
│       ├── entity.py                # MemoryEntity, EntityPolicy
│       ├── screenshot.py            # Screenshot dataclass
│       └── signal.py                # SignalEpisode, SignalPolicy
└── tests/
    ├── __init__.py
    ├── conftest.py                  # shared fixtures (in-memory SQLite, temp dirs)
    ├── unit/
    │   ├── test_uri.py
    │   ├── test_uri_graph_service.py
    │   ├── test_signal_accumulator.py
    │   ├── test_entity_lifecycle.py
    │   ├── test_index_service.py
    │   └── test_ocr_service.py
    ├── integration/
    │   ├── test_capture_pipeline.py
    │   ├── test_memory_crud.py
    │   ├── test_signal_to_materialization.py
    │   └── test_search_pipeline.py
    └── tools/
        ├── test_capture_tools.py
        ├── test_search_tools.py
        ├── test_memory_tools.py
        └── test_entity_tools.py
```

---

## 9. Test Case Design

### 9.1 Unit Tests

#### `test_uri.py`

| # | Test Case | Input | Expected |
|---|-----------|-------|----------|
| 1 | Parse valid URI | `"core://my_user/identity"` | domain="core", path="my_user/identity" |
| 2 | Parse root URI | `"core://"` | domain="core", path="" |
| 3 | Reject invalid URI | `"not_a_uri"` | raises `ValueError` |
| 4 | Reject empty domain | `"://path"` | raises `ValueError` |
| 5 | Normalize URI | `"core://my_user/"` | trailing slash stripped |
| 6 | URI equality | `"core://a"` vs `"core://a"` | equal |
| 7 | URI parent detection | `"core://a/b"` parent of `"core://a"` | true |
| 8 | Parse system URI | `"system://boot"` | domain="system", path="boot" |

#### `test_uri_graph_service.py`

| # | Test Case | Setup | Action | Expected |
|---|-----------|-------|--------|----------|
| 1 | Create root node | empty DB | `create_memory("core://", "test")` | node created, readable via `read_memory("core://")` |
| 2 | Create child node | root exists | `create_memory("core://agent", "content", parent="core://")` | edge created, path resolves |
| 3 | Create deep path | "core://a" exists | `create_memory("core://a/b/c", "deep")` | all intermediate nodes + edges + paths created |
| 4 | Read non-existent | empty DB | `read_memory("core://missing")` | returns `None` or empty result |
| 5 | Update via patch | node with "hello world" | `update_memory(uri, old="hello", new="hi")` | content becomes "hi world" |
| 6 | Update via append | node with "line1" | `update_memory(uri, append="\nline2")` | content becomes "line1\nline2" |
| 7 | Patch ambiguous | node with "abc abc" | `update_memory(uri, old="abc", new="x")` | raises error (multiple matches) |
| 8 | Delete node | node with children | `delete_memory(uri)` | path removed, children paths removed |
| 9 | Add alias | node at "core://a" | `add_alias("core://b", "core://a")` | read_memory("core://b") returns same content |
| 10 | Search by keyword | 3 nodes | `search_memory("keyword")` | returns matching nodes only |
| 11 | Content versioning | node with content | update twice | 3 versions in memories table, only latest active |
| 12 | Priority ordering | 3 children with priorities | read parent | children returned in priority order |

#### `test_signal_accumulator.py`

| # | Test Case | Setup | Action | Expected |
|---|-----------|-------|--------|----------|
| 1 | Single episode | new entity | record 1 episode | raw_score=1, decayed_score≈1 |
| 2 | Same-day duplicates | entity exists | record 2 episodes same day | distinct_day_count=1, raw_score=2 |
| 3 | Multi-day evidence | entity exists | record episodes across 2 days | distinct_day_count=2 |
| 4 | Decay calculation | episode 30 days ago, τ=30 | refresh signals | decayed_score ≈ raw × e^(-1) ≈ 0.368 |
| 5 | Activation threshold | people entity, score=2.1, days=2 | refresh signals | ready_to_activate=True, status→active |
| 6 | Below threshold | people entity, score=1.5, days=2 | refresh signals | ready_to_activate=False, stays candidate |
| 7 | Single strong signal | identity, 1 strong episode | refresh signals | evidence_satisfied=True (allow_single_strong=true) |
| 8 | No single strong for habits | habits, 1 strong episode, days=1 | refresh signals | evidence_satisfied=False (allow_single_strong=false) |
| 9 | Archival | active entity, 200 days since last seen | refresh signals | status→archived |
| 10 | Missing score tracking | entity score=1.0, threshold=2.0 | refresh signals | missing_activation_score=1.0 |

#### `test_entity_lifecycle.py`

| # | Test Case | Setup | Action | Expected |
|---|-----------|-------|--------|----------|
| 1 | Candidate→Active | entity at threshold | trigger refresh | status becomes "active", activated_at set |
| 2 | Active→Archived | entity not seen for archive_after_days | trigger refresh | status becomes "archived", archived_at set |
| 3 | Review queue | borderline entity | trigger refresh | needs_review=True, review queue entry created |
| 4 | Approve review | review queue item | approve | entity materialized, review resolved |
| 5 | Dismiss review | review queue item | dismiss | entity dropped, review resolved |
| 6 | Root materialization block | root entity, policy disallows | trigger refresh | root_materialization_blocked=True |

#### `test_index_service.py`

| # | Test Case | Setup | Action | Expected |
|---|-----------|-------|--------|----------|
| 1 | Index screenshot | screenshot with OCR text | index | FTS search finds it |
| 2 | Search CJK text | screenshot with "你好世界" | search("你好") | returns match |
| 3 | Search by app name | 2 screenshots, different apps | search("query", app_name="WeChat") | only WeChat results |
| 4 | Time range filter | screenshots across 3 days | search with start/end | only results in range |
| 5 | Pagination | 30 screenshots | search(limit=10, offset=0) | returns 10, has_more=True |
| 6 | Update OCR text | indexed screenshot | update OCR | old FTS entry removed, new one added |
| 7 | Delete screenshot | indexed screenshot | delete | FTS entry removed |

#### `test_ocr_service.py`

| # | Test Case | Setup | Action | Expected |
|---|-----------|-------|--------|----------|
| 1 | System OCR available | mock system OCR returning text | recognize | returns result with source="system" |
| 2 | System OCR unavailable | mock system OCR raises, AI available | recognize | falls back to AI, source="ai" |
| 3 | All OCR unavailable | mock all OCRs unavailable | recognize | raises `OcrError` |
| 4 | Low confidence fallback | system OCR confidence=0.3, AI available | recognize | tries tesseract, then AI |

### 9.2 Integration Tests

#### `test_capture_pipeline.py`

| # | Test Case | Flow | Expected |
|---|-----------|------|----------|
| 1 | Capture → OCR → Index | capture screenshot → OCR → index → search | search finds the captured content |
| 2 | Duplicate detection | capture same screen twice | second capture skipped or deduplicated |
| 3 | Timed capture lifecycle | start → wait → stop | captures recorded, status correct |

#### `test_memory_crud.py`

| # | Test Case | Flow | Expected |
|---|-----------|------|----------|
| 1 | Full CRUD cycle | create → read → update → read → delete → read | each step returns correct state |
| 2 | Aliased read | create → add_alias → read via alias | same content as original |
| 3 | Deep hierarchy | create root → create 3 children → read root | all 3 children listed |

#### `test_signal_to_materialization.py`

| # | Test Case | Flow | Expected |
|---|-----------|------|----------|
| 1 | Full lifecycle | seed episodes across days → refresh → auto-activate → materialize | entity becomes active, URI Graph node created |
| 2 | Review intervention | seed borderline entity → review queue → approve | entity materialized after approval |
| 3 | Archival + cleanup | archive old entity → verify URI Graph updated | archived content in URI Graph |

#### `test_search_pipeline.py`

| # | Test Case | Flow | Expected |
|---|-----------|------|----------|
| 1 | Capture → search | capture 5 screenshots → search by keyword | correct subset returned |
| 2 | Memory + screenshot search | create memory → search both | both sources returned |
| 3 | Time-bounded search | capture over 3 days → search 1 day | only that day's results |

### 9.3 Tool Tests

#### `test_capture_tools.py`

| # | Test Case | Mock | Expected |
|---|-----------|------|----------|
| 1 | screen_capture success | CaptureAdapter returning result | returns CaptureResult JSON |
| 2 | screen_capture platform unavailable | CaptureAdapter raising error | returns error response with code |
| 3 | screen_capture_timed start | CaptureAdapter mock | returns running status |
| 4 | screen_capture_timed stop | running capture | returns stopped status |

#### `test_memory_tools.py`

| # | Test Case | Mock | Expected |
|---|-----------|------|----------|
| 1 | read_memory valid URI | URI Graph with data | returns content + children |
| 2 | read_memory system://boot | boot data populated | returns boot context |
| 3 | create_memory missing parent | URI Graph without parent | returns PARENT_NOT_FOUND error |
| 4 | create_memory success | parent exists | returns created URI |
| 5 | update_memory patch | content with old_string | returns updated content |
| 6 | update_memory ambiguous patch | content with 2 matches | returns error |
| 7 | delete_memory with children | node with children | all paths removed |
| 8 | add_alias then read | aliased node | read via alias returns same content |
| 9 | search_memory | 5 nodes, 2 matching | returns 2 results |

#### `test_entity_tools.py`

| # | Test Case | Mock | Expected |
|---|-----------|------|----------|
| 1 | query_signals all | 10 entities mixed status | returns all with counts |
| 2 | query_signals by type | entities of different types | returns only matching type |
| 3 | review_entity approve | candidate in review queue | entity becomes active |
| 4 | review_entity dismiss | candidate in review queue | entity removed |

---

## 10. Configuration

### 10.1 Plugin Config Schema

```python
# config.yaml (in plugin directory or OpenClaw config)
screen_memory:
  database_path: "~/.screenmemory/db.sqlite"
  screenshot_dir: "~/.screenmemory/screenshots"
  capture:
    default_quality: 80
    default_interval_seconds: 30
    duplicate_hash: true       # SHA-256 dedup
    max_screenshot_age_days: 365
  ocr:
    preferred_engine: "auto"   # auto | system | tesseract | ai
    min_confidence: 0.5
    ai_fallback: true
  signals:
    auto_materialize: true     # auto-activate when threshold met
    review_threshold_score: 0.8  # flag for review if below this
    refresh_interval_seconds: 300
  indexing:
    fts_enabled: true
    cjk_optimized: true
    prefix_sizes: [2, 3, 4]
```
