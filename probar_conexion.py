"""
Verifica que Python llega a Oracle. Correrlo ANTES que todo lo demas.
Ejecutar:  python probar_conexion.py
"""
from sqlalchemy import create_engine, text

from config_vars import BBDD_CONNECTION, DB_USER, DB_HOST, DB_PORT, DB_SERVICE

print(f"Conectando a {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_SERVICE} ...")
try:
    engine = create_engine(BBDD_CONNECTION)
    with engine.connect() as con:
        version = con.execute(text("SELECT banner FROM v$version")).scalar()
        usuario = con.execute(text("SELECT USER FROM dual")).scalar()
    print("OK - conectado como", usuario)
    print("   ", version)
except Exception as e:
    print("ERROR:", e)
    print("""
Revisa:
  * DPY-6005 / connection refused -> el contenedor no esta levantado o todavia
    esta arrancando. Mira:  docker logs -f oracle-biblio  hasta ver
    'DATABASE IS READY TO USE!'
  * ORA-12514 -> el servicio no es XEPDB1 (revisa DB_SERVICE en config_vars.py)
  * ORA-01017 -> usuario o contrasena incorrectos
  * ORA-28000 -> la cuenta esta bloqueada
""")
