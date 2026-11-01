# BiblioDAO

Trabajo final de Base de Datos II (UNdeC).
Alumno: Alesandro David Fajardo Torres

Sistema de prestamos para una biblioteca hecho con el patron DAO en Python.

## El problema

En la biblioteca de la facultad los prestamos se anotan a mano o en planillas.
No hay forma rapida de saber cuantas copias de un libro quedan, quien tiene un
libro vencido o si un alumno debe una multa antes de prestarle otro. Tampoco
queda registro de que opinan los lectores de cada libro ni de que libros se
piden mas.

BiblioDAO resuelve eso con una capa de acceso a datos que:

- controla los prestamos con reglas (multas, maximo de libros, copias disponibles)
  y transacciones, para que nunca quede un prestamo a medias;
- calcula las multas solas al devolver con atraso;
- guarda resenas de los libros con etiquetas;
- mantiene un ranking de los libros mas pedidos y una cache de la disponibilidad;
- registra cada operacion en una auditoria.

## Por que tres bases de datos

- **Oracle XE**: socios, autores, libros, ejemplares, prestamos y multas. Son datos
  muy relacionados entre si y un prestamo tiene que respetar varias reglas a la
  vez, asi que conviene una base relacional con transacciones y claves foraneas.
- **MongoDB**: resenas y auditoria. Cada resena tiene una lista de etiquetas de largo
  variable y cada evento de auditoria guarda datos distintos. En tablas habria que
  usar varias tablas o muchas columnas vacias.
- **Redis**: ranking de libros mas prestados, cache de la disponibilidad y contadores
  del dia. Son datos que se leen todo el tiempo y que conviene tener en memoria.

Oracle es la base principal. Mongo y Redis se actualizan despues de que la
operacion se guarda en Oracle, asi que si alguno de los dos no anda el prestamo
se registra igual. Lo de Redis se puede volver a armar desde Oracle con
`dao.inicializar_nosql()`.

## Estructura

```
config_vars.py       conexiones y reglas (dias de prestamo, maximo, multa por dia)
.env.example         ejemplo de configuracion (copiar como .env)
dao.py               clase BibliotecaDAO, todo el acceso a las bases pasa por aca
db_models/           arman las consultas
    socios, autores, libros, ejemplares, prestamos, multas   (tablas de oracle)
    resenas, auditoria                                        (colecciones de mongo)
    cache                                                     (claves de redis)
dbscripts.sql        tablas, indices y datos de prueba de oracle
crear_bd.py          carga los datos de prueba en las tres bases
probar_conexion.py   prueba la conexion a las tres bases
main.py              menu por consola
demo_dao.ipynb       notebook con la demo
demo_sqlite.py       para usarlo con sqlite si no anda docker
tests/test_dao.py    pruebas
docker-compose.yml   levanta oracle, mongo y redis
```

Los modelos solo arman la consulta (el select, el documento de mongo o el nombre
de la clave de redis) y el DAO es el que la ejecuta. main.py y el notebook no
tocan las bases directamente, solo llaman metodos del DAO.

## Como correrlo

Hace falta Docker Desktop y Python 3.12.

```bash
docker compose up -d
docker ps                      # esperar que los tres contenedores digan (healthy)

python -m venv venv
venv\Scripts\activate          # en linux: source venv/bin/activate
pip install -r requirements.txt

python probar_conexion.py
python crear_bd.py

python main.py
jupyter notebook demo_dao.ipynb
```

Si se quieren cambiar usuarios, claves o puertos, copiar `.env.example` como
`.env` y editarlo. Sin `.env` se usan los valores del `docker-compose.yml`.

Datos de conexion:

- SQL Developer: usuario `biblio`, clave `biblio123`, host `localhost`, puerto `1521`, servicio `XEPDB1`.
- MongoDB Compass: `mongodb://biblio:biblio123@localhost:27017/?authSource=admin`, base `biblioteca`.
- Consolas: `docker exec -it mongo-biblio mongosh -u biblio -p biblio123` y `docker exec -it redis-biblio redis-cli`.

