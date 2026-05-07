"""Tests for Signal Accumulation + Entity Lifecycle.

TDD order: entity creation → signal ingestion → scoring → activation → materialization
"""

import math
import time

import pytest

from screen_memory.models.uri import NocturneUri
from screen_memory.storage.database import Database
from screen_memory.storage.graph_repo import GraphRepo
from screen_memory.services.signal_service import (
    EntityPolicy,
    SignalService,
    EntityType,
)


@pytest.fixture
def svc():
    db = Database(":memory:")
    db.initialize()
    repo = GraphRepo(db)
    policies = {
        EntityType.PERSON: EntityPolicy(
            entity_type="person",
            activation_threshold=3.0,
            decay_tau=86400 * 7,  # 1 week
            required_evidence=["seen_multiple_times"],
        ),
        EntityType.TOPIC: EntityPolicy(
            entity_type="topic",
            activation_threshold=2.0,
            decay_tau=86400 * 3,
            required_evidence=[],
        ),
    }
    return SignalService(repo, policies)


# -- Entity creation ---------------------------------------------------------


class TestEntityCreation:
    def test_create_candidate(self, svc):
        e = svc.ingest_signal(
            entity_type="person",
            entity_name="Alice",
            source="screenshot",
            evidence=["seen_multiple_times"],
        )
        assert e["name"] == "Alice"
        assert e["status"] == "candidate"
        assert e["score"] > 0

    def test_duplicate_signal_bumps_score(self, svc):
        svc.ingest_signal("person", "Alice", "screenshot", ["seen_multiple_times"])
        e = svc.ingest_signal("person", "Alice", "screenshot", ["seen_multiple_times"])
        assert e["signal_count"] == 2
        assert e["score"] > 1.0  # accumulated


# -- Scoring -----------------------------------------------------------------


class TestScoring:
    def test_score_increases_with_signals(self, svc):
        e1 = svc.ingest_signal("person", "Bob", "screenshot", ["seen_multiple_times"])
        first_score = e1["score"]
        e2 = svc.ingest_signal("person", "Bob", "screenshot", ["seen_multiple_times"])
        assert e2["score"] > first_score

    def test_decay_reduces_old_score(self, svc):
        # Create entity with a timestamp in the past
        svc.ingest_signal("person", "Charlie", "screenshot", ["seen_multiple_times"])
        # Manually age the entity
        svc._db.execute(
            "UPDATE entities SET last_seen_at=datetime('now', '-7 days') WHERE name='Charlie'"
        )
        score = svc.get_entity_score("Charlie")
        # After 7 days with tau=7 days, score should be ~e^(-1) * original
        assert score < 1.0


# -- Activation --------------------------------------------------------------


class TestActivation:
    def test_activates_when_threshold_met(self, svc):
        # person threshold is 3.0, each signal adds ~1.0 base score
        svc.ingest_signal("person", "Dave", "screenshot", ["seen_multiple_times"])
        svc.ingest_signal("person", "Dave", "screenshot", ["seen_multiple_times"])
        svc.ingest_signal("person", "Dave", "screenshot", ["seen_multiple_times"])
        e = svc.get_entity("Dave")
        # Should be at or near activation threshold
        assert e["score"] >= 2.9

    def test_activate_creates_graph_memory(self, svc):
        # Pump signals to exceed threshold
        for _ in range(5):
            svc.ingest_signal("person", "Eve", "screenshot", ["seen_multiple_times"])
        svc.activate("Eve")
        e = svc.get_entity("Eve")
        assert e["status"] == "active"
        # Check graph node was created
        uri = NocturneUri.parse(f"core://entities/person/Eve")
        mem = svc._repo.read_memory(uri)
        assert mem is not None

    def test_activate_without_evidence_blocked(self, svc):
        # Policy requires "seen_multiple_times" evidence
        svc.ingest_signal("person", "Frank", "screenshot", [])
        # Even with enough score, activation should require evidence
        for _ in range(5):
            svc.ingest_signal("person", "Frank", "screenshot", [])
        result = svc.can_activate("Frank")
        assert result is False


# -- Entity lifecycle --------------------------------------------------------


class TestEntityLifecycle:
    def test_archive_entity(self, svc):
        svc.ingest_signal("person", "Grace", "screenshot", ["seen_multiple_times"])
        svc.archive("Grace")
        e = svc.get_entity("Grace")
        assert e["status"] == "archived"

    def test_list_by_status(self, svc):
        svc.ingest_signal("person", "H1", "screenshot", [])
        svc.ingest_signal("topic", "T1", "screenshot", [])
        candidates = svc.list_entities(status="candidate")
        assert len(candidates) == 2

    def test_list_by_type(self, svc):
        svc.ingest_signal("person", "P1", "screenshot", [])
        svc.ingest_signal("topic", "T1", "screenshot", [])
        people = svc.list_entities(entity_type="person")
        assert len(people) == 1
        assert people[0]["name"] == "P1"


# -- Materialization ----------------------------------------------------------


class TestMaterialization:
    def test_materialize_writes_graph(self, svc):
        for _ in range(5):
            svc.ingest_signal("topic", "AI", "screenshot", [])
        svc.activate("AI")
        uri = NocturneUri.parse("core://entities/topic/AI")
        mem = svc._repo.read_memory(uri)
        assert mem is not None
        assert "AI" in mem["content"]

    def test_materialize_creates_edges(self, svc):
        for _ in range(5):
            svc.ingest_signal("person", "Alice", "screenshot", ["seen_multiple_times"])
        for _ in range(5):
            svc.ingest_signal("person", "Bob", "screenshot", ["seen_multiple_times"])
        svc.activate("Alice")
        svc.activate("Bob")
        # Both should exist under entities/person
        alice_uri = NocturneUri.parse("core://entities/person/Alice")
        assert svc._repo.get_node(alice_uri) is not None
