"""
DAO de la biblioteca.

Todo el acceso a las bases pasa por esta clase. main.py y el notebook
solo llaman metodos (dao.prestar_libro(...), dao.agregar_resena(...)) y
no saben nada de SQL ni de conexiones.

Se usan tres bases:
  - Oracle: socios, libros, ejemplares, prestamos y multas
  - MongoDB: resenas de libros y auditoria
  - Redis: ranking de prestamos, cache de disponibilidad y contadores

Las consultas las arman las clases de db_models/ y aca se ejecutan.
"""
from datetime import date, datetime, timedelta

import redis
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError
from redis.exceptions import RedisError
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError

from config_vars import (BBDD_CONNECTION, DIAS_PRESTAMO, MAX_PRESTAMOS_ACTIVOS,
                         MULTA_POR_DIA, USAR_NOSQL, MONGO_URI, MONGO_DB, REDIS_URL,
                         CACHE_TTL_SEGUNDOS)
from db_models import (Socios, Autores, Libros, Ejemplares, Prestamos, Multas,
                       TIPOS_SOCIO, ESTADOS_EJEMPLAR,
                       Resenas, PUNTAJE_MIN, PUNTAJE_MAX, Auditoria, cache)

ERRORES_NOSQL = (PyMongoError, RedisError)


class BibliotecaError(Exception):
    """Errores de las reglas de negocio, el mensaje se le muestra al usuario."""


def _a_fecha(valor):
    # oracle devuelve los DATE como datetime, lo paso a date para poder restar dias
    return valor.date() if isinstance(valor, datetime) else valor


