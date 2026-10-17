import os
from datetime import datetime, time, timedelta
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/citas_test")
os.environ["NOTIFICACIONES_SIMULADAS"] = "true"
os.environ["JOBS_ACTIVOS"] = "false"
os.environ["ANTHROPIC_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

ESQUEMA = Path(__file__).parent.parent / "sql" / "001_esquema.sql"


@pytest.fixture(scope="session", autouse=True)
def esquema():
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        c.exec_driver_sql(ESQUEMA.read_text())
    yield


@pytest.fixture(autouse=True)
def limpiar():
    yield
    with engine.begin() as c:
        c.execute(text("TRUNCATE notificaciones, lista_espera, citas_historial, citas, salas, "
                       "medicos, pacientes, centros RESTART IDENTITY CASCADE"))


@pytest.fixture
def api():
    return TestClient(app)


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


def dia_habil(dias: int = 3):
    d = datetime.now(settings.tz).date() + timedelta(days=dias)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def hora(h: int, m: int = 0, dias: int = 3) -> str:
    return datetime.combine(dia_habil(dias), time(h, m), tzinfo=settings.tz).isoformat()


@pytest.fixture
def base(api):
    """Un centro con 2 salas, otro centro con 1 sala, 2 médicos y 3 pacientes."""
    c1 = api.post("/centros", json={"nombre": "Norte", "direccion": "Cl 1", "ciudad": "Bogotá",
                                     "hora_apertura": "07:00", "hora_cierre": "17:00"}).json()
    c2 = api.post("/centros", json={"nombre": "Sur", "direccion": "Cl 2", "ciudad": "Bogotá"}).json()
    s1 = api.post("/salas", json={"centro_id": c1["id"], "nombre": "101"}).json()
    s2 = api.post("/salas", json={"centro_id": c1["id"], "nombre": "102"}).json()
    s3 = api.post("/salas", json={"centro_id": c2["id"], "nombre": "201"}).json()
    m1 = api.post("/medicos", json={"documento": "m1", "nombres": "Laura", "apellidos": "Gómez",
                                     "especialidad": "Cardiología"}).json()
    m2 = api.post("/medicos", json={"documento": "m2", "nombres": "Andrés", "apellidos": "Rincón",
                                     "especialidad": "Cardiología"}).json()
    pac = [api.post("/pacientes", json={"documento": f"p{i}", "nombres": f"Paciente{i}", "apellidos": "X",
                                        "fecha_nacimiento": "1960-01-01", "email": f"p{i}@correo.com.co"}).json()
           for i in range(1, 4)]
    return {"c1": c1, "c2": c2, "s1": s1, "s2": s2, "s3": s3, "m1": m1, "m2": m2, "p": pac}


def cita(api, b, paciente=0, medico="m1", centro="c1", sala=None, inicio=None, **extra):
    datos = {"paciente_id": b["p"][paciente]["id"], "medico_id": b[medico]["id"],
             "centro_id": b[centro]["id"], "inicio": inicio or hora(9), **extra}
    if sala:
        datos["sala_id"] = b[sala]["id"]
    return api.post("/citas", json=datos)
