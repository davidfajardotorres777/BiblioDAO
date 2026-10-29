"""
Pruebas automaticas del DAO SIN necesitar Oracle.

Usa SQLite (viene con Python) como base temporal: crea las tablas a partir
de db_models, carga datos con el propio DAO y prueba cada metodo.
Sirve para demostrar que la logica funciona y que el DAO es independiente
del motor: solo cambia la URL de conexion.

Ejecutar desde la carpeta del proyecto:   python -m tests.test_dao
"""
import os
import tempfile
import warnings
from datetime import date, timedelta

from sqlalchemy import exc as sa_exc

from dao import BibliotecaDAO, BibliotecaError
from db_models import metadata

warnings.filterwarnings("ignore", category=sa_exc.SAWarning)  # Decimal en SQLite

HOY = date.today()


def preparar_dao():
    archivo = os.path.join(tempfile.mkdtemp(), "biblio_test.db")
    dao = BibliotecaDAO(f"sqlite:///{archivo}")
    metadata.create_all(dao.engine)       # en Oracle esto lo hace dbscripts.sql
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

    # ---- Sin copias disponibles => error y NO queda nada a medias (rollback)
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

    dao.close()
    print("\nTODAS LAS PRUEBAS PASARON")


if __name__ == "__main__":
    main()
