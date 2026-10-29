"""
Base comun para todos los modelos.

- `metadata` junta la definicion de TODAS las tablas (la usa SQLAlchemy
  para saber como se relacionan y para armar los JOIN).
- `ModeloBase` tiene el CRUD generico. Cada modelo (Socios, Libros, ...)
  hereda de aca y solo define su tabla, su PK y sus consultas propias.

IMPORTANTE: los modelos NO ejecutan nada. Solo ARMAN la consulta
(select / insert / update / delete) y la devuelven. Quien la ejecuta es
el DAO (dao.py). Asi se separa "que consulta hago" de "como me conecto".
"""
from sqlalchemy import MetaData, Table, select, insert, update, delete

metadata = MetaData()


class ModeloBase:
    tabla: Table = None   # la Table de SQLAlchemy (se define en cada hijo)
    pk: str = None        # nombre de la columna clave primaria

    @classmethod
    def columna_pk(cls):
        return cls.tabla.c[cls.pk]

    # ----------------------------- READ -----------------------------
    @classmethod
    def todos(cls):
        """SELECT * FROM tabla ORDER BY pk"""
        return select(cls.tabla).order_by(cls.columna_pk())

    @classmethod
    def por_id(cls, id_):
        """SELECT * FROM tabla WHERE pk = :id"""
        return select(cls.tabla).where(cls.columna_pk() == id_)

    # ---------------------------- CREATE ----------------------------
    @classmethod
    def insertar(cls, **datos):
        """INSERT INTO tabla (...) VALUES (...) RETURNING pk"""
        return insert(cls.tabla).values(**datos).returning(cls.columna_pk())

    # ---------------------------- UPDATE ----------------------------
    @classmethod
    def actualizar(cls, id_, **cambios):
        """UPDATE tabla SET col = valor, ... WHERE pk = :id"""
        return update(cls.tabla).where(cls.columna_pk() == id_).values(**cambios)

    # ---------------------------- DELETE ----------------------------
    @classmethod
    def eliminar(cls, id_):
        """DELETE FROM tabla WHERE pk = :id"""
        return delete(cls.tabla).where(cls.columna_pk() == id_)
