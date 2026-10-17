import threading

from sqlalchemy import select

from app.models import Notificacion
from tests.conftest import cita, hora


def test_agendar_asigna_sala_y_notifica(api, base, db):
    r = cita(api, base)
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["estado"] == "programada" and c["sala_id"] == base["s1"]["id"]
    assert c["duracion_min"] == 30
    notif = db.scalars(select(Notificacion).where(Notificacion.cita_id == c["id"])).all()
    assert [n.tipo for n in notif] == ["confirmacion"]


def test_medico_no_puede_tener_citas_cruzadas(api, base):
    assert cita(api, base, paciente=0, inicio=hora(9)).status_code == 201
    r = cita(api, base, paciente=1, inicio=hora(9, 15))
    assert r.status_code == 409
    assert r.json()["detalle"] == "El médico ya tiene una cita en ese horario."


def test_sala_no_puede_tener_citas_cruzadas(api, base):
    assert cita(api, base, paciente=0, medico="m1", sala="s1").status_code == 201
    r = cita(api, base, paciente=1, medico="m2", sala="s1")
    assert r.status_code == 409 and "sala" in r.json()["detalle"]


def test_paciente_no_puede_tener_citas_cruzadas(api, base):
    assert cita(api, base, paciente=0, medico="m1").status_code == 201
    r = cita(api, base, paciente=0, medico="m2", inicio=hora(9, 10))
    assert r.status_code == 409 and "paciente" in r.json()["detalle"]


def test_citas_contiguas_si_se_permiten(api, base):
    assert cita(api, base, paciente=0, inicio=hora(9)).status_code == 201
    assert cita(api, base, paciente=1, inicio=hora(9, 30)).status_code == 201


def test_sala_debe_pertenecer_al_centro(api, base):
    r = cita(api, base, centro="c1", sala="s3")
    assert r.status_code == 409 and "no pertenece" in r.json()["detalle"]


def test_fuera_del_horario_del_centro(api, base):
    r = cita(api, base, inicio=hora(16, 45))   # terminaría 17:15, el centro cierra 17:00
    assert r.status_code == 422 and "atiende" in r.json()["detalle"]


def test_no_se_agenda_en_el_pasado(api, base):
    r = cita(api, base, inicio="2020-01-06T09:00:00-05:00")
    assert r.status_code == 422


def test_sin_salas_libres(api, base):
    assert cita(api, base, paciente=0, medico="m1").status_code == 201   # ocupa 101
    assert cita(api, base, paciente=1, medico="m2").status_code == 201   # ocupa 102
    r = api.post("/medicos", json={"documento": "m3", "nombres": "A", "apellidos": "B",
                                   "especialidad": "Pediatría"}).json()
    r = api.post("/citas", json={"paciente_id": base["p"][2]["id"], "medico_id": r["id"],
                                 "centro_id": base["c1"]["id"], "inicio": hora(9)})
    assert r.status_code == 409 and "salas libres" in r.json()["detalle"]


def test_dos_reservas_simultaneas_solo_una_gana(api, base):
    """Condición de carrera: dos pacientes piden el mismo cupo al mismo tiempo.
    La base de datos garantiza que solo uno lo obtiene."""
    resultados = []

    def reservar(i):
        resultados.append(cita(api, base, paciente=i, medico="m1", sala="s1").status_code)

    hilos = [threading.Thread(target=reservar, args=(i,)) for i in range(3)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert sorted(resultados) == [201, 409, 409]


def test_cancelar_exige_motivo_y_libera_el_cupo(api, base):
    c = cita(api, base).json()
    assert api.post(f"/citas/{c['id']}/cancelar", json={}).status_code == 422
    r = api.post(f"/citas/{c['id']}/cancelar", json={"motivo": "Viaje"})
    assert r.json()["estado"] == "cancelada"
    assert cita(api, base, paciente=1).status_code == 201   # el cupo quedó libre


def test_no_se_cancela_dos_veces(api, base):
    c = cita(api, base).json()
    api.post(f"/citas/{c['id']}/cancelar", json={"motivo": "x" * 5})
    assert api.post(f"/citas/{c['id']}/cancelar", json={"motivo": "otra vez"}).status_code == 422


def test_maquina_de_estados(api, base):
    c = cita(api, base).json()
    assert api.post(f"/citas/{c['id']}/estado", json={"estado": "confirmada"}).json()["estado"] == "confirmada"
    r = api.post(f"/citas/{c['id']}/estado", json={"estado": "atendida"})
    assert r.status_code == 422 and "ya empezó" in r.json()["detalle"]
    hist = api.get(f"/citas/{c['id']}/historial").json()
    assert [h["a"] for h in hist] == ["programada", "confirmada"]


def test_reprogramar(api, base):
    c = cita(api, base).json()
    api.post(f"/citas/{c['id']}/estado", json={"estado": "confirmada"})
    r = api.post(f"/citas/{c['id']}/reprogramar", json={"inicio": hora(11)})
    assert r.status_code == 200
    assert r.json()["estado"] == "programada"   # un horario nuevo se confirma de nuevo
    assert cita(api, base, paciente=1, inicio=hora(9)).status_code == 201   # el horario viejo quedó libre


def test_consultas(api, base):
    cita(api, base, paciente=0, inicio=hora(9))
    cita(api, base, paciente=0, medico="m2", centro="c2", inicio=hora(11))
    cita(api, base, paciente=1, inicio=hora(10))
    assert len(api.get(f"/pacientes/{base['p'][0]['id']}/citas").json()) == 2
    assert len(api.get(f"/centros/{base['c1']['id']}/citas").json()) == 2
    assert len(api.get(f"/salas/{base['s3']['id']}/citas").json()) == 1


def test_disponibilidad_excluye_lo_ocupado(api, base):
    cita(api, base, paciente=0, medico="m1", inicio=hora(9))
    fecha = hora(9)[:10]
    cupos = api.get("/disponibilidad", params={"fecha": fecha, "medico_id": base["m1"]["id"],
                                               "centro_id": base["c1"]["id"], "limite": 200}).json()
    inicios = {c["inicio"][11:16] for c in cupos}
    assert "09:00" not in inicios and "09:30" in inicios
