from tests.conftest import cita


def test_crud_paciente(api):
    datos = {"documento": "123", "nombres": "Rosa", "apellidos": "M", "fecha_nacimiento": "1948-03-12",
             "telefono": "3001112233", "canal_preferido": "whatsapp", "atencion_asistida": True}
    p = api.post("/pacientes", json=datos).json()
    assert p["atencion_asistida"] is True
    assert api.post("/pacientes", json=datos).status_code == 409   # documento duplicado
    assert api.patch(f"/pacientes/{p['id']}", json={"email": "rosa@correo.com.co"}).json()["email"] == "rosa@correo.com.co"
    assert api.delete(f"/pacientes/{p['id']}").json()["activo"] is False
    assert api.get("/pacientes").json() == []


def test_paciente_requiere_un_contacto(api):
    r = api.post("/pacientes", json={"documento": "1", "nombres": "A", "apellidos": "B",
                                     "fecha_nacimiento": "1990-01-01"})
    assert r.status_code == 422


def test_no_se_desactiva_con_citas_proximas(api, base):
    cita(api, base)
    assert api.delete(f"/pacientes/{base['p'][0]['id']}").status_code == 409
    assert api.delete(f"/medicos/{base['m1']['id']}").status_code == 409
    assert api.delete(f"/salas/{base['s1']['id']}").status_code == 409


def test_horario_de_centro_valido(api):
    r = api.post("/centros", json={"nombre": "Centro X", "direccion": "d", "ciudad": "c",
                                   "hora_apertura": "18:00", "hora_cierre": "07:00"})
    assert r.status_code == 409
