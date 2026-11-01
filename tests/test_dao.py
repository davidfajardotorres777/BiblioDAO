"""
Pruebas del DAO sin necesitar docker.

En vez de oracle uso sqlite, y para mongo y redis uso mongomock y fakeredis,
que funcionan en memoria. Se le pasan al DAO en el constructor.

Correr desde la carpeta del proyecto:  python -m tests.test_dao
"""
import os
import tempfile
import warnings
from datetime import date, timedelta

import fakeredis
import mongomock
from sqlalchemy import exc as sa_exc

from dao import BibliotecaDAO, BibliotecaError
from db_models import metadata, cache

warnings.filterwarnings("ignore", category=sa_exc.SAWarning)  # Decimal en SQLite

HOY = date.today()


def preparar_dao():
    archivo = os.path.join(tempfile.mkdtemp(), "biblio_test.db")
    dao = BibliotecaDAO(f"sqlite:///{archivo}",
                        mongo=mongomock.MongoClient()["biblio_test"],
                        redis_cli=fakeredis.FakeRedis(decode_responses=True))
    metadata.create_all(dao.engine)       # en oracle esto lo hace dbscripts.sql
    dao.inicializar_nosql()
    return dao


def cargar_datos(dao):
    borges = dao.crear_autor(nombre="Jorge Luis Borges", nacionalidad="Argentina")
    elmasri = dao.crear_autor(nombre="Ramez Elmasri", nacionalidad="Estados Unidos")
    ficciones = dao.crear_libro(isbn="111", titulo="Ficciones", aut_id=borges,
                                anio=1944, categoria="Literatura")
    bd = dao.crear_libro(isbn="222", titulo="Fundamentos de Sistemas de Bases de Datos",
                         aut_id=elmasri, anio=2007, categoria="Informatica")
    dao.agregar_ejemplar(lib_id=ficciones, codigo_inventario="INV-001")
    dao.agregar_ejemplar(lib_id=bd, codigo_inventario="INV-002")
    dao.agregar_ejemplar(lib_id=bd, codigo_inventario="INV-003")
    lucia = dao.crear_socio(dni="40111222", nombre="Lucia", apellido="Herrera", tipo="alumno")
    carlos = dao.crear_socio(dni="25444555", nombre="Carlos", apellido="Vega", tipo="DOCENTE")
    return dict(ficciones=ficciones, bd=bd, lucia=lucia, carlos=carlos)


def debe_fallar(funcion, *args, **kwargs):
    try:
        funcion(*args, **kwargs)
    except BibliotecaError as e:
        return str(e)
    raise AssertionError(f"{funcion.__name__} deberia haber fallado")


