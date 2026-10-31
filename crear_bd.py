"""
Crea las tablas y carga los datos de prueba corriendo dbscripts.sql en
oracle (es lo mismo que abrirlo en SQL Developer y darle F5).
Despues deja listos mongo y redis con algunas resenas de ejemplo.

Ejecutar:  python crear_bd.py
"""
from pathlib import Path

from pymongo.errors import PyMongoError
from redis.exceptions import RedisError
from sqlalchemy import create_engine, text

from config_vars import BBDD_CONNECTION, USAR_NOSQL
from dao import BibliotecaDAO

SCRIPT = Path(__file__).with_name("dbscripts.sql")


def separar_sentencias(sql):
    """
    Corta el script en sentencias sueltas:
      - SQL comun termina en ';'
      - bloques PL/SQL (BEGIN ... END;) terminan con una linea que tiene solo '/'
    """
    sentencias, actual, en_plsql = [], [], False
    for linea in sql.splitlines():
        limpia = linea.strip()
        if not actual and (not limpia or limpia.startswith("--")):
            continue                      # lineas vacias o comentarios sueltos
        if not actual and limpia.upper().startswith(("BEGIN", "DECLARE")):
            en_plsql = True
        if en_plsql:
            if limpia == "/":
                sentencias.append("\n".join(actual))
                actual, en_plsql = [], False
            else:
                actual.append(linea)
        else:
            actual.append(linea)
            if limpia.endswith(";"):
                sentencias.append("\n".join(actual).rstrip().rstrip(";"))
                actual = []
    return sentencias


def main():
    sentencias = separar_sentencias(SCRIPT.read_text(encoding="utf-8"))
    engine = create_engine(BBDD_CONNECTION)
    with engine.begin() as con:
        for sentencia in sentencias:
            if sentencia.strip().upper() == "COMMIT":
                continue                  # engine.begin() ya hace el COMMIT
            resultado = con.execute(text(sentencia))
            if resultado.returns_rows:    # el SELECT final de control
                for tabla, filas in resultado:
                    print(f"  {tabla:<11} {filas} filas")
    engine.dispose()
    print(f"Listo: {len(sentencias)} sentencias ejecutadas.")

    if USAR_NOSQL:
        preparar_nosql()


# resenas de ejemplo, cada socio resena un libro que pidio en dbscripts.sql
RESENAS_INICIALES = [
    dict(soc_id=4, lib_id=1, puntaje=5, comentario="Un clasico: cada cuento es un laberinto.",
         etiquetas=["clasico", "cuentos", "literatura-argentina"]),
    dict(soc_id=1, lib_id=4, puntaje=5, comentario="Muy claro para normalizacion y SQL.",
         etiquetas=["bases-de-datos", "teoria", "recomendado"]),
    dict(soc_id=3, lib_id=4, puntaje=3, comentario="Completo pero denso; mejor con el apunte.",
         etiquetas=["bases-de-datos", "denso"]),
    dict(soc_id=2, lib_id=3, puntaje=4, comentario="Se puede leer en el orden que quieras.",
         etiquetas=["novela", "literatura-argentina"]),
]


def preparar_nosql():
    try:
        with BibliotecaDAO() as dao:
            dao.inicializar_nosql()
            for resena in RESENAS_INICIALES:
                dao.agregar_resena(**resena)
            for clave, valor in dao.resumen_nosql().items():
                print(f"  {clave:<30} {valor}")
        print("Listo: MongoDB y Redis preparados.")
    except (PyMongoError, RedisError) as e:
        print(f"[aviso] No se pudo preparar MongoDB/Redis ({type(e).__name__}). "
              f"Oracle quedo listo igual. Revisar: docker ps")


if __name__ == "__main__":
    main()
