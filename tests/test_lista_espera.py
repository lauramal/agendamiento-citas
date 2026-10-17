from datetime import timedelta

from sqlalchemy import select

from app.models import Cita, ListaEspera, Notificacion
from app.services import lista_espera
from app.services.citas import ahora
from app.services.tokens import generar
from tests.conftest import cita, dia_habil


def _esperar(api, base, i, especialidad="Cardiología"):
    hoy = ahora().date()
    return api.post("/lista-espera", json={"paciente_id": base["p"][i]["id"], "especialidad": especialidad,
                                           "desde": str(hoy), "hasta": str(dia_habil(10))}).json()


def test_cancelacion_ofrece_el_cupo_al_primero_de_la_fila(api, base, db):
    c = cita(api, base, paciente=0).json()
    _esperar(api, base, 1)
    _esperar(api, base, 2)
    api.post(f"/citas/{c['id']}/cancelar", json={"motivo": "No puedo"})

    oferta = db.scalar(select(Cita).where(Cita.estado == "ofrecida"))
    assert oferta.paciente_id == base["p"][1]["id"]           # el primero de la fila
    assert oferta.inicio == db.get(Cita, c["id"]).inicio      # el mismo cupo que se liberó
    tipos = [n.tipo for n in db.scalars(select(Notificacion).where(Notificacion.cita_id == oferta.id))]
    assert "oferta_lista_espera" in tipos
    # mientras decide, el cupo está bloqueado para los demás canales
    assert cita(api, base, paciente=2).status_code == 409


def test_aceptar_oferta(api, base, db):
    c = cita(api, base, paciente=0).json()
    e = _esperar(api, base, 1)
    api.post(f"/citas/{c['id']}/cancelar", json={"motivo": "No puedo"})
    oferta = db.scalar(select(Cita).where(Cita.estado == "ofrecida"))
    r = api.post(f"/lista-espera/ofertas/{oferta.id}/aceptar")
    assert r.json()["estado"] == "confirmada"
    db.expire_all()
    assert db.get(ListaEspera, e["id"]).estado == "asignada"


def test_rechazar_pasa_al_siguiente_y_conserva_el_turno(api, base, db):
    c = cita(api, base, paciente=0).json()
    e1 = _esperar(api, base, 1)
    _esperar(api, base, 2)
    api.post(f"/citas/{c['id']}/cancelar", json={"motivo": "No puedo"})
    primera = db.scalar(select(Cita).where(Cita.estado == "ofrecida"))
    api.post(f"/lista-espera/ofertas/{primera.id}/rechazar")
    db.expire_all()
    segunda = db.scalar(select(Cita).where(Cita.estado == "ofrecida"))
    assert segunda.paciente_id == base["p"][2]["id"]
    assert db.get(ListaEspera, e1["id"]).estado == "esperando"


def test_oferta_vencida_pasa_al_siguiente(api, base, db):
    c = cita(api, base, paciente=0).json()
    e1 = _esperar(api, base, 1)
    _esperar(api, base, 2)
    api.post(f"/citas/{c['id']}/cancelar", json={"motivo": "No puedo"})
    vencidas = lista_espera.expirar_ofertas(db, momento=ahora() + timedelta(days=1, hours=-20))
    assert vencidas == 1
    db.expire_all()
    assert db.get(ListaEspera, e1["id"]).estado == "expirada"
    assert db.scalar(select(Cita).where(Cita.estado == "ofrecida")).paciente_id == base["p"][2]["id"]


def test_no_se_duplica_en_lista_de_espera(api, base):
    _esperar(api, base, 1)
    hoy = ahora().date()
    r = api.post("/lista-espera", json={"paciente_id": base["p"][1]["id"], "especialidad": "cardiología",
                                        "desde": str(hoy), "hasta": str(hoy)})
    assert r.status_code == 409


def test_enlace_del_correo_no_actua_con_solo_abrirlo(api, base, db):
    c = cita(api, base).json()
    token = generar(c["id"], "cancelar")
    pagina = api.get(f"/acciones/{token}")
    assert pagina.status_code == 200 and "cancelar" in pagina.text.lower()
    assert api.get(f"/citas/{c['id']}").json()["estado"] == "programada"   # abrir no cancela
    api.post(f"/acciones/{token}")
    assert api.get(f"/citas/{c['id']}").json()["estado"] == "cancelada"


def test_enlace_alterado_es_rechazado(api):
    assert "no es válido" in api.get("/acciones/token-falso").text
