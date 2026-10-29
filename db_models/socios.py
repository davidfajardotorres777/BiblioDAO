"""Tabla SOCIOS: personas que pueden pedir libros."""
from sqlalchemy import Table, Column, Integer, String, Date, Identity, CheckConstraint, select, update

from db_models.base import metadata, ModeloBase

TIPOS_SOCIO = ("ALUMNO", "DOCENTE", "EXTERNO")

socios = Table(
    "socios", metadata,
    Column("soc_id", Integer, Identity(), primary_key=True),
    Column("dni", String(10), nullable=False, unique=True),
    Column("nombre", String(60), nullable=False),
    Column("apellido", String(60), nullable=False),
    Column("email", String(100), unique=True),
    Column("tipo", String(10), nullable=False),
    Column("fecha_alta", Date, nullable=False),
    Column("activo", Integer, nullable=False, default=1),
    CheckConstraint("tipo IN ('ALUMNO','DOCENTE','EXTERNO')", name="ck_socios_tipo"),
)


class Socios(ModeloBase):
    tabla = socios
    pk = "soc_id"

    @staticmethod
    def todos(solo_activos=False):
        query = select(socios).order_by(socios.c.apellido, socios.c.nombre)
        if solo_activos:
            query = query.where(socios.c.activo == 1)
        return query

    @staticmethod
    def por_dni(dni):
        return select(socios).where(socios.c.dni == dni)

    @staticmethod
    def dar_de_baja(soc_id):
        """Baja LOGICA: no se borra la fila (tiene prestamos asociados)."""
        return update(socios).where(socios.c.soc_id == soc_id).values(activo=0)
