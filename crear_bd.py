"""
Crea (o recrea) las tablas y carga los datos de prueba ejecutando
dbscripts.sql contra Oracle. Alternativa a correrlo en SQL Developer.

Ejecutar:  python crear_bd.py
"""
from pathlib import Path

from sqlalchemy import create_engine, text

from config_vars import BBDD_CONNECTION

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


if __name__ == "__main__":
    main()
