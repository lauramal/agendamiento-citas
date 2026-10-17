from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Toda la configuración sale de variables de entorno (.env)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/citas"
    zona_horaria: str = "America/Bogota"
    url_publica: str = "http://localhost:8000"
    secreto_enlaces: str = "cambiar-en-produccion"

    # Reglas de negocio configurables (no quemadas en el código)
    duracion_cita_min: int = 30
    horas_recordatorio: int = 24
    minutos_reserva_oferta: int = 120
    horas_minimas_cancelacion: int = 2

    # Correo (en local: Mailpit, que captura todo y lo muestra en http://localhost:8025)
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_remitente: str = "citas@centromedico.com.co"
    smtp_usuario: str | None = None        # para un SMTP real (ej. Gmail)
    smtp_clave: str | None = None          # en Gmail: contraseña de aplicación, nunca la clave normal
    smtp_tls: bool = False                 # STARTTLS (Gmail: true, puerto 587)
    # Modo demostración: si se define, TODOS los correos se envían a esta dirección
    # (los pacientes de la semilla tienen correos ficticios). Nunca usar en producción.
    correo_redirigir_a: str | None = None
    notificaciones_simuladas: bool = False   # True: no envía, solo registra (útil en pruebas)

    # Agente (opcional): proveedor intercambiable vía init_chat_model
    llm_modelo: str = "anthropic:claude-haiku-4-5"
    anthropic_api_key: str | None = None

    jobs_activos: bool = True

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.zona_horaria)


settings = Settings()
