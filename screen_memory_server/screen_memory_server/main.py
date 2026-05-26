"""FastAPI sync server for cross-device screen memory."""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel

from screen_memory_server.db import SyncDatabase
from screen_memory_server.config import SyncConfig


class PushRequest(BaseModel):
    device_id: str
    tables: dict[str, list[dict]]


class QueryRequest(BaseModel):
    device_id: str
    table: str
    query: dict = {}
    exclude_self: bool = True


def create_app(config_path: Optional[str] = None, auth_token: Optional[str] = None, db_path: Optional[str] = None) -> FastAPI:
    if config_path:
        cfg = SyncConfig.from_yaml(config_path)
    else:
        cfg = SyncConfig()

    token = auth_token or cfg.auth_token
    database_path = db_path or cfg.db_path
    db = SyncDatabase(database_path)
    db.initialize()

    app = FastAPI(title="Screen Memory Sync Server")
    app.state.db = db

    def _check_auth(authorization: Optional[str] = Header(None)):
        if not authorization:
            raise HTTPException(status_code=401, detail="Missing authorization")
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Invalid authorization format")
        if authorization[7:] != token:
            raise HTTPException(status_code=401, detail="Invalid token")

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/v1/sync/push")
    def push(req: PushRequest, authorization: Optional[str] = Header(None)):
        _check_auth(authorization)
        received = {}
        for table, records in req.tables.items():
            count = db.push_records(req.device_id, table, records)
            received[table] = count
        return {"ok": True, "received": received}

    @app.post("/api/v1/sync/query")
    def query(req: QueryRequest, authorization: Optional[str] = Header(None)):
        _check_auth(authorization)
        exclude = req.device_id if req.exclude_self else None
        results = db.query_records(req.table, exclude_device=exclude)
        return {"results": results}

    @app.get("/api/v1/sync/status")
    def status(device_id: str = Query(...), authorization: Optional[str] = Header(None)):
        _check_auth(authorization)
        devices = db.get_status()
        return {"devices": devices}

    return app


def main():
    import uvicorn
    cfg = SyncConfig.from_yaml("config.yaml")
    app = create_app(config_path="config.yaml")
    uvicorn.run(app, host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
