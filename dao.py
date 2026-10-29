"""
DAO (Data Access Object) de la Biblioteca UNdeC.

Es la UNICA puerta de entrada a la base de datos. El resto del programa
(main.py, el notebook, una futura pagina web) llama a metodos como
`dao.prestar_libro(...)` y no sabe nada de SQL, de Oracle ni de conexiones.

Capas:
    main.py / notebook   ->  dao.py (BibliotecaDAO)  ->  db_models/ (arman las consultas)  ->  Oracle
"""
from datetime import date, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError

from config_vars import (BBDD_CONNECTION, DIAS_PRESTAMO, MAX_PRESTAMOS_ACTIVOS,
                         MULTA_POR_DIA)
from db_models import (Socios, Autores, Libros, Ejemplares, Prestamos, Multas,
                       TIPOS_SOCIO, ESTADOS_EJEMPLAR)


class BibliotecaError(Exception):
    """Error de negocio (ej.: 'el socio tiene multas'). Se muestra al usuario tal cual."""


def _a_fecha(valor):
    """Oracle devuelve DATE como datetime; lo pasamos a date para restar dias."""
    return valor.date() if isinstance(valor, datetime) else valor


class BibliotecaDAO:

    def __init__(self, url=BBDD_CONNECTION, echo=False):
        # El engine maneja un "pool" de conexiones: se abren cuando hacen falta
        # y se reutilizan. echo=True muestra en consola cada SQL que se ejecuta.
        self.engine = create_engine(url, echo=echo)

    def close(self):
        self.engine.dispose()

    # Permite usar:  with BibliotecaDAO() as dao: ...   (cierra solo al final)
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # =================================================================
    #  Metodos privados de ayuda (ejecutan las consultas)
    # =================================================================
    def _uno(self, query):
        """Ejecuta un SELECT y devuelve la primera fila como dict (o None)."""
        with self.engine.connect() as con:
            fila = con.execute(query).mappings().first()
            return dict(fila) if fila else None

    def _todos(self, query):
        """Ejecuta un SELECT y devuelve una lista de dicts."""
        with self.engine.connect() as con:
            return [dict(f) for f in con.execute(query).mappings().all()]

    def _insertar(self, query):
        """Ejecuta un INSERT ... RETURNING id y devuelve el id nuevo."""
        try:
            # engine.begin() = abre transaccion; COMMIT si todo sale bien,
            # ROLLBACK automatico si hay una excepcion.
            with self.engine.begin() as con:
                return con.execute(query).scalar_one()
        except IntegrityError as e:
            raise BibliotecaError(f"Dato duplicado o invalido: {e.orig}") from e

    def _modificar(self, query):
        """Ejecuta un UPDATE/DELETE y devuelve cuantas filas cambio."""
        try:
            with self.engine.begin() as con:
                return con.execute(query).rowcount
        except IntegrityError as e:
            raise BibliotecaError(f"No se puede modificar: {e.orig}") from e

    # =================================================================
    #  SOCIOS
    # =================================================================
    def listar_socios(self, *, solo_activos=False):
        return self._todos(Socios.todos(solo_activos=solo_activos))

    def obtener_socio(self, soc_id):
        return self._uno(Socios.por_id(soc_id))

    def buscar_socio_por_dni(self, dni):
        return self._uno(Socios.por_dni(dni))

    def crear_socio(self, *, dni, nombre, apellido, tipo, email=None):
        tipo = tipo.upper()
        if tipo not in TIPOS_SOCIO:
            raise BibliotecaError(f"Tipo invalido. Opciones: {', '.join(TIPOS_SOCIO)}")
        return self._insertar(Socios.insertar(
            dni=dni, nombre=nombre, apellido=apellido, email=email,
            tipo=tipo, fecha_alta=date.today(), activo=1))

    def actualizar_socio(self, soc_id, **cambios):
        """Ej.: dao.actualizar_socio(3, email='nuevo@mail.com')"""
        return self._modificar(Socios.actualizar(soc_id, **cambios))

    def dar_de_baja_socio(self, soc_id):
        return self._modificar(Socios.dar_de_baja(soc_id))

    # =================================================================
    #  AUTORES y LIBROS
    # =================================================================
    def listar_autores(self):
        return self._todos(Autores.todos())

    def crear_autor(self, *, nombre, nacionalidad=None):
        return self._insertar(Autores.insertar(nombre=nombre, nacionalidad=nacionalidad))

    def listar_libros(self, *, categoria=None):
        return self._todos(Libros.con_autor(categoria=categoria))

    def buscar_libros(self, texto):
        return self._todos(Libros.con_autor(texto=texto))

    def obtener_libro(self, lib_id):
        return self._uno(Libros.por_id(lib_id))

    def crear_libro(self, *, isbn, titulo, aut_id, anio=None, categoria=None):
        if self._uno(Autores.por_id(aut_id)) is None:
            raise BibliotecaError(f"No existe el autor {aut_id}")
        return self._insertar(Libros.insertar(
            isbn=isbn, titulo=titulo, aut_id=aut_id, anio=anio, categoria=categoria))

    # =================================================================
    #  EJEMPLARES
    # =================================================================
    def listar_ejemplares(self, lib_id):
        return self._todos(Ejemplares.de_libro(lib_id))

    def agregar_ejemplar(self, *, lib_id, codigo_inventario):
        if self.obtener_libro(lib_id) is None:
            raise BibliotecaError(f"No existe el libro {lib_id}")
        return self._insertar(Ejemplares.insertar(
            lib_id=lib_id, codigo_inventario=codigo_inventario, estado="DISPONIBLE"))

    def cambiar_estado_ejemplar(self, eje_id, estado):
        estado = estado.upper()
        if estado not in ESTADOS_EJEMPLAR:
            raise BibliotecaError(f"Estado invalido. Opciones: {', '.join(ESTADOS_EJEMPLAR)}")
        return self._modificar(Ejemplares.actualizar(eje_id, estado=estado))

    def disponibilidad(self, lib_id):
        """Devuelve {'DISPONIBLE': 2, 'PRESTADO': 1, ...} para un libro."""
        conteo = {estado: 0 for estado in ESTADOS_EJEMPLAR}
        for fila in self._todos(Ejemplares.conteo_por_estado(lib_id)):
            conteo[fila["estado"]] = fila["cantidad"]
        return conteo

    # =================================================================
    #  PRESTAMOS  (aca estan las TRANSACCIONES importantes)
    # =================================================================
    def prestar_libro(self, *, soc_id, lib_id, dias=DIAS_PRESTAMO, hoy=None):
        """
        Presta una copia disponible del libro al socio.
        Todo pasa en UNA transaccion: si falla una regla, no se guarda nada.
        Devuelve el id del prestamo creado.
        """
        hoy = hoy or date.today()
        with self.engine.begin() as con:
            # 1) el socio existe y esta activo
            socio = con.execute(Socios.por_id(soc_id)).mappings().first()
            if socio is None:
                raise BibliotecaError(f"No existe el socio {soc_id}")
            if socio["activo"] != 1:
                raise BibliotecaError("El socio esta dado de baja")

            # 2) no tiene multas sin pagar
            if con.execute(Multas.contar_pendientes(soc_id)).scalar_one() > 0:
                raise BibliotecaError("El socio tiene multas sin pagar")

            # 3) no supera el maximo de prestamos simultaneos
            activos = con.execute(Prestamos.contar_activos(soc_id)).scalar_one()
            if activos >= MAX_PRESTAMOS_ACTIVOS:
                raise BibliotecaError(f"El socio ya tiene {activos} prestamos activos "
                                      f"(maximo {MAX_PRESTAMOS_ACTIVOS})")

            # 4) buscar una copia DISPONIBLE y marcarla PRESTADO
            if con.execute(Libros.por_id(lib_id)).first() is None:
                raise BibliotecaError(f"No existe el libro {lib_id}")
            candidatos = con.execute(Ejemplares.disponibles_de_libro(lib_id)).scalars().all()
            eje_id = None
            for candidato in candidatos:
                if con.execute(Ejemplares.ocupar(candidato)).rowcount == 1:
                    eje_id = candidato
                    break
            if eje_id is None:
                raise BibliotecaError("No hay ejemplares disponibles de ese libro")

            # 5) registrar el prestamo
            return con.execute(Prestamos.insertar(
                eje_id=eje_id, soc_id=soc_id,
                fecha_prestamo=hoy,
                fecha_vencimiento=hoy + timedelta(days=dias),
            )).scalar_one()
        # al salir del "with" sin errores => COMMIT

    def devolver_libro(self, pre_id, *, fecha_devolucion=None):
        """
        Registra la devolucion, libera el ejemplar y, si hubo atraso,
        genera la multa. Todo en UNA transaccion.
        Devuelve {'pre_id', 'dias_atraso', 'multa'}.
        """
        fecha_devolucion = fecha_devolucion or date.today()
        with self.engine.begin() as con:
            prestamo = con.execute(Prestamos.por_id(pre_id)).mappings().first()
            if prestamo is None:
                raise BibliotecaError(f"No existe el prestamo {pre_id}")
            if prestamo["fecha_devolucion"] is not None:
                raise BibliotecaError("Ese prestamo ya fue devuelto")

            con.execute(Prestamos.registrar_devolucion(pre_id, fecha_devolucion))
            con.execute(Ejemplares.liberar(prestamo["eje_id"]))

            dias_atraso = (fecha_devolucion - _a_fecha(prestamo["fecha_vencimiento"])).days
            monto = 0
            if dias_atraso > 0:
                monto = dias_atraso * MULTA_POR_DIA
                con.execute(Multas.insertar(pre_id=pre_id, monto=monto, pagada=0))

        return {"pre_id": pre_id, "dias_atraso": max(dias_atraso, 0), "multa": monto}

    def prestamos_activos(self, soc_id=None):
        return self._todos(Prestamos.activos(soc_id))

    def prestamos_vencidos(self, hoy=None):
        hoy = hoy or date.today()
        filas = self._todos(Prestamos.vencidos(hoy))
        for f in filas:   # dato calculado: cuantos dias lleva vencido
            f["dias_atraso"] = (hoy - _a_fecha(f["fecha_vencimiento"])).days
        return filas

    def historial_socio(self, soc_id):
        return self._todos(Prestamos.historial_socio(soc_id))

    # =================================================================
    #  MULTAS
    # =================================================================
    def multas_pendientes(self, soc_id=None):
        return self._todos(Multas.pendientes(soc_id))

    def pagar_multa(self, mul_id):
        if self._modificar(Multas.pagar(mul_id)) == 0:
            raise BibliotecaError(f"La multa {mul_id} no existe o ya estaba pagada")
        return True

    # =================================================================
    #  REPORTES
    # =================================================================
    def libros_mas_prestados(self, top=5):
        return self._todos(Prestamos.libros_mas_prestados(top))

    def resumen(self):
        """Numeros generales para mostrar en un tablero."""
        return {
            "socios_activos": len(self.listar_socios(solo_activos=True)),
            "libros": len(self.listar_libros()),
            "prestamos_activos": len(self.prestamos_activos()),
            "prestamos_vencidos": len(self.prestamos_vencidos()),
            "multas_pendientes": len(self.multas_pendientes()),
        }


# Prueba rapida:  python dao.py
if __name__ == "__main__":
    with BibliotecaDAO() as dao:
        print("Resumen:", dao.resumen())
        for libro in dao.listar_libros():
            print(f"  [{libro['lib_id']}] {libro['titulo']} - {libro['autor']}")