class BibliotecaDAO:

    def __init__(self, url=BBDD_CONNECTION, echo=False, *,
                 mongo=None, redis_cli=None, usar_nosql=USAR_NOSQL):
        # con echo=True se imprime cada sentencia SQL que se manda
        self.engine = create_engine(url, echo=echo)

        # mongo y redis se pueden pasar desde afuera (en los tests uso mongomock
        # y fakeredis), si no se crean con lo que hay en config_vars
        self.mongo = self.redis = None
        if usar_nosql or mongo is not None or redis_cli is not None:
            self.mongo = mongo if mongo is not None else \
                MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)[MONGO_DB]
            self.redis = redis_cli if redis_cli is not None else \
                redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=3)
        self.avisos = []            # errores de mongo/redis que no cortaron la operacion
        self.ultima_fuente = None   # "redis" u "oracle", para saber de donde salio la disponibilidad

    def close(self):
        self.engine.dispose()
        if self.mongo is not None:
            self.mongo.client.close()
        if self.redis is not None:
            self.redis.close()

    # para poder usar  with BibliotecaDAO() as dao:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ---------------------------------------------------------------
    # metodos internos
    # ---------------------------------------------------------------
    def _uno(self, query):
        """Primera fila del select como dict, o None."""
        with self.engine.connect() as con:
            fila = con.execute(query).mappings().first()
            return dict(fila) if fila else None

    def _todos(self, query):
        """Todas las filas del select como lista de dicts."""
        with self.engine.connect() as con:
            return [dict(f) for f in con.execute(query).mappings().all()]

    def _insertar(self, query):
        """Ejecuta un INSERT ... RETURNING y devuelve el id nuevo."""
        try:
            # begin() hace commit al final, o rollback si salta una excepcion
            with self.engine.begin() as con:
                return con.execute(query).scalar_one()
        except IntegrityError as e:
            raise BibliotecaError(f"Dato duplicado o invalido: {e.orig}") from e

    def _modificar(self, query):
        """UPDATE o DELETE, devuelve cuantas filas cambiaron."""
        try:
            with self.engine.begin() as con:
                return con.execute(query).rowcount
        except IntegrityError as e:
            raise BibliotecaError(f"No se puede modificar: {e.orig}") from e

    def _requiere_nosql(self):
        if self.mongo is None or self.redis is None:
            raise BibliotecaError("MongoDB/Redis no estan habilitados (USAR_NOSQL=0)")

    def _sincronizar(self, accion):
        # lo de mongo y redis se hace despues del commit en oracle.
        # si alguno esta caido no se deshace nada, solo queda anotado el aviso
        if self.mongo is None:
            return
        try:
            accion()
        except ERRORES_NOSQL as e:
            aviso = f"[aviso NoSQL] {type(e).__name__}: {e}"
            self.avisos.append(aviso)
            print(aviso)

    def _auditar(self, evento, **datos):
        self.mongo[Auditoria.coleccion].insert_one(Auditoria.documento(evento, **datos))

    def _invalidar_disponibilidad(self, lib_id):
        # borro la clave asi la proxima lectura va a oracle
        self.redis.delete(cache.disponibilidad(lib_id))

    def _contar_actividad(self, campo):
        clave = cache.actividad()
        self.redis.hincrby(clave, campo, 1)
        self.redis.expire(clave, cache.ACTIVIDAD_TTL_SEGUNDOS)

    @staticmethod
    def _sin_object_id(doc):
        # el _id de mongo es un ObjectId, lo paso a string para mostrarlo
        doc["_id"] = str(doc["_id"])
        return doc

    # ---------------------------------------------------------------
    # socios
    # ---------------------------------------------------------------
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
        soc_id = self._insertar(Socios.insertar(
            dni=dni, nombre=nombre, apellido=apellido, email=email,
            tipo=tipo, fecha_alta=date.today(), activo=1))
        self._sincronizar(lambda: self._auditar("ALTA_SOCIO", soc_id=soc_id, dni=dni, tipo=tipo))
        return soc_id

    def actualizar_socio(self, soc_id, **cambios):
        # ej: dao.actualizar_socio(3, email="nuevo@mail.com")
        return self._modificar(Socios.actualizar(soc_id, **cambios))

    def dar_de_baja_socio(self, soc_id):
        filas = self._modificar(Socios.dar_de_baja(soc_id))
        if filas:
            self._sincronizar(lambda: self._auditar("BAJA_SOCIO", soc_id=soc_id))
        return filas

    # ---------------------------------------------------------------
    # autores y libros
    # ---------------------------------------------------------------
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

    # ---------------------------------------------------------------
    # ejemplares
    # ---------------------------------------------------------------
    def listar_ejemplares(self, lib_id):
        return self._todos(Ejemplares.de_libro(lib_id))

    def agregar_ejemplar(self, *, lib_id, codigo_inventario):
        if self.obtener_libro(lib_id) is None:
            raise BibliotecaError(f"No existe el libro {lib_id}")
        eje_id = self._insertar(Ejemplares.insertar(
            lib_id=lib_id, codigo_inventario=codigo_inventario, estado="DISPONIBLE"))
        self._sincronizar(lambda: self._invalidar_disponibilidad(lib_id))
        return eje_id

    def cambiar_estado_ejemplar(self, eje_id, estado):
        estado = estado.upper()
        if estado not in ESTADOS_EJEMPLAR:
            raise BibliotecaError(f"Estado invalido. Opciones: {', '.join(ESTADOS_EJEMPLAR)}")
        filas = self._modificar(Ejemplares.actualizar(eje_id, estado=estado))
        ejemplar = self._uno(Ejemplares.por_id(eje_id))
        if filas and ejemplar:
            def sincronizar():
                self._invalidar_disponibilidad(ejemplar["lib_id"])
                self._auditar("CAMBIO_ESTADO_EJEMPLAR", eje_id=eje_id,
                              lib_id=ejemplar["lib_id"], estado=estado)
            self._sincronizar(sincronizar)
        return filas

    def disponibilidad(self, lib_id):
        """
        Cuantas copias hay en cada estado, ej: {'DISPONIBLE': 2, 'PRESTADO': 1, ...}

        Primero se fija en redis. Si no esta, lo cuenta en oracle y lo deja
        guardado en redis por CACHE_TTL_SEGUNDOS. Cuando se presta o se
        devuelve un libro la clave se borra para no mostrar datos viejos.
        """
        clave = cache.disponibilidad(lib_id)
        if self.redis is not None:
            try:
                guardado = self.redis.hgetall(clave)
                if guardado:
                    self.ultima_fuente = "redis"
                    return {estado: int(guardado.get(estado, 0)) for estado in ESTADOS_EJEMPLAR}
            except RedisError as e:
                self.avisos.append(f"[aviso NoSQL] Redis no responde, se usa Oracle: {e}")

        conteo = {estado: 0 for estado in ESTADOS_EJEMPLAR}
        for fila in self._todos(Ejemplares.conteo_por_estado(lib_id)):
            conteo[fila["estado"]] = fila["cantidad"]
        self.ultima_fuente = "oracle"

        def guardar_en_cache():
            self.redis.hset(clave, mapping=conteo)
            self.redis.expire(clave, CACHE_TTL_SEGUNDOS)
        self._sincronizar(guardar_en_cache)
        return conteo

    # ---------------------------------------------------------------
    # prestamos
    # ---------------------------------------------------------------
    def prestar_libro(self, *, soc_id, lib_id, dias=DIAS_PRESTAMO, hoy=None):
        """
        Presta una copia disponible del libro y devuelve el id del prestamo.
        Va todo en una sola transaccion, si alguna validacion falla no se
        guarda nada.
        """
        hoy = hoy or date.today()
        with self.engine.begin() as con:
            socio = con.execute(Socios.por_id(soc_id)).mappings().first()
            if socio is None:
                raise BibliotecaError(f"No existe el socio {soc_id}")
            if socio["activo"] != 1:
                raise BibliotecaError("El socio esta dado de baja")

            if con.execute(Multas.contar_pendientes(soc_id)).scalar_one() > 0:
                raise BibliotecaError("El socio tiene multas sin pagar")

            activos = con.execute(Prestamos.contar_activos(soc_id)).scalar_one()
            if activos >= MAX_PRESTAMOS_ACTIVOS:
                raise BibliotecaError(f"El socio ya tiene {activos} prestamos activos "
                                      f"(maximo {MAX_PRESTAMOS_ACTIVOS})")

            if con.execute(Libros.por_id(lib_id)).first() is None:
                raise BibliotecaError(f"No existe el libro {lib_id}")

            # el update solo pasa si la copia sigue DISPONIBLE, si otro la
            # agarro antes rowcount da 0 y pruebo con la siguiente
            candidatos = con.execute(Ejemplares.disponibles_de_libro(lib_id)).scalars().all()
            eje_id = None
            for candidato in candidatos:
                if con.execute(Ejemplares.ocupar(candidato)).rowcount == 1:
                    eje_id = candidato
                    break
            if eje_id is None:
                raise BibliotecaError("No hay ejemplares disponibles de ese libro")

            vence = hoy + timedelta(days=dias)
            pre_id = con.execute(Prestamos.insertar(
                eje_id=eje_id, soc_id=soc_id,
                fecha_prestamo=hoy,
                fecha_vencimiento=vence,
            )).scalar_one()
        # aca ya se hizo el commit

        def sincronizar():
            self._auditar("PRESTAMO", pre_id=pre_id, soc_id=soc_id, lib_id=lib_id,
                          eje_id=eje_id, vence=vence.isoformat())
            self.redis.zincrby(cache.RANKING_PRESTAMOS, 1, lib_id)
            self._invalidar_disponibilidad(lib_id)
            self._contar_actividad("prestamos")
        self._sincronizar(sincronizar)
        return pre_id

    def devolver_libro(self, pre_id, *, fecha_devolucion=None):
        """
        Registra la devolucion y libera la copia. Si se paso de la fecha
        genera la multa. Devuelve {'pre_id', 'dias_atraso', 'multa'}.
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
            lib_id = con.execute(Ejemplares.por_id(prestamo["eje_id"])).mappings().one()["lib_id"]

            dias_atraso = (fecha_devolucion - _a_fecha(prestamo["fecha_vencimiento"])).days
            monto = 0
            if dias_atraso > 0:
                monto = dias_atraso * MULTA_POR_DIA
                con.execute(Multas.insertar(pre_id=pre_id, monto=monto, pagada=0))

        def sincronizar():
            self._auditar("DEVOLUCION", pre_id=pre_id, soc_id=prestamo["soc_id"],
                          lib_id=lib_id, dias_atraso=max(dias_atraso, 0), multa=monto)
            self._invalidar_disponibilidad(lib_id)
            self._contar_actividad("devoluciones")
        self._sincronizar(sincronizar)
        return {"pre_id": pre_id, "dias_atraso": max(dias_atraso, 0), "multa": monto}

    def prestamos_activos(self, soc_id=None):
        return self._todos(Prestamos.activos(soc_id))

    def prestamos_vencidos(self, hoy=None):
        hoy = hoy or date.today()
        filas = self._todos(Prestamos.vencidos(hoy))
        for f in filas:
            f["dias_atraso"] = (hoy - _a_fecha(f["fecha_vencimiento"])).days
        return filas

    def historial_socio(self, soc_id):
        return self._todos(Prestamos.historial_socio(soc_id))

    # ---------------------------------------------------------------
    # multas
    # ---------------------------------------------------------------
    def multas_pendientes(self, soc_id=None):
        return self._todos(Multas.pendientes(soc_id))

    def pagar_multa(self, mul_id):
        if self._modificar(Multas.pagar(mul_id)) == 0:
            raise BibliotecaError(f"La multa {mul_id} no existe o ya estaba pagada")
        self._sincronizar(lambda: self._auditar("MULTA_PAGADA", mul_id=mul_id))
        return True

    # ---------------------------------------------------------------
    # reportes
    # ---------------------------------------------------------------
    def libros_mas_prestados(self, top=5):
        return self._todos(Prestamos.libros_mas_prestados(top))

    def resumen(self):
        return {
            "socios_activos": len(self.listar_socios(solo_activos=True)),
            "libros": len(self.listar_libros()),
            "prestamos_activos": len(self.prestamos_activos()),
            "prestamos_vencidos": len(self.prestamos_vencidos()),
            "multas_pendientes": len(self.multas_pendientes()),
        }

    # ---------------------------------------------------------------
    # resenas (mongo)
    # ---------------------------------------------------------------
    def agregar_resena(self, *, soc_id, lib_id, puntaje, comentario="", etiquetas=()):
        """
        Guarda una resena en mongo. Controles:
        - puntaje de 1 a 5
        - el socio y el libro tienen que existir (oracle)
        - el socio tiene que haber pedido el libro alguna vez (oracle)
        - una sola resena por socio y libro (indice unique en mongo)
        """
        self._requiere_nosql()
        if not isinstance(puntaje, int) or not PUNTAJE_MIN <= puntaje <= PUNTAJE_MAX:
            raise BibliotecaError(f"El puntaje va de {PUNTAJE_MIN} a {PUNTAJE_MAX}")
        socio = self.obtener_socio(soc_id)
        if socio is None:
            raise BibliotecaError(f"No existe el socio {soc_id}")
        libro = self.obtener_libro(lib_id)
        if libro is None:
            raise BibliotecaError(f"No existe el libro {lib_id}")
        with self.engine.connect() as con:
            veces = con.execute(Prestamos.contar_de_socio_y_libro(soc_id, lib_id)).scalar_one()
        if veces == 0:
            raise BibliotecaError("Solo puede resenar un libro quien lo pidio prestado")

        documento = Resenas.documento(
            lib_id=lib_id, soc_id=soc_id, socio=f"{socio['apellido']}, {socio['nombre']}",
            titulo=libro["titulo"], puntaje=puntaje, comentario=comentario,
            etiquetas=list(etiquetas))
        try:
            return str(self.mongo[Resenas.coleccion].insert_one(documento).inserted_id)
        except DuplicateKeyError as e:
            raise BibliotecaError("Ese socio ya reseno ese libro (usar actualizar_resena)") from e

    def resenas_de_libro(self, lib_id):
        self._requiere_nosql()
        cursor = self.mongo[Resenas.coleccion].find(Resenas.de_libro(lib_id)).sort("fecha", -1)
        return [self._sin_object_id(d) for d in cursor]

    def buscar_resenas_por_etiqueta(self, etiqueta):
        self._requiere_nosql()
        cursor = self.mongo[Resenas.coleccion].find(Resenas.con_etiqueta(etiqueta)).sort("puntaje", -1)
        return [self._sin_object_id(d) for d in cursor]

    def actualizar_resena(self, soc_id, lib_id, **cambios):
        # ej: dao.actualizar_resena(1, 4, puntaje=4, etiquetas=["denso"])
        self._requiere_nosql()
        puntaje = cambios.get("puntaje")
        if puntaje is not None and (not isinstance(puntaje, int)
                                    or not PUNTAJE_MIN <= puntaje <= PUNTAJE_MAX):
            raise BibliotecaError(f"El puntaje va de {PUNTAJE_MIN} a {PUNTAJE_MAX}")
        r = self.mongo[Resenas.coleccion].update_one(
            Resenas.de_socio_y_libro(soc_id, lib_id), Resenas.cambios(**cambios))
        if r.matched_count == 0:
            raise BibliotecaError("No existe esa resena")
        return r.modified_count

    def eliminar_resena(self, soc_id, lib_id):
        self._requiere_nosql()
        r = self.mongo[Resenas.coleccion].delete_one(Resenas.de_socio_y_libro(soc_id, lib_id))
        if r.deleted_count == 0:
            raise BibliotecaError("No existe esa resena")
        return True

    def mejores_libros(self, top=5, minimo_resenas=1):
        self._requiere_nosql()
        filas = self.mongo[Resenas.coleccion].aggregate(Resenas.mejores_libros(top, minimo_resenas))
        return [{"lib_id": f["_id"], "titulo": f["titulo"],
                 "promedio": round(f["promedio"], 2), "resenas": f["resenas"]} for f in filas]

    def etiquetas_populares(self, top=10):
        self._requiere_nosql()
        filas = self.mongo[Resenas.coleccion].aggregate(Resenas.etiquetas_populares(top))
        return [{"etiqueta": f["_id"], "cantidad": f["cantidad"]} for f in filas]

    # ---------------------------------------------------------------
    # auditoria (mongo)
    # ---------------------------------------------------------------
    def auditoria(self, evento=None, limite=20):
        self._requiere_nosql()
        cursor = (self.mongo[Auditoria.coleccion]
                  .find(Auditoria.filtro(evento), {"_id": 0})
                  .sort("fecha", -1).limit(limite))
        return list(cursor)

    def auditoria_por_evento(self):
        self._requiere_nosql()
        filas = self.mongo[Auditoria.coleccion].aggregate(Auditoria.por_evento())
        return [{"evento": f["_id"], "cantidad": f["cantidad"], "ultimo": f["ultimo"]} for f in filas]

    # ---------------------------------------------------------------
    # redis
    # ---------------------------------------------------------------
    def ranking_tiempo_real(self, top=5):
        # el ranking esta en redis, el titulo lo saco de oracle
        self._requiere_nosql()
        filas = []
        for lib_id, puntaje in self.redis.zrevrange(cache.RANKING_PRESTAMOS, 0, top - 1,
                                                    withscores=True):
            libro = self.obtener_libro(int(lib_id))
            filas.append({"lib_id": int(lib_id),
                          "titulo": libro["titulo"] if libro else "?",
                          "prestamos": int(puntaje)})
        return filas

    def actividad_de_hoy(self):
        self._requiere_nosql()
        return {k: int(v) for k, v in self.redis.hgetall(cache.actividad()).items()}

    def claves_redis(self):
        """Claves del proyecto con su tipo y el ttl que les queda."""
        self._requiere_nosql()
        claves = sorted({c for patron in cache.PREFIJOS for c in self.redis.scan_iter(patron)})
        return [{"clave": c, "tipo": self.redis.type(c), "ttl_segundos": self.redis.ttl(c)}
                for c in claves]

    # ---------------------------------------------------------------
    # preparar mongo y redis
    # ---------------------------------------------------------------
    def inicializar_nosql(self):
        """
        Borra las colecciones de mongo y crea los indices. En redis borra las
        claves del proyecto y vuelve a armar el ranking con los prestamos que
        hay en oracle.
        """
        self._requiere_nosql()
        for modelo in (Resenas, Auditoria):
            self.mongo.drop_collection(modelo.coleccion)
            for campos, opciones in modelo.indices:
                self.mongo[modelo.coleccion].create_index(campos, **opciones)

        for patron in cache.PREFIJOS:
            for clave in self.redis.scan_iter(patron):
                self.redis.delete(clave)
        for fila in self.libros_mas_prestados(top=1000):
            self.redis.zadd(cache.RANKING_PRESTAMOS, {fila["lib_id"]: fila["veces"]})
        return self.resumen_nosql()

    def resumen_nosql(self):
        self._requiere_nosql()
        return {
            "resenas (Mongo)": self.mongo[Resenas.coleccion].count_documents({}),
            "eventos de auditoria (Mongo)": self.mongo[Auditoria.coleccion].count_documents({}),
            "libros en el ranking (Redis)": self.redis.zcard(cache.RANKING_PRESTAMOS),
            "claves del proyecto (Redis)": len(self.claves_redis()),
        }


# prueba rapida: python dao.py
if __name__ == "__main__":
    with BibliotecaDAO() as dao:
        print("Resumen:", dao.resumen())
        for libro in dao.listar_libros():
            print(f"  [{libro['lib_id']}] {libro['titulo']} - {libro['autor']}")