## Uso del DAO

```python
from dao import BibliotecaDAO, BibliotecaError

dao = BibliotecaDAO()          # o: with BibliotecaDAO() as dao: ...

# --- catalogo ---
dao.listar_libros()                         # todos, con el nombre del autor
dao.listar_libros(categoria="Literatura")
dao.buscar_libros("bases")                  # por titulo, sin importar mayusculas
dao.disponibilidad(4)                       # {'DISPONIBLE': 2, 'PRESTADO': 1, 'REPARACION': 0, 'BAJA': 0}
dao.ultima_fuente                           # 'oracle' o 'redis', de donde salio el dato

aut = dao.crear_autor(nombre="Gabriel Garcia Marquez", nacionalidad="Colombia")
lib = dao.crear_libro(isbn="9789871138012", titulo="Cien anios de soledad", aut_id=aut, anio=1967)
eje = dao.agregar_ejemplar(lib_id=lib, codigo_inventario="INV-012")
dao.cambiar_estado_ejemplar(eje, "REPARACION")

# --- socios ---
soc = dao.crear_socio(dni="45000111", nombre="Juan", apellido="Paz", tipo="ALUMNO",
                      email="juan@mail.com")
dao.actualizar_socio(soc, email="juan.paz@undec.edu.ar")
dao.dar_de_baja_socio(soc)                  # baja logica (activo = 0)

# --- prestamos y multas ---
pre = dao.prestar_libro(soc_id=1, lib_id=2)
dao.devolver_libro(pre)                     # {'pre_id': 5, 'dias_atraso': 0, 'multa': 0}
dao.prestamos_activos()
dao.prestamos_vencidos()                    # con los dias de atraso
dao.multas_pendientes()
dao.pagar_multa(1)
dao.historial_socio(1)

# --- reportes ---
dao.libros_mas_prestados()
dao.resumen()

# --- resenas (mongo) ---
# (el socio tiene que haber pedido el libro antes, como arriba)
dao.agregar_resena(soc_id=1, lib_id=2, puntaje=5, comentario="Muy bueno",
                   etiquetas=["cuentos", "recomendado"])
dao.resenas_de_libro(2)
dao.buscar_resenas_por_etiqueta("cuentos")
dao.actualizar_resena(1, 2, puntaje=4)
dao.eliminar_resena(1, 2)
dao.mejores_libros()                        # promedio de puntaje por libro
dao.etiquetas_populares()

# --- auditoria (mongo) ---
dao.auditoria(limite=10)
dao.auditoria(evento="DEVOLUCION")
dao.auditoria_por_evento()

# --- redis ---
dao.ranking_tiempo_real()
dao.actividad_de_hoy()                      # {'prestamos': 3, 'devoluciones': 1}
dao.claves_redis()

dao.close()
```

Cuando algo no se puede hacer (socio con multa, libro sin copias, DNI repetido,
etc.) el DAO tira `BibliotecaError` con el motivo.

## Reglas

- Un socio dado de baja no puede pedir libros.
- Si tiene multas sin pagar tampoco.
- Maximo 3 prestamos a la vez.
- El prestamo dura 14 dias y por cada dia de atraso se cobran $500.
- Prestar y devolver son transacciones: si algo falla se hace rollback.
- El estado PRESTADO de una copia solo lo cambian prestar y devolver.
- No se puede devolver con una fecha anterior al prestamo.
- El DNI tiene que tener 7 u 8 numeros y no puede repetirse.
- Solo puede resenar un libro quien lo pidio alguna vez, y una sola resena por libro.

## Oracle: tablas e indices

```
AUTORES 1---N LIBROS 1---N EJEMPLARES 1---N PRESTAMOS N---1 SOCIOS
                                                |
                                                1---0..1 MULTAS
```

