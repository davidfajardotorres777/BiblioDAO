"""Tabla LIBROS: la obra (titulo, ISBN). Las copias fisicas son EJEMPLARES."""
from sqlalchemy import Table, Column, Integer, String, Identity, ForeignKey, select, func

from db_models.base import metadata, ModeloBase
from db_models.autores import autores

libros = Table(
    "libros", metadata,
    Column("lib_id", Integer, Identity(), primary_key=True),
    Column("isbn", String(20), nullable=False, unique=True),
    Column("titulo", String(200), nullable=False),
    Column("anio", Integer),
    Column("categoria", String(50)),
    Column("aut_id", Integer, ForeignKey("autores.aut_id"), nullable=False),
)


class Libros(ModeloBase):
    tabla = libros
    pk = "lib_id"

    @staticmethod
    def con_autor(*, categoria=None, texto=None):
        """
        SELECT l.*, a.nombre AS autor
          FROM libros l JOIN autores a ON a.aut_id = l.aut_id
         [WHERE l.categoria = :categoria]
         [AND LOWER(l.titulo) LIKE :texto]
         ORDER BY l.titulo
        """
        query = (
            select(libros, autores.c.nombre.label("autor"))
            .join(autores, autores.c.aut_id == libros.c.aut_id)
            .order_by(libros.c.titulo)
        )
        if categoria is not None:
            query = query.where(libros.c.categoria == categoria)
        if texto:
            # LOWER(...) LIKE: busqueda sin importar mayusculas.
            # El valor va como parametro (bind), no pegado al SQL => sin inyeccion SQL.
            query = query.where(func.lower(libros.c.titulo).like(f"%{texto.lower()}%"))
        return query

    @staticmethod
    def por_isbn(isbn):
        return select(libros).where(libros.c.isbn == isbn)
