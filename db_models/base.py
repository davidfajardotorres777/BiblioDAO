"""
Base comun para todos los modelos.

metadata tiene la definicion de todas las tablas (sqlalchemy la usa para
saber como se relacionan). ModeloBase tiene el CRUD generico y cada modelo
hereda de aca con su tabla, su pk y sus consultas.

Los modelos no ejecutan nada, solo arman el select/insert/update/delete y
lo devuelven. El que ejecuta es el DAO.
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
