from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from pob_engine.errors import EngineError
from pob_engine.examples import LIFE_PLATE
from pob_engine.paths import library_path, resolve_paths
from pob_engine.service import EngineService


class ImportBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    xml: str = Field(min_length=1)


class EquipBody(BaseModel):
    text: str = Field(min_length=1)
    slot: str | None = None


class PassiveBody(BaseModel):
    nodeId: int | None = None


class CompareBody(BaseModel):
    leftRevisionId: str
    rightRevisionId: str


class CopyBody(BaseModel):
    revisionId: str | None = None


def create_app(service: EngineService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if getattr(app.state, "service", None) is None:
            app.state.service = EngineService.start(store_path=library_path())
            app.state.owns_service = True
        yield
        if getattr(app.state, "owns_service", False):
            app.state.service.close()

    app = FastAPI(title="PoE Forge engine", version="0.2.0", lifespan=lifespan)
    if service is not None:
        app.state.service = service

    @app.exception_handler(EngineError)
    async def engine_error(_request, exc: EngineError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(KeyError)
    async def missing(_request, exc: KeyError):
        return JSONResponse(status_code=404, content={"detail": f"Not found: {exc.args[0]}"})

    def svc() -> EngineService:
        current = getattr(app.state, "service", None)
        if current is None:
            raise HTTPException(status_code=503, detail="Engine is not running.")
        return current

    @app.get("/api/engine")
    def engine():
        return svc().engine_info()

    @app.get("/api/examples/life-plate")
    def life_plate():
        return {"slot": "Body Armour", "text": LIFE_PLATE}

    @app.get("/api/fixtures/scion-baseline")
    def baseline():
        path = resolve_paths().fixture
        return {"name": "Scion baseline", "xml": path.read_text(encoding="utf-8")}

    @app.post("/api/builds")
    def import_build(body: ImportBody):
        return svc().import_xml(body.xml, body.name)

    @app.post("/api/builds/{revision_id}/calculate")
    def calculate(revision_id: str):
        return svc().calculate(revision_id)

    @app.post("/api/builds/{revision_id}/equipment")
    def equip(revision_id: str, body: EquipBody):
        return svc().equip(revision_id, body.text, body.slot)

    @app.post("/api/builds/{revision_id}/passives")
    def passives(revision_id: str, body: PassiveBody):
        return svc().allocate(revision_id, body.nodeId)

    @app.get("/api/builds/{revision_id}/export")
    def export(revision_id: str):
        xml = svc().export_xml(revision_id)
        return {"xml": xml}

    @app.post("/api/builds/{revision_id}/inspect")
    def inspect(revision_id: str):
        return svc().inspect(revision_id)

    @app.post("/api/builds/{revision_id}/save")
    def save(revision_id: str):
        return svc().save(revision_id)

    @app.post("/api/builds/{revision_id}/discard")
    def discard(revision_id: str):
        return svc().discard(revision_id)

    @app.get("/api/library")
    def library(q: str = ""):
        return {"builds": svc().library(q), "storage": "sqlite"}

    @app.get("/api/library/{build_id}")
    def build_detail(build_id: str):
        return svc().history(build_id)

    @app.post("/api/library/{build_id}/copies")
    def copy_build(build_id: str, body: CopyBody):
        return svc().copy(build_id, body.revisionId)

    @app.post("/api/compare")
    def compare(body: CompareBody):
        return svc().compare(body.leftRevisionId, body.rightRevisionId)

    @app.get("/api/search")
    def search(q: str = ""):
        return {"revisions": svc().search(q)}

    return app
