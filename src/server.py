"""FastAPI + uvicorn server for the SlimTorq simulator.

- :func:`get_app` — lazily build and cache the :class:`FastAPI` instance.
- :func:`get_server` — lazily build and cache the :class:`uvicorn.Server`
  using the ``app`` block of the package-level config.
- :func:`run` — ``await`` the server.

The two-step /api/simulate flow keeps each response cleanly typed:

    POST /api/simulate              -> JSON meta + params_hash (small)
    GET  /api/simulate/{hash}/data  -> Arrow IPC stream of the DataFrame (large)

The Arrow IPC body is decoded zero-copy in the browser by ``apache-arrow``
and fed straight into ECharts series. Parquet artifacts are also served
via GET /api/artifacts/{hash}.parquet for external tooling (polars,
duckdb, …).

The Next.js frontend's static export (``frontend/out/``) is mounted at
``/``, so a single container serves both the UI and the API on one port.
"""

from __future__ import annotations

import io

import polars as pl
import pyarrow as pa
import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src import get_config
from src.model import CatalogResponse, CatalogVariant, SimMeta, SimParams
from src.simulator import CATALOG, artifact_by_hash, run_simulation

ARROW_MIME = "application/vnd.apache.arrow.stream"

__app__: FastAPI | None = None
__server__: uvicorn.Server | None = None


def _build_api_router() -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/health")
    def health() -> dict:
        return {"ok": True}

    @router.get("/catalog", response_model=CatalogResponse)
    def catalog() -> CatalogResponse:
        return CatalogResponse(variants=[CatalogVariant.from_pmsm_model(m) for _, m in sorted(CATALOG.items())])

    @router.get("/defaults", response_model=SimParams)
    def defaults() -> SimParams:
        return SimParams()

    @router.post("/simulate", response_model=SimMeta)
    def simulate(params: SimParams) -> SimMeta:
        try:
            _df, meta = run_simulation(params)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return meta

    @router.get("/simulate/{hash_str}/data")
    def simulate_data(hash_str: str) -> Response:
        path = artifact_by_hash(hash_str)
        if path is None:
            raise HTTPException(status_code=404, detail=f"no artifact for hash={hash_str}")
        df = pl.read_parquet(path)
        buf = io.BytesIO()
        with pa.ipc.new_stream(buf, df.to_arrow().schema) as writer:
            writer.write_table(df.to_arrow())
        return Response(content=buf.getvalue(), media_type=ARROW_MIME)

    @router.get("/artifacts/{hash_str}.parquet")
    def artifact(hash_str: str) -> FileResponse:
        path = artifact_by_hash(hash_str)
        if path is None:
            raise HTTPException(status_code=404, detail=f"no artifact for hash={hash_str}")
        return FileResponse(path, media_type="application/octet-stream", filename=path.name)

    return router


def get_app() -> FastAPI:
    global __app__
    if __app__ is None:
        cfg = get_config()
        __app__ = FastAPI(title="SlimTorq Simulator API", version=cfg.app.version)
        __app__.add_middleware(
            CORSMiddleware,
            allow_origins=cfg.cors.allow_origins,
            allow_methods=cfg.cors.allow_methods,
            allow_headers=cfg.cors.allow_headers,
        )
        __app__.include_router(_build_api_router())
        # Serve the frontend's static export at /. Skipped when the bundle
        # isn't present so an API-only dev run still works.
        frontend_dist = cfg.frontend.dist_path
        if frontend_dist.is_dir():
            __app__.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
    return __app__


def get_server() -> uvicorn.Server:
    global __server__
    if __server__ is None:
        cfg = get_config()
        # ``app`` is passed as an import-string with ``factory=True`` so the
        # ``reload`` flag in config/config.yaml is honoured by uvicorn — reload
        # only works when the app is referenced by import path. The
        # ``get_app`` factory is cached, so within a single worker process the
        # FastAPI instance is still a singleton.
        config = uvicorn.Config(
            app="src.server:get_app",
            factory=True,
            host=cfg.app.host,
            port=cfg.app.port,
            log_level=cfg.app.log_level,
            log_config=cfg.app.log_config,
            reload=cfg.app.reload,
        )
        __server__ = uvicorn.Server(config=config)
    return __server__


async def run() -> None:
    await get_server().serve()
