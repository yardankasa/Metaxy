from __future__ import annotations

import uuid

from fastapi import FastAPI, Request

from api.handlers import router


def create_app(container) -> FastAPI:
    app = FastAPI(title="Metaxy | Proxy Health Pool", version="0.1.0")
    app.state.container = container

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex
        return await call_next(request)

    app.include_router(router)
    return app
