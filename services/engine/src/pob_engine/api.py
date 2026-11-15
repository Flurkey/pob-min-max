from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from pob_engine.errors import EngineError
from pob_engine.examples import LIFE_PLATE
from pob_engine.paths import resolve_paths
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


def create_app(service: EngineService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if getattr(app.state, "service", None) is None:
            app.state.service = EngineService.start()
            app.state.owns_service = True
        yield
        if getattr(app.state, "owns_service", False):
            app.state.service.close()

    app = FastAPI(title="PoE Forge engine", version="0.1.0", lifespan=lifespan)
    if service is not None:
        app.state.service = service

    @app.exception_handler(EngineError)
    async def engine_error(_request, exc: EngineError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(KeyError)
    async def missing(_request, exc: KeyError):
        return JSONResponse(status_code=404, content={"detail": f"Unknown revision {exc.args[0]}"})

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
        return {"xml": svc().export_xml(revision_id)}

    @app.post("/api/compare")
    def compare(body: CompareBody):
        return svc().compare(body.leftRevisionId, body.rightRevisionId)

    @app.get("/api/search")
    def search(q: str = ""):
        return {"revisions": svc().search(q)}

    return app