- `socios`: soc_id, dni (unique), nombre, apellido, email (unique), tipo
  (ALUMNO / DOCENTE / EXTERNO), fecha_alta, activo.
- `autores`: aut_id, nombre, nacionalidad.
- `libros`: lib_id, isbn (unique), titulo, anio, categoria, aut_id (FK).
- `ejemplares`: eje_id, lib_id (FK), codigo_inventario (unique), estado
  (DISPONIBLE / PRESTADO / REPARACION / BAJA).
- `prestamos`: pre_id, eje_id (FK), soc_id (FK), fecha_prestamo, fecha_vencimiento,
  fecha_devolucion (NULL mientras esta activo).
- `multas`: mul_id, pre_id (FK unique, una multa por prestamo), monto, pagada.

Ademas de las PK y unique hay indices en las FK (`ix_libros_autor`,
`ix_ejemplares_libro`, `ix_prestamos_socio`, `ix_prestamos_eje`), porque Oracle no
los crea solo y se usan en todos los JOIN.

## MongoDB: colecciones

`resenas`

| campo | tipo | ejemplo |
|---|---|---|
| lib_id, soc_id | int | 4, 1 |
| socio, titulo | string | "Herrera, Lucia", "Fundamentos de Sistemas de Bases de Datos" |
| puntaje | int (1 a 5) | 5 |
| comentario | string | "Muy claro para normalizacion y SQL." |
| etiquetas | lista de strings | ["bases-de-datos", "teoria"] |
| fecha | fecha | 2026-10-31 19:00 |

Indices: `uq_resena_libro_socio` unique (lib_id, soc_id) e `ix_resena_etiquetas`
sobre la lista de etiquetas.

`auditoria`: siempre tiene `evento` y `fecha`, el resto depende del evento.

- ALTA_SOCIO: soc_id, dni, tipo
- BAJA_SOCIO: soc_id
- PRESTAMO: pre_id, soc_id, lib_id, eje_id, vence
- DEVOLUCION: pre_id, soc_id, lib_id, dias_atraso, multa
- MULTA_PAGADA: mul_id
- CAMBIO_ESTADO_EJEMPLAR: eje_id, lib_id, estado

Indices: `ix_auditoria_fecha` y `ix_auditoria_evento_fecha`.

## Redis: claves

- `ranking:prestamos` (sorted set): libro -> cantidad de prestamos. Se suma con
  ZINCRBY en cada prestamo y se lee con ZREVRANGE.
- `disponibilidad:libro:<id>` (hash): copias en cada estado. Dura 60 segundos y se
  borra al prestar, devolver o cambiar el estado de una copia.
- `actividad:<fecha>` (hash): prestamos y devoluciones del dia, con HINCRBY. Dura una semana.

## Pruebas

```bash
python -m tests.test_dao
```

No necesitan docker: usan sqlite en lugar de oracle, y mongomock y fakeredis
en lugar de mongo y redis. Prueban las reglas de negocio, las validaciones,
las resenas, la auditoria, la cache y que el prestamo se guarde aunque redis
este caido.

## Si no anda docker

```bash
python demo_sqlite.py
$env:BBDD_CONNECTION="sqlite:///biblio_demo.db"; $env:USAR_NOSQL="0"; python main.py
```

Con eso el mismo DAO funciona con sqlite y sin mongo ni redis.

## Errores comunes

- `No se pudo conectar a Oracle` / `DPY-6005`: docker apagado o oracle todavia arrancando, esperar a que `docker ps` diga healthy.
- `ORA-12514`: el servicio tiene que ser `XEPDB1`.
- `ORA-00942`: faltan las tablas, correr `python crear_bd.py`.
- `ORA-00001`: dato repetido (dni, isbn o codigo de inventario).
- `No responde la base de datos` en el menu: algun contenedor esta apagado.
- `[aviso NoSQL] ...`: mongo o redis no respondio pero la operacion quedo guardada en oracle.
