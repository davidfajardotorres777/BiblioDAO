"""Tabla EJEMPLARES: cada copia fisica de un libro."""
from sqlalchemy import (Table, Column, Integer, String, Identity, ForeignKey,
                        CheckConstraint, select, update, func)

from db_models.base import metadata, ModeloBase

ESTADOS_EJEMPLAR = ("DISPONIBLE", "PRESTADO", "REPARACION", "BAJA")

ejemplares = Table(
    "ejemplares", metadata,
    Column("eje_id", Integer, Identity(), primary_key=True),
    Column("lib_id", Integer, ForeignKey("libros.lib_id"), nullable=False),
    Column("codigo_inventario", String(20), nullable=False, unique=True),
    Column("estado", String(12), nullable=False, default="DISPONIBLE"),
    CheckConstraint("estado IN ('DISPONIBLE','PRESTADO','REPARACION','BAJA')",
                    name="ck_ejemplares_estado"),
)


class Ejemplares(ModeloBase):
    tabla = ejemplares
    pk = "eje_id"

    @staticmethod
    def de_libro(lib_id):
        return (select(ejemplares)
                .where(ejemplares.c.lib_id == lib_id)
                .order_by(ejemplares.c.codigo_inventario))

    @staticmethod
    def disponibles_de_libro(lib_id):
        """IDs de las copias DISPONIBLES de un libro."""
        return (select(ejemplares.c.eje_id)
                .where(ejemplares.c.lib_id == lib_id,
                       ejemplares.c.estado == "DISPONIBLE")
                .order_by(ejemplares.c.eje_id))

    @staticmethod
    def ocupar(eje_id):
        """
        UPDATE ejemplares SET estado='PRESTADO'
         WHERE eje_id = :id AND estado = 'DISPONIBLE'
        Si otro usuario lo presto un instante antes, actualiza 0 filas
        (el DAO revisa rowcount). Evita prestar la misma copia dos veces.
        """
        return (update(ejemplares)
                .where(ejemplares.c.eje_id == eje_id,
                       ejemplares.c.estado == "DISPONIBLE")
                .values(estado="PRESTADO"))

    @staticmethod
    def liberar(eje_id):
        return (update(ejemplares)
                .where(ejemplares.c.eje_id == eje_id)
                .values(estado="DISPONIBLE"))

    @staticmethod
    def conteo_por_estado(lib_id):
        """SELECT estado, COUNT(*) FROM ejemplares WHERE lib_id=:id GROUP BY estado"""
        return (select(ejemplares.c.estado, func.count().label("cantidad"))
                .where(ejemplares.c.lib_id == lib_id)
                .group_by(ejemplares.c.estado))