def main():
    dao = preparar_dao()
    ids = cargar_datos(dao)
    ok = lambda msg: print(f"  OK  {msg}")

    # ---- CRUD basico
    assert len(dao.listar_libros()) == 2
    assert dao.buscar_libros("bases")[0]["autor"] == "Ramez Elmasri"
    assert len(dao.listar_libros(categoria="Literatura")) == 1
    assert dao.buscar_socio_por_dni("40111222")["nombre"] == "Lucia"
    dao.actualizar_socio(ids["lucia"], email="lucia@undec.edu.ar")
    assert dao.obtener_socio(ids["lucia"])["email"] == "lucia@undec.edu.ar"
    debe_fallar(dao.crear_socio, dni="40111222", nombre="X", apellido="Y", tipo="ALUMNO")
    debe_fallar(dao.crear_socio, dni="1", nombre="X", apellido="Y", tipo="JEFE")
    debe_fallar(dao.crear_libro, isbn="999", titulo="X", aut_id=999)
    ok("CRUD de socios, autores, libros y validaciones")

    # ---- Prestamo normal
    p1 = dao.prestar_libro(soc_id=ids["lucia"], lib_id=ids["bd"])
    assert dao.disponibilidad(ids["bd"])["PRESTADO"] == 1
    assert dao.disponibilidad(ids["bd"])["DISPONIBLE"] == 1
    assert len(dao.prestamos_activos(ids["lucia"])) == 1
    ok("prestar_libro marca el ejemplar como PRESTADO")

    # ---- sin copias disponibles: error y no queda nada guardado
    dao.prestar_libro(soc_id=ids["carlos"], lib_id=ids["bd"])
    msg = debe_fallar(dao.prestar_libro, soc_id=ids["lucia"], lib_id=ids["bd"])
    assert "No hay ejemplares" in msg
    assert len(dao.prestamos_activos()) == 2
    ok("sin copias disponibles -> error y rollback")

    # ---- Devolucion a tiempo
    r = dao.devolver_libro(p1)
    assert r == {"pre_id": p1, "dias_atraso": 0, "multa": 0}
    assert dao.disponibilidad(ids["bd"])["DISPONIBLE"] == 1
    debe_fallar(dao.devolver_libro, p1)
    ok("devolver_libro a tiempo, sin multa; no se puede devolver dos veces")

    # ---- Prestamo vencido y devolucion tarde => multa
    hace_20 = HOY - timedelta(days=20)
    p2 = dao.prestar_libro(soc_id=ids["lucia"], lib_id=ids["ficciones"], hoy=hace_20)
    vencidos = dao.prestamos_vencidos()
    assert len(vencidos) == 1 and vencidos[0]["dias_atraso"] == 6
    r = dao.devolver_libro(p2)
    assert r["dias_atraso"] == 6 and r["multa"] == 6 * 500
    multas = dao.multas_pendientes(ids["lucia"])
    assert len(multas) == 1 and float(multas[0]["monto"]) == 3000
    ok("devolucion con 6 dias de atraso -> multa de $3000")

    # ---- Con multa impaga no puede pedir
    msg = debe_fallar(dao.prestar_libro, soc_id=ids["lucia"], lib_id=ids["ficciones"])
    assert "multas" in msg
    dao.pagar_multa(multas[0]["mul_id"])
    debe_fallar(dao.pagar_multa, multas[0]["mul_id"])
    dao.prestar_libro(soc_id=ids["lucia"], lib_id=ids["ficciones"])
    ok("multa impaga bloquea prestamos; al pagarla se habilita")

    # ---- Maximo de prestamos simultaneos
    for i in range(3):
        dao.agregar_ejemplar(lib_id=ids["bd"], codigo_inventario=f"INV-X{i}")
    dao.prestar_libro(soc_id=ids["lucia"], lib_id=ids["bd"])
    dao.prestar_libro(soc_id=ids["lucia"], lib_id=ids["bd"])
    msg = debe_fallar(dao.prestar_libro, soc_id=ids["lucia"], lib_id=ids["bd"])
    assert "maximo" in msg
    ok("no puede superar MAX_PRESTAMOS_ACTIVOS")

    # ---- Baja de socio
    dao.dar_de_baja_socio(ids["carlos"])
    msg = debe_fallar(dao.prestar_libro, soc_id=ids["carlos"], lib_id=ids["bd"])
    assert "baja" in msg
    assert len(dao.listar_socios(solo_activos=True)) == 1
    ok("socio dado de baja no puede pedir libros")

    # ---- Reportes
    top = dao.libros_mas_prestados()
    assert top[0]["titulo"].startswith("Fundamentos") and top[0]["veces"] == 4
    assert len(dao.historial_socio(ids["lucia"])) == 5
    assert dao.resumen()["prestamos_activos"] == 4
    ok("reportes: mas prestados, historial, resumen")

    # ---- resenas en mongo
    msg = debe_fallar(dao.agregar_resena, soc_id=ids["carlos"], lib_id=ids["ficciones"], puntaje=5)
    assert "quien lo pidio" in msg                     # carlos nunca pidio ficciones
    dao.agregar_resena(soc_id=ids["lucia"], lib_id=ids["ficciones"], puntaje=5,
                       comentario="Clasico", etiquetas=["Clasico", " cuentos "])
    dao.agregar_resena(soc_id=ids["lucia"], lib_id=ids["bd"], puntaje=5,
                       etiquetas=["teoria", "recomendado"])
    dao.agregar_resena(soc_id=ids["carlos"], lib_id=ids["bd"], puntaje=3, etiquetas=["teoria"])
    assert "ya reseno" in debe_fallar(dao.agregar_resena, soc_id=ids["lucia"],
                                      lib_id=ids["ficciones"], puntaje=4)   # salta el indice unique
    debe_fallar(dao.agregar_resena, soc_id=ids["lucia"], lib_id=ids["bd"], puntaje=7)
    assert dao.resenas_de_libro(ids["ficciones"])[0]["etiquetas"] == ["clasico", "cuentos"]
    assert len(dao.resenas_de_libro(ids["bd"])) == 2
    assert len(dao.buscar_resenas_por_etiqueta("TEORIA")) == 2
    mejores = dao.mejores_libros()
    assert mejores[0]["lib_id"] == ids["ficciones"] and mejores[0]["promedio"] == 5
    assert mejores[1] == {"lib_id": ids["bd"], "titulo": mejores[1]["titulo"],
                          "promedio": 4.0, "resenas": 2}
    assert [m["lib_id"] for m in dao.mejores_libros(minimo_resenas=2)] == [ids["bd"]]
    assert dao.etiquetas_populares()[0] == {"etiqueta": "teoria", "cantidad": 2}
    dao.actualizar_resena(ids["carlos"], ids["bd"], puntaje=5)
    assert dao.mejores_libros(minimo_resenas=2)[0]["promedio"] == 5
    dao.eliminar_resena(ids["carlos"], ids["bd"])
    assert len(dao.resenas_de_libro(ids["bd"])) == 1
    debe_fallar(dao.eliminar_resena, ids["carlos"], ids["bd"])
    debe_fallar(dao.actualizar_resena, ids["carlos"], ids["bd"], puntaje=2)
    ok("MongoDB: resenas (CRUD, regla 'solo quien lo leyo', UNIQUE, agregaciones)")

    # ---- auditoria en mongo
    eventos = {e["evento"]: e["cantidad"] for e in dao.auditoria_por_evento()}
    assert eventos == {"PRESTAMO": 6, "DEVOLUCION": 2, "ALTA_SOCIO": 2,
                       "MULTA_PAGADA": 1, "BAJA_SOCIO": 1}
    ultima_devolucion = dao.auditoria(evento="DEVOLUCION", limite=1)[0]
    assert ultima_devolucion["dias_atraso"] == 6 and ultima_devolucion["multa"] == 3000
    assert "vence" in dao.auditoria(evento="PRESTAMO", limite=1)[0]
    ok("MongoDB: auditoria registra cada operacion con su propio esquema")

    # ---- redis: el ranking tiene que dar igual que en oracle
    ranking = dao.ranking_tiempo_real()
    assert ranking[0]["lib_id"] == ids["bd"] and ranking[0]["prestamos"] == 4
    assert {r["lib_id"]: r["prestamos"] for r in ranking} == \
           {f["lib_id"]: f["veces"] for f in dao.libros_mas_prestados()}
    assert dao.actividad_de_hoy() == {"prestamos": 6, "devoluciones": 2}

    # cache: la primera vez lee oracle, la segunda redis, y al prestar se borra
    dao.disponibilidad(ids["ficciones"])
    assert dao.ultima_fuente == "oracle"
    antes = dao.disponibilidad(ids["ficciones"])
    assert dao.ultima_fuente == "redis"
    assert 0 < dao.redis.ttl(cache.disponibilidad(ids["ficciones"])) <= 60
    dao.agregar_ejemplar(lib_id=ids["ficciones"], codigo_inventario="INV-F2")
    ana = dao.crear_socio(dni="30555666", nombre="Ana", apellido="Romero", tipo="EXTERNO")
    dao.prestar_libro(soc_id=ana, lib_id=ids["ficciones"])
    despues = dao.disponibilidad(ids["ficciones"])
    assert dao.ultima_fuente == "oracle" and despues["PRESTADO"] == antes["PRESTADO"] + 1

    # si se borra el ranking, inicializar_nosql lo vuelve a armar desde oracle
    dao.redis.delete(cache.RANKING_PRESTAMOS)
    dao.inicializar_nosql()
    assert dao.ranking_tiempo_real()[0]["prestamos"] == 4
    ok("Redis: ranking, contadores y cache con TTL e invalidacion")

    # ---- con redis caido el prestamo se guarda igual en oracle
    servidor_caido = fakeredis.FakeServer()
    servidor_caido.connected = False
    dao_sin_redis = BibliotecaDAO(str(dao.engine.url), mongo=dao.mongo,
                                  redis_cli=fakeredis.FakeRedis(server=servidor_caido))
    pre_id = dao_sin_redis.prestar_libro(soc_id=ana, lib_id=ids["bd"])
    assert dao_sin_redis.obtener_libro(ids["bd"]) and pre_id
    assert len(dao_sin_redis.avisos) == 1
    dao_sin_redis.disponibilidad(ids["bd"])
    assert dao_sin_redis.ultima_fuente == "oracle"
    ok("si Redis no responde, el prestamo se guarda en Oracle igual (con aviso)")

    # ---- validaciones de datos
    assert "DNI" in debe_fallar(dao.crear_socio, dni="12ab", nombre="X", apellido="Y", tipo="ALUMNO")
    assert "Falta" in debe_fallar(dao.crear_socio, dni="12345678", nombre=" ", apellido="Y",
                                  tipo="ALUMNO")
    assert "email" in debe_fallar(dao.crear_socio, dni="12345678", nombre="X", apellido="Y",
                                  tipo="ALUMNO", email="sin-arroba")
    assert "Solo se puede cambiar" in debe_fallar(dao.actualizar_socio, ids["lucia"], telefono="1")
    assert "No existe" in debe_fallar(dao.actualizar_socio, 999, nombre="X")
    assert "No existe" in debe_fallar(dao.dar_de_baja_socio, 999)
    assert "No existe" in debe_fallar(dao.disponibilidad, 999)
    assert "Falta" in debe_fallar(dao.crear_libro, isbn=" ", titulo="X", aut_id=1)
    assert "Anio" in debe_fallar(dao.crear_libro, isbn="333", titulo="X", aut_id=1, anio=3000)
    assert "puntaje" in debe_fallar(dao.agregar_resena, soc_id=ids["lucia"], lib_id=ids["bd"],
                                    puntaje=True)
    assert "dias" in debe_fallar(dao.prestar_libro, soc_id=ana, lib_id=ids["bd"], dias=0)
    pre_ana = dao.prestamos_activos(ana)[0]["pre_id"]
    assert "anterior" in debe_fallar(dao.devolver_libro, pre_ana,
                                     fecha_devolucion=HOY - timedelta(days=60))
    ok("validaciones: datos vacios o invalidos, ids que no existen, fechas imposibles")

    # ---- estados de los ejemplares
    copias = dao.listar_ejemplares(ids["bd"])
    prestada = next(e["eje_id"] for e in copias if e["estado"] == "PRESTADO")
    libre = next(e["eje_id"] for e in copias if e["estado"] == "DISPONIBLE")
    assert "devolverla" in debe_fallar(dao.cambiar_estado_ejemplar, prestada, "DISPONIBLE")
    assert "prestar_libro" in debe_fallar(dao.cambiar_estado_ejemplar, libre, "PRESTADO")
    assert "No existe" in debe_fallar(dao.cambiar_estado_ejemplar, 999, "BAJA")
    antes = dao.disponibilidad(ids["bd"])
    dao.cambiar_estado_ejemplar(libre, "reparacion")
    despues = dao.disponibilidad(ids["bd"])
    assert dao.ultima_fuente == "oracle" and despues["REPARACION"] == antes["REPARACION"] + 1
    assert dao.auditoria(evento="CAMBIO_ESTADO_EJEMPLAR", limite=1)[0]["estado"] == "REPARACION"
    ok("estados de ejemplares: PRESTADO solo por prestar/devolver, la cache se actualiza")

    dao.close()
    print("\nTODAS LAS PRUEBAS PASARON")


if __name__ == "__main__":
    main()
