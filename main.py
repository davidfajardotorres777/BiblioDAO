"""
Menu de consola para usar el DAO.
Ejecutar:  python main.py
"""
from dao import BibliotecaDAO, BibliotecaError, ERRORES_CONEXION


def mostrar(filas, columnas):
    """Imprime una lista de dicts como tabla simple."""
    if not filas:
        print("  (sin resultados)")
        return
    anchos = {c: max(len(c), *(len(str(f.get(c, ""))) for f in filas)) for c in columnas}
    print("  " + " | ".join(c.upper().ljust(anchos[c]) for c in columnas))
    print("  " + "-+-".join("-" * anchos[c] for c in columnas))
    for f in filas:
        print("  " + " | ".join(str(f.get(c, "")).ljust(anchos[c]) for c in columnas))


def pedir_int(texto):
    while True:
        valor = input(texto).strip()
        if valor.isdigit():
            return int(valor)
        print("  Ingresa un numero.")


MENU = """
========= BIBLIOTECA UNdeC =========
 1. Listar libros
 2. Buscar libro por titulo
 3. Ver disponibilidad de un libro
 4. Listar socios
 5. Registrar socio
 6. Prestar libro
 7. Devolver libro
 8. Prestamos activos
 9. Prestamos vencidos
10. Multas pendientes / pagar multa
11. Historial de un socio
12. Libros mas prestados
13. Resumen
---------- MongoDB / Redis ----------
14. Resenas de un libro            (Mongo)
15. Escribir una resena            (Mongo)
16. Mejores libros por puntaje     (Mongo)
17. Ranking en tiempo real         (Redis)
18. Auditoria de operaciones       (Mongo)
-------------------------------------
19. Administracion
 0. Salir
"""

MENU_ADMIN = """
----------- ADMINISTRACION -----------
 1. Agregar autor
 2. Agregar libro
 3. Agregar ejemplar (copia) a un libro
 4. Ver ejemplares de un libro
 5. Cambiar estado de un ejemplar
 6. Modificar datos de un socio
 7. Dar de baja un socio
 8. Modificar una resena
 9. Borrar una resena
 0. Volver
"""


def administracion(dao):
    print(MENU_ADMIN)
    opcion = input("Opcion: ").strip()
    if opcion == "1":
        mostrar(dao.listar_autores(), ["aut_id", "nombre", "nacionalidad"])
        nombre = input("Nombre: ")
        nacionalidad = input("Nacionalidad (opcional): ")
        aut_id = dao.crear_autor(nombre=nombre, nacionalidad=nacionalidad)
        print(f"  Autor creado con id {aut_id}")
    elif opcion == "2":
        mostrar(dao.listar_autores(), ["aut_id", "nombre"])
        isbn = input("ISBN: ")
        titulo = input("Titulo: ")
        aut_id = pedir_int("ID del autor: ")
        anio = input("Anio (opcional): ").strip()
        categoria = input("Categoria (opcional): ")
        lib_id = dao.crear_libro(isbn=isbn, titulo=titulo, aut_id=aut_id,
                                 anio=int(anio) if anio.isdigit() else None,
                                 categoria=categoria)
        print(f"  Libro creado con id {lib_id} (todavia no tiene copias)")
    elif opcion == "3":
        eje_id = dao.agregar_ejemplar(lib_id=pedir_int("ID del libro: "),
                                      codigo_inventario=input("Codigo de inventario: "))
        print(f"  Ejemplar creado con id {eje_id}")
    elif opcion == "4":
        mostrar(dao.listar_ejemplares(pedir_int("ID del libro: ")),
                ["eje_id", "codigo_inventario", "estado"])
    elif opcion == "5":
        dao.cambiar_estado_ejemplar(pedir_int("ID del ejemplar: "),
                                    input("Nuevo estado (DISPONIBLE/REPARACION/BAJA): "))
        print("  Estado cambiado.")
    elif opcion == "6":
        soc_id = pedir_int("ID socio: ")
        print("  Dejar vacio lo que no se cambia.")
        cambios = {campo: valor for campo in ("nombre", "apellido", "email", "tipo")
                   if (valor := input(f"  {campo.capitalize()}: ").strip())}
        dao.actualizar_socio(soc_id, **cambios)
        print("  Socio actualizado.")
    elif opcion == "7":
        dao.dar_de_baja_socio(pedir_int("ID socio: "))
        print("  Socio dado de baja.")
    elif opcion == "8":
        soc_id = pedir_int("ID socio: ")
        lib_id = pedir_int("ID libro: ")
        puntaje = pedir_int("Nuevo puntaje (1 a 5): ")
        comentario = input("Nuevo comentario: ")
        dao.actualizar_resena(soc_id, lib_id, puntaje=puntaje, comentario=comentario)
        print("  Resena actualizada.")
    elif opcion == "9":
        dao.eliminar_resena(pedir_int("ID socio: "), pedir_int("ID libro: "))
        print("  Resena borrada.")


