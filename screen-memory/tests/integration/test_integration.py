"""Integration tests: end-to-end scenarios across all layers.

Tests exercise the full pipeline: capture → OCR → index → graph → signal → tool query.
"""

import pytest

from screen_memory.adapters.capture import CaptureResult, ScreenCapture
from screen_memory.adapters.ocr import OCRChain, OCRResult
from screen_memory.models.uri import NocturneUri
from screen_memory.storage.database import Database
from screen_memory.storage.graph_repo import GraphRepo
from screen_memory.storage.screenshot_repo import ScreenshotRepo
from screen_memory.services.graph_service import GraphService
from screen_memory.services.index_service import IndexService
from screen_memory.services.signal_service import SignalService, EntityPolicy
from screen_memory.tools.registry import ToolRegistry


class _StubCapture(ScreenCapture):
    _n = 0

    def capture(self) -> CaptureResult:
        _StubCapture._n += 1
        return CaptureResult(
            image_data=b"fake-screenshot",
            file_path=f"/tmp/screen_{_StubCapture._n}.png",
        )


class _StubOCR:
    def __init__(self, text: str):
        self._text = text

    def is_available(self) -> bool:
        return True

    def recognize(self, image_data: bytes) -> OCRResult:
        return OCRResult(text=self._text, confidence=0.95, engine="stub")


@pytest.fixture
def system():
    """Wire up the full system."""
    db = Database(":memory:")
    db.initialize()
    repo = GraphRepo(db)
    ss_repo = ScreenshotRepo(db)
    graph_svc = GraphService(repo)
    policies = {
        "person": EntityPolicy("person", 3.0, 86400 * 7, ["seen_multiple_times"]),
        "topic": EntityPolicy("topic", 2.0, 86400 * 3, []),
    }
    signal_svc = SignalService(repo, policies)
    capture = _StubCapture()
    ocr = OCRChain([_StubOCR("Meeting with Alice about AI project")])
    index_svc = IndexService(repo, ss_repo, capture, ocr)
    registry = ToolRegistry(graph_svc, signal_svc, ss_repo)
    return {
        "db": db,
        "repo": repo,
        "ss_repo": ss_repo,
        "graph_svc": graph_svc,
        "signal_svc": signal_svc,
        "index_svc": index_svc,
        "registry": registry,
    }


# -- Scenario 1: Write memories and query subtree ---------------------------


class TestMemorySubtreeScenario:
    def test_write_and_query_hierarchy(self, system):
        reg = system["registry"]
        reg.call("memory_write", {"uri": "core://project/x", "content": "Project X overview"})
        reg.call("memory_write", {"uri": "core://project/x/tasks", "content": "Task list"})
        reg.call("memory_write", {"uri": "core://project/x/tasks/t1", "content": "Task 1: design"})
        reg.call("memory_write", {"uri": "core://project/x/notes", "content": "Meeting notes"})

        tree = reg.call("graph_query_subtree", {"uri": "core://project/x"})
        assert tree["uri"] == "core://project/x"
        assert len(tree["children"]) == 2  # tasks + notes
        tasks = next(c for c in tree["children"] if "tasks" in c["uri"])
        assert len(tasks["children"]) == 1  # t1

    def test_search_across_hierarchy(self, system):
        reg = system["registry"]
        reg.call("memory_write", {"uri": "core://a", "content": "Python programming"})
        reg.call("memory_write", {"uri": "core://b", "content": "JavaScript frameworks"})
        reg.call("memory_write", {"uri": "core://c", "content": "Python data science"})

        results = reg.call("memory_search", {"query": "Python"})
        assert len(results) == 2


# -- Scenario 2: Capture → OCR → index → search -----------------------------


class TestCaptureIndexScenario:
    def test_capture_and_search(self, system):
        index = system["index_svc"]
        result = index.capture_and_index(link_uri="core://screenshots/1")
        assert result["ocr_text"] == "Meeting with Alice about AI project"

        results = index.search_memories("Alice")
        assert len(results) >= 1

    def test_screenshot_search(self, system):
        index = system["index_svc"]
        index.capture_and_index()
        results = index.search_screenshots("Alice")
        assert len(results) == 1


# -- Scenario 3: Signal accumulation → activation → graph materialization --


class TestSignalLifecycleScenario:
    def test_person_lifecycle(self, system):
        reg = system["registry"]
        # Ingest signals
        for i in range(5):
            reg.call("signal_ingest", {
                "entity_type": "person",
                "entity_name": "Alice",
                "source": "screenshot",
                "evidence": ["seen_multiple_times"],
            })

        # Activate
        result = reg.call("signal_activate", {"entity_name": "Alice"})
        assert result["status"] == "active"

        # Should be searchable in graph
        mem_results = reg.call("memory_search", {"query": "Alice"})
        assert len(mem_results) >= 1

    def test_topic_activation_simple(self, system):
        reg = system["registry"]
        # Topic has lower threshold (2.0) and no required evidence
        reg.call("signal_ingest", {
            "entity_type": "topic",
            "entity_name": "Machine Learning",
            "source": "chat",
        })
        reg.call("signal_ingest", {
            "entity_type": "topic",
            "entity_name": "Machine Learning",
            "source": "screenshot",
        })

        result = reg.call("signal_activate", {"entity_name": "Machine Learning"})
        assert result["status"] == "active"

    def test_archived_not_in_active_list(self, system):
        signal = system["signal_svc"]
        signal.ingest_signal("topic", "Old Topic", "chat")
        signal.archive("Old Topic")
        active = signal.list_entities(status="candidate")
        assert all(e["name"] != "Old Topic" for e in active)


# -- Scenario 4: Memory versioning ------------------------------------------


class TestMemoryVersioningScenario:
    def test_read_always_latest(self, system):
        reg = system["registry"]
        reg.call("memory_write", {"uri": "core://doc", "content": "version 1"})
        reg.call("memory_write", {"uri": "core://doc", "content": "version 2"})
        reg.call("memory_write", {"uri": "core://doc", "content": "version 3"})

        result = reg.call("memory_read", {"uri": "core://doc"})
        assert result["content"] == "version 3"
        assert result["version"] == 3

    def test_delete_removes_all(self, system):
        reg = system["registry"]
        reg.call("memory_write", {"uri": "core://temp", "content": "temp data"})
        reg.call("memory_write", {"uri": "core://temp", "content": "updated temp"})
        reg.call("memory_delete", {"uri": "core://temp"})
        assert reg.call("memory_read", {"uri": "core://temp"}) is None


# -- Scenario 5: Plugin registration ----------------------------------------


class TestPluginRegistrationScenario:
    def test_register_and_use(self, system):
        tools = system["registry"].list_tools()
        assert len(tools) == 8
        # Each tool has OpenClaw-compatible schema
        for t in tools:
            assert "name" in t
            assert "description" in t
            assert "parameters" in t
            params = t["parameters"]
            assert "type" in params
            assert params["type"] == "object"
