"""Tabla AUTORES."""
from sqlalchemy import Table, Column, Integer, String, Identity, select

from db_models.base import metadata, ModeloBase

autores = Table(
    "autores", metadata,
    Column("aut_id", Integer, Identity(), primary_key=True),
    Column("nombre", String(100), nullable=False),
    Column("nacionalidad", String(50)),
)


class Autores(ModeloBase):
    tabla = autores
    pk = "aut_id"

    @staticmethod
    def todos():
        return select(autores).order_by(autores.c.nombre)
