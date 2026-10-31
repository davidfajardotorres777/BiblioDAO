"""
Por si docker no anda: crea biblio_demo.db (sqlite) con los mismos datos
de prueba que dbscripts.sql.

    python demo_sqlite.py
    (Windows PowerShell)  $env:BBDD_CONNECTION="sqlite:///biblio_demo.db"; $env:USAR_NOSQL="0"; python main.py
    (Linux / Git Bash)    BBDD_CONNECTION=sqlite:///biblio_demo.db USAR_NOSQL=0 python main.py

El DAO es el mismo, solo cambia la url. Con USAR_NOSQL=0 no se usan mongo ni redis.
"""
import os
import warnings
from datetime import date, timedelta

from sqlalchemy import exc as sa_exc

from dao import BibliotecaDAO
from db_models import metadata

warnings.filterwarnings("ignore", category=sa_exc.SAWarning)

ARCHIVO = "biblio_demo.db"
HOY = date.today()


def main():
    if os.path.exists(ARCHIVO):
        os.remove(ARCHIVO)
    with BibliotecaDAO(f"sqlite:///{ARCHIVO}", usar_nosql=False) as dao:
        metadata.create_all(dao.engine)

        a = {n: dao.crear_autor(nombre=n, nacionalidad=p) for n, p in [
            ("Jorge Luis Borges", "Argentina"), ("Julio Cortazar", "Argentina"),
            ("Ramez Elmasri", "Estados Unidos"), ("Abraham Silberschatz", "Estados Unidos"),
            ("Ian Sommerville", "Reino Unido")]}

        l = {}
        for isbn, titulo, anio, cat, autor in [
            ("978-8499089515", "Ficciones", 1944, "Literatura", "Jorge Luis Borges"),
            ("978-8466331623", "El Aleph", 1949, "Literatura", "Jorge Luis Borges"),
            ("978-8437604572", "Rayuela", 1963, "Literatura", "Julio Cortazar"),
            ("978-8478290857", "Fundamentos de Sistemas de Bases de Datos", 2007, "Informatica", "Ramez Elmasri"),
            ("978-8448146443", "Fundamentos de Bases de Datos", 2006, "Informatica", "Abraham Silberschatz"),
            ("978-6073206037", "Ingenieria de Software", 2011, "Informatica", "Ian Sommerville")]:
            l[titulo] = dao.crear_libro(isbn=isbn, titulo=titulo, anio=anio,
                                        categoria=cat, aut_id=a[autor])

        for cod, titulo in [("INV-001", "Ficciones"), ("INV-002", "Ficciones"),
                            ("INV-003", "El Aleph"), ("INV-004", "Rayuela"),
                            ("INV-005", "Rayuela"),
                            ("INV-006", "Fundamentos de Sistemas de Bases de Datos"),
                            ("INV-007", "Fundamentos de Sistemas de Bases de Datos"),
                            ("INV-008", "Fundamentos de Sistemas de Bases de Datos"),
                            ("INV-009", "Fundamentos de Bases de Datos"),
                            ("INV-010", "Fundamentos de Bases de Datos"),
                            ("INV-011", "Ingenieria de Software")]:
            eje = dao.agregar_ejemplar(lib_id=l[titulo], codigo_inventario=cod)
            if cod == "INV-010":
                dao.cambiar_estado_ejemplar(eje, "REPARACION")

        s = {}
        for dni, nom, ape, mail, tipo in [
            ("40111222", "Lucia", "Herrera", "lherrera@undec.edu.ar", "ALUMNO"),
            ("41222333", "Martin", "Quiroga", "mquiroga@undec.edu.ar", "ALUMNO"),
            ("42333444", "Sofia", "Andrada", "sandrada@undec.edu.ar", "ALUMNO"),
            ("25444555", "Carlos", "Vega", "cvega@undec.edu.ar", "DOCENTE"),
            ("30555666", "Ana", "Romero", "ana.romero@mail.com", "EXTERNO")]:
            s[nom] = dao.crear_socio(dni=dni, nombre=nom, apellido=ape, email=mail, tipo=tipo)

        bd = l["Fundamentos de Sistemas de Bases de Datos"]
        # Carlos: devuelto a tiempo (Ficciones)
        p = dao.prestar_libro(soc_id=s["Carlos"], lib_id=l["Ficciones"], hoy=HOY - timedelta(days=40))
        dao.devolver_libro(p, fecha_devolucion=HOY - timedelta(days=30))
        # Sofia: devuelto 4 dias tarde => multa $2000
        p = dao.prestar_libro(soc_id=s["Sofia"], lib_id=bd, hoy=HOY - timedelta(days=30))
        dao.devolver_libro(p, fecha_devolucion=HOY - timedelta(days=12))
        # Lucia: activo al dia ; Martin: activo vencido (Rayuela)
        dao.prestar_libro(soc_id=s["Lucia"], lib_id=bd, hoy=HOY - timedelta(days=3))
        dao.prestar_libro(soc_id=s["Martin"], lib_id=l["Rayuela"], hoy=HOY - timedelta(days=20))

        print("Base demo creada:", ARCHIVO)
        print(dao.resumen())


if __name__ == "__main__":
    main()
