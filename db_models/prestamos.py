"""Tabla PRESTAMOS. fecha_devolucion NULL = prestamo activo."""
from sqlalchemy import (Table, Column, Integer, Date, Identity, ForeignKey,
                        select, update, func, desc)

from db_models.base import metadata, ModeloBase
from db_models.socios import socios
from db_models.libros import libros
from db_models.autores import autores
from db_models.ejemplares import ejemplares

prestamos = Table(
    "prestamos", metadata,
    Column("pre_id", Integer, Identity(), primary_key=True),
    Column("eje_id", Integer, ForeignKey("ejemplares.eje_id"), nullable=False),
    Column("soc_id", Integer, ForeignKey("socios.soc_id"), nullable=False),
    Column("fecha_prestamo", Date, nullable=False),
    Column("fecha_vencimiento", Date, nullable=False),
    Column("fecha_devolucion", Date),
)


def _detalle():
    """
    SELECT base con todos los datos "lindos" de un prestamo:
      prestamos JOIN socios JOIN ejemplares JOIN libros
    Las demas consultas le agregan su WHERE.
    """
    return (
        select(
            prestamos.c.pre_id,
            socios.c.soc_id,
            (socios.c.apellido + ", " + socios.c.nombre).label("socio"),
            libros.c.titulo,
            ejemplares.c.codigo_inventario,
            prestamos.c.fecha_prestamo,
            prestamos.c.fecha_vencimiento,
            prestamos.c.fecha_devolucion,
        )
        .select_from(prestamos)
        .join(socios, socios.c.soc_id == prestamos.c.soc_id)
        .join(ejemplares, ejemplares.c.eje_id == prestamos.c.eje_id)
        .join(libros, libros.c.lib_id == ejemplares.c.lib_id)
    )


class Prestamos(ModeloBase):
    tabla = prestamos
    pk = "pre_id"

    @staticmethod
    def contar_activos(soc_id):
        """SELECT COUNT(*) FROM prestamos WHERE soc_id=:id AND fecha_devolucion IS NULL"""
        return (select(func.count())
                .select_from(prestamos)
                .where(prestamos.c.soc_id == soc_id,
                       prestamos.c.fecha_devolucion.is_(None)))

    @staticmethod
    def contar_de_socio_y_libro(soc_id, lib_id):
        """Cuantas veces el socio pidio ese libro. Se usa para las resenas."""
        return (select(func.count())
                .select_from(prestamos)
                .join(ejemplares, ejemplares.c.eje_id == prestamos.c.eje_id)
                .where(prestamos.c.soc_id == soc_id, ejemplares.c.lib_id == lib_id))

    @staticmethod
    def activos(soc_id=None):
        query = (_detalle()
                 .where(prestamos.c.fecha_devolucion.is_(None))
                 .order_by(prestamos.c.fecha_vencimiento))
        if soc_id is not None:
            query = query.where(prestamos.c.soc_id == soc_id)
        return query

    @staticmethod
    def vencidos(hoy):
        """Activos cuya fecha de vencimiento ya paso."""
        return (_detalle()
                .where(prestamos.c.fecha_devolucion.is_(None),
                       prestamos.c.fecha_vencimiento < hoy)
                .order_by(prestamos.c.fecha_vencimiento))

    @staticmethod
    def historial_socio(soc_id):
        return (_detalle()
                .where(prestamos.c.soc_id == soc_id)
                .order_by(desc(prestamos.c.fecha_prestamo), desc(prestamos.c.pre_id)))

    @staticmethod
    def registrar_devolucion(pre_id, fecha):
        return (update(prestamos)
                .where(prestamos.c.pre_id == pre_id)
                .values(fecha_devolucion=fecha))

    @staticmethod
    def libros_mas_prestados(top=5):
        """
        SELECT l.lib_id, l.titulo, a.nombre AS autor, COUNT(p.pre_id) AS veces
          FROM prestamos p JOIN ejemplares e ... JOIN libros l ... JOIN autores a ...
         GROUP BY l.lib_id, l.titulo, a.nombre
         ORDER BY veces DESC
         FETCH FIRST :top ROWS ONLY
        """
        veces = func.count(prestamos.c.pre_id).label("veces")
        return (
            select(libros.c.lib_id, libros.c.titulo, autores.c.nombre.label("autor"), veces)
            .select_from(prestamos)
            .join(ejemplares, ejemplares.c.eje_id == prestamos.c.eje_id)
            .join(libros, libros.c.lib_id == ejemplares.c.lib_id)
            .join(autores, autores.c.aut_id == libros.c.aut_id)
            .group_by(libros.c.lib_id, libros.c.titulo, autores.c.nombre)
            .order_by(desc(veces), libros.c.titulo)
            .limit(top)
        )
