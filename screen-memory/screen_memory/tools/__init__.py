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
    from screen_memory.sync.config import SyncConfig
    from screen_memory.sync.client import SyncClient
    from screen_memory.sync.query_bridge import QueryBridge

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
    registry = ToolRegistry(graph_svc, signal_svc, ss_repo)

    sync_cfg = SyncConfig.from_env()
    if sync_cfg.enabled:
        client = SyncClient(db, sync_cfg.server_url, sync_cfg.token, sync_cfg.interval)
        bridge = QueryBridge(sync_cfg.server_url, sync_cfg.token, client.get_device_id())
        registry.set_sync_client(client)
        registry.set_query_bridge(bridge)
        client.start()

    return registry
