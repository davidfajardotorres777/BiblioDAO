"""
Menu de consola para usar el DAO.
Ejecutar:  python main.py
"""
from dao import BibliotecaDAO, BibliotecaError


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
 0. Salir
"""


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
                elif opcion == "0":
                    break
                else:
                    print("  Opcion invalida.")
            except BibliotecaError as e:
                print(f"  [!] {e}")
            input("\n(Enter para continuar)")


if __name__ == "__main__":
    main()
