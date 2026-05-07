"""OpenClaw plugin entry point for screen-memory."""

from screen_memory.tools.registry import ToolRegistry


def register(api) -> ToolRegistry:
    """Called by OpenClaw to register screen-memory tools.

    ``api`` provides the database path and platform configuration::

        registry = register(api)
        for tool in registry.list_tools():
            api.register_tool(tool)
    """
    db_path = getattr(api, "db_path", ":memory:")
    from screen_memory.storage.database import Database
    from screen_memory.storage.graph_repo import GraphRepo
    from screen_memory.storage.screenshot_repo import ScreenshotRepo
    from screen_memory.services.graph_service import GraphService
    from screen_memory.services.signal_service import SignalService, EntityPolicy

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
