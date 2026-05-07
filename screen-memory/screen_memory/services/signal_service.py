"""Signal Accumulation + Entity Lifecycle Service.

Entities progress: candidate → active → archived.
Signals accumulate with exponential decay scoring.
On activation, entities are materialized into the URI Graph.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Optional

from screen_memory.models.uri import NocturneUri
from screen_memory.storage.database import Database
from screen_memory.storage.graph_repo import GraphRepo


class EntityType:
    PERSON = "person"
    TOPIC = "topic"
    LOCATION = "location"
    EVENT = "event"


@dataclass
class EntityPolicy:
    entity_type: str
    activation_threshold: float
    decay_tau: float  # seconds
    required_evidence: list[str]


class SignalService:
    def __init__(
        self,
        repo: GraphRepo,
        policies: Optional[dict[str, EntityPolicy]] = None,
        base_signal_score: float = 1.0,
    ) -> None:
        self._repo = repo
        self._db: Database = repo._db
        self._policies = policies or {}
        self._base_score = base_signal_score

    # -- Signal ingestion -----------------------------------------------------

    def ingest_signal(
        self,
        entity_type: str,
        entity_name: str,
        source: str,
        evidence: Optional[list[str]] = None,
    ) -> dict:
        """Ingest a signal for an entity. Creates or updates the entity."""
        evidence = evidence or []
        row = self._db.execute(
            "SELECT id, score, signal_count, evidence FROM entities "
            "WHERE entity_type=? AND name=?",
            (entity_type, entity_name),
        ).fetchone()

        if row is None:
            self._db.execute(
                "INSERT INTO entities (entity_type, name, score, signal_count, evidence, status) "
                "VALUES (?, ?, ?, 1, ?, 'candidate')",
                (entity_type, entity_name, self._base_score, json.dumps(evidence)),
            )
            return self.get_entity(entity_name)

        eid, old_score, count, old_evidence_json = row
        old_evidence = json.loads(old_evidence_json)
        merged_evidence = list(set(old_evidence + evidence))
        new_count = count + 1

        # Apply decay + new signal
        age = self._get_age_seconds(entity_name)
        policy = self._policies.get(entity_type)
        tau = policy.decay_tau if policy else 86400 * 7
        decayed = old_score * math.exp(-age / tau)
        new_score = decayed + self._base_score

        self._db.execute(
            "UPDATE entities SET score=?, signal_count=?, evidence=?, "
            "last_seen_at=datetime('now'), updated_at=datetime('now') WHERE id=?",
            (new_score, new_count, json.dumps(merged_evidence), eid),
        )
        return self.get_entity(entity_name)

    # -- Scoring --------------------------------------------------------------

    def get_entity_score(self, name: str) -> float:
        row = self._db.execute(
            "SELECT score, entity_type FROM entities WHERE name=?", (name,)
        ).fetchone()
        if row is None:
            return 0.0
        score, entity_type = row
        policy = self._policies.get(entity_type)
        if not policy:
            return score
        age = self._get_age_seconds(name)
        return score * math.exp(-age / policy.decay_tau)

    def _get_age_seconds(self, name: str) -> float:
        """Get seconds since last_seen_at for an entity."""
        row = self._db.execute(
            "SELECT CAST((julianday('now') - julianday(last_seen_at)) * 86400 AS INTEGER) FROM entities WHERE name=?",
            (name,),
        ).fetchone()
        if row is None or row[0] is None:
            return 0.0
        return max(0, row[0])

    # -- Activation -----------------------------------------------------------

    def can_activate(self, name: str) -> bool:
        row = self._db.execute(
            "SELECT entity_type, evidence, status FROM entities WHERE name=?",
            (name,),
        ).fetchone()
        if row is None:
            return False
        entity_type, evidence_json, status = row
        if status != "candidate":
            return False
        score = self.get_entity_score(name)
        policy = self._policies.get(entity_type)
        if not policy:
            return score > 0
        if score < policy.activation_threshold:
            return False
        evidence = json.loads(evidence_json)
        for req in policy.required_evidence:
            if req not in evidence:
                return False
        return True

    def activate(self, name: str) -> dict:
        """Activate an entity and materialize it into the graph."""
        if not self.can_activate(name):
            raise ValueError(f"Entity '{name}' cannot be activated yet")
        row = self._db.execute(
            "SELECT entity_type, score, evidence FROM entities WHERE name=?", (name,)
        ).fetchone()
        entity_type, score, evidence_json = row
        self._db.execute(
            "UPDATE entities SET status='active', updated_at=datetime('now') WHERE name=?",
            (name,),
        )
        # Materialize into graph
        uri = NocturneUri.make("core", f"entities/{entity_type}/{name}")
        content = f"Entity: {name} (type: {entity_type}, score: {score:.2f})"
        if evidence_json != "[]":
            evidence = json.loads(evidence_json)
            content += f" | Evidence: {', '.join(evidence)}"
        self._repo.write_memory(uri, content)
        return self.get_entity(name)

    # -- Archive --------------------------------------------------------------

    def archive(self, name: str) -> dict:
        self._db.execute(
            "UPDATE entities SET status='archived', updated_at=datetime('now') WHERE name=?",
            (name,),
        )
        return self.get_entity(name)

    # -- Queries --------------------------------------------------------------

    def get_entity(self, name: str) -> Optional[dict]:
        row = self._db.execute(
            "SELECT id, entity_type, name, status, score, signal_count, evidence, "
            "first_seen_at, last_seen_at FROM entities WHERE name=?",
            (name,),
        ).fetchone()
        if row is None:
            return None
        keys = [
            "id", "entity_type", "name", "status", "score", "signal_count",
            "evidence", "first_seen_at", "last_seen_at",
        ]
        result = dict(zip(keys, row))
        result["evidence"] = json.loads(result["evidence"])
        return result

    def list_entities(
        self,
        status: Optional[str] = None,
        entity_type: Optional[str] = None,
    ) -> list[dict]:
        sql = "SELECT id, entity_type, name, status, score, signal_count FROM entities WHERE 1=1"
        params: list = []
        if status:
            sql += " AND status=?"
            params.append(status)
        if entity_type:
            sql += " AND entity_type=?"
            params.append(entity_type)
        rows = self._db.execute(sql, tuple(params)).fetchall()
        keys = ["id", "entity_type", "name", "status", "score", "signal_count"]
        return [dict(zip(keys, r)) for r in rows]