def main():
    with BibliotecaDAO() as dao:
        while True:
            print(MENU)
            opcion = input("Opcion: ").strip()
            try:
                if opcion == "1":
                    mostrar(dao.listar_libros(), ["lib_id", "titulo", "autor", "categoria", "anio"])
                elif opcion == "2":
                    texto = input("Texto a buscar: ")
                    mostrar(dao.buscar_libros(texto), ["lib_id", "titulo", "autor"])
                elif opcion == "3":
                    lib_id = pedir_int("ID del libro: ")
                    for estado, cantidad in dao.disponibilidad(lib_id).items():
                        print(f"  {estado:<11} {cantidad}")
                    print(f"  (dato leido de: {dao.ultima_fuente})")
                elif opcion == "4":
                    mostrar(dao.listar_socios(),
                            ["soc_id", "dni", "apellido", "nombre", "tipo", "activo"])
                elif opcion == "5":
                    nuevo = dao.crear_socio(
                        dni=input("DNI: "), nombre=input("Nombre: "),
                        apellido=input("Apellido: "),
                        tipo=input("Tipo (ALUMNO/DOCENTE/EXTERNO): "),
                        email=input("Email (opcional): ") or None)
                    print(f"  Socio creado con id {nuevo}")
                elif opcion == "6":
                    pre_id = dao.prestar_libro(soc_id=pedir_int("ID socio: "),
                                               lib_id=pedir_int("ID libro: "))
                    print(f"  Prestamo registrado (id {pre_id})")
                elif opcion == "7":
                    r = dao.devolver_libro(pedir_int("ID prestamo: "))
                    print(f"  Devuelto. Dias de atraso: {r['dias_atraso']}  Multa: ${r['multa']}")
                elif opcion == "8":
                    mostrar(dao.prestamos_activos(),
                            ["pre_id", "socio", "titulo", "fecha_vencimiento"])
                elif opcion == "9":
                    mostrar(dao.prestamos_vencidos(),
                            ["pre_id", "socio", "titulo", "fecha_vencimiento", "dias_atraso"])
                elif opcion == "10":
                    mostrar(dao.multas_pendientes(), ["mul_id", "socio", "monto"])
                    mul = input("ID de multa a pagar (Enter para volver): ").strip()
                    if mul.isdigit():
                        dao.pagar_multa(int(mul))
                        print("  Multa pagada.")
                elif opcion == "11":
                    mostrar(dao.historial_socio(pedir_int("ID socio: ")),
                            ["pre_id", "titulo", "fecha_prestamo", "fecha_devolucion"])
                elif opcion == "12":
                    mostrar(dao.libros_mas_prestados(), ["titulo", "autor", "veces"])
                elif opcion == "13":
                    for clave, valor in dao.resumen().items():
                        print(f"  {clave:<20} {valor}")
                elif opcion == "14":
                    mostrar(dao.resenas_de_libro(pedir_int("ID del libro: ")),
                            ["socio", "puntaje", "comentario", "etiquetas"])
                elif opcion == "15":
                    dao.agregar_resena(
                        soc_id=pedir_int("ID socio: "), lib_id=pedir_int("ID libro: "),
                        puntaje=pedir_int("Puntaje (1 a 5): "),
                        comentario=input("Comentario: "),
                        etiquetas=input("Etiquetas separadas por coma: ").split(","))
                    print("  Resena guardada en MongoDB.")
                elif opcion == "16":
                    mostrar(dao.mejores_libros(), ["titulo", "promedio", "resenas"])
                elif opcion == "17":
                    mostrar(dao.ranking_tiempo_real(), ["titulo", "prestamos"])
                    print(f"  Actividad de hoy: {dao.actividad_de_hoy() or 'sin movimientos'}")
                elif opcion == "18":
                    mostrar(dao.auditoria(limite=10), ["fecha", "evento", "soc_id", "pre_id", "lib_id"])
                elif opcion == "19":
                    administracion(dao)
                elif opcion == "0":
                    break
                else:
                    print("  Opcion invalida.")
            except BibliotecaError as e:
                print(f"  [!] {e}")
            except ERRORES_CONEXION as e:
                print(f"  [!] No responde la base de datos ({type(e).__name__}). Revisar: docker ps")
            input("\n(Enter para continuar)")


if __name__ == "__main__":
    main()
