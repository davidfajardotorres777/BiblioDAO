"""Tabla MULTAS: se genera una al devolver un prestamo con atraso."""
from sqlalchemy import (Table, Column, Integer, Numeric, Identity, ForeignKey,
                        select, update, func)

from db_models.base import metadata, ModeloBase
from db_models.socios import socios
from db_models.prestamos import prestamos

multas = Table(
    "multas", metadata,
    Column("mul_id", Integer, Identity(), primary_key=True),
    Column("pre_id", Integer, ForeignKey("prestamos.pre_id"), nullable=False, unique=True),
    Column("monto", Numeric(10, 2), nullable=False),
    Column("pagada", Integer, nullable=False, default=0),
)


class Multas(ModeloBase):
    tabla = multas
    pk = "mul_id"

    @staticmethod
    def pendientes(soc_id=None):
        """Multas impagas con el nombre del socio."""
        query = (
            select(multas.c.mul_id, multas.c.pre_id, multas.c.monto,
                   socios.c.soc_id,
                   (socios.c.apellido + ", " + socios.c.nombre).label("socio"))
            .select_from(multas)
            .join(prestamos, prestamos.c.pre_id == multas.c.pre_id)
            .join(socios, socios.c.soc_id == prestamos.c.soc_id)
            .where(multas.c.pagada == 0)
            .order_by(multas.c.mul_id)
        )
        if soc_id is not None:
            query = query.where(socios.c.soc_id == soc_id)
        return query

    @staticmethod
    def contar_pendientes(soc_id):
        return (select(func.count())
                .select_from(multas)
                .join(prestamos, prestamos.c.pre_id == multas.c.pre_id)
                .where(prestamos.c.soc_id == soc_id, multas.c.pagada == 0))

    @staticmethod
    def pagar(mul_id):
        return (update(multas)
                .where(multas.c.mul_id == mul_id, multas.c.pagada == 0)
                .values(pagada=1))
