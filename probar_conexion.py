"""
Verifica que Python llega a las TRES bases. Correrlo ANTES que todo lo demas.
Ejecutar:  python probar_conexion.py
"""
import redis
from pymongo import MongoClient
from sqlalchemy import create_engine, text

from config_vars import (BBDD_CONNECTION, DB_USER, DB_HOST, DB_PORT, DB_SERVICE,
                         USAR_NOSQL, MONGO_URI, MONGO_DB, REDIS_URL)

print(f"Oracle:  {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_SERVICE} ...")
try:
    engine = create_engine(BBDD_CONNECTION)
    with engine.connect() as con:
        version = con.execute(text("SELECT banner FROM v$version")).scalar()
        usuario = con.execute(text("SELECT USER FROM dual")).scalar()
    print("  OK - conectado como", usuario)
    print("   ", version)
except Exception as e:
    print("  ERROR:", e)
    print("""
  Revisa:
    * DPY-6005 / connection refused -> el contenedor no esta levantado o todavia
      esta arrancando. Mira:  docker logs -f oracle-biblio  hasta ver
      'DATABASE IS READY TO USE!'
    * ORA-12514 -> el servicio no es XEPDB1 (revisa DB_SERVICE en config_vars.py)
    * ORA-01017 -> usuario o contrasena incorrectos
    * ORA-28000 -> la cuenta esta bloqueada
""")

if not USAR_NOSQL:
    print("MongoDB / Redis: deshabilitados (USAR_NOSQL=0)")
    raise SystemExit

print(f"MongoDB: base '{MONGO_DB}' ...")
try:
    cliente = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    print(f"  OK - MongoDB {cliente.server_info()['version']}, "
          f"colecciones: {cliente[MONGO_DB].list_collection_names()}")
except Exception as e:
    print("  ERROR:", type(e).__name__, "-> revisa 'docker ps' (mongo-biblio) y MONGO_URI")

print(f"Redis:   {REDIS_URL} ...")
try:
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=3)
    print(f"  OK - Redis {r.info()['redis_version']}, PING -> {r.ping()}, claves: {r.dbsize()}")
except Exception as e:
    print("  ERROR:", type(e).__name__, "-> revisa 'docker ps' (redis-biblio) y REDIS_URL")
