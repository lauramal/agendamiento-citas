import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.errores import ErrorNegocio
from app.routers import acciones, agente, catalogos, citas, lista_espera

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    sched = None
    if settings.jobs_activos:
        from app.jobs import iniciar
        sched = iniciar()
    yield
    if sched:
        sched.shutdown(wait=False)


app = FastAPI(
    title="Agendamiento de citas médicas",
    description="Una sola fuente de verdad de cupos para todos los canales, con validaciones en "
                "la base de datos, lista de espera automática, recordatorios y asistente conversacional.",
    version="1.0.0",
    lifespan=ciclo_de_vida,
)


@app.exception_handler(ErrorNegocio)
def manejar_error_negocio(_: Request, e: ErrorNegocio):
    return JSONResponse(status_code=e.codigo, content={"detalle": e.mensaje})


for r in (catalogos.pacientes, catalogos.medicos, catalogos.centros, catalogos.salas,
          citas.router, lista_espera.router, agente.router, acciones.router):
    app.include_router(r)


@app.get("/", include_in_schema=False)
def inicio():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/salud", tags=["Sistema"])
def salud():
    return {"estado": "ok", "asistente": bool(settings.anthropic_api_key)}
