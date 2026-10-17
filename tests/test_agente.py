"""Guardrails del agente: se prueban las herramientas sin LLM.
La identidad viaja en el contexto, así que el modelo no puede tocar citas ajenas."""
import json
from types import SimpleNamespace

from app.agente.sofia import ContextoPaciente, agendar_cita, cancelar_cita, mis_citas
from tests.conftest import cita, hora


def _rt(paciente_id):
    return SimpleNamespace(context=ContextoPaciente(paciente_id=paciente_id))


def test_agente_no_puede_cancelar_citas_de_otro_paciente(api, base):
    ajena = cita(api, base, paciente=0).json()
    r = json.loads(cancelar_cita.func(cita_id=ajena["id"], motivo="x", runtime=_rt(base["p"][1]["id"])))
    assert r["resultado"] == "no_permitido"
    assert api.get(f"/citas/{ajena['id']}").json()["estado"] == "programada"


def test_agente_recibe_el_motivo_cuando_la_base_rechaza(api, base):
    cita(api, base, paciente=0, inicio=hora(9))
    r = json.loads(agendar_cita.func(medico_id=base["m1"]["id"], centro_id=base["c1"]["id"],
                                     inicio=hora(9), motivo=None, runtime=_rt(base["p"][1]["id"])))
    assert r == {"resultado": "no_permitido", "motivo": "El médico ya tiene una cita en ese horario."}


def test_agente_solo_ve_las_citas_del_paciente(api, base):
    cita(api, base, paciente=0, inicio=hora(9))
    cita(api, base, paciente=1, inicio=hora(10))
    r = json.loads(mis_citas.func(runtime=_rt(base["p"][1]["id"])))
    assert len(r["citas"]) == 1
