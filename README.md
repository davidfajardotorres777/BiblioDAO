# BiblioDAO

Trabajo final de Base de Datos II (UNdeC).
Alumno: Alesandro David Fajardo Torres

Sistema de prestamos para una biblioteca hecho con el patron DAO en Python.
Usa tres bases de datos:

- **Oracle XE**: socios, autores, libros, ejemplares, prestamos y multas.
- **MongoDB**: resenas de los libros y un registro (auditoria) de las operaciones.
- **Redis**: ranking de libros mas prestados, cache de la disponibilidad y contadores del dia.

Oracle es la base principal. Mongo y Redis se actualizan despues de que la
operacion se guarda en Oracle, asi que si alguno de los dos no anda el
prestamo se registra igual.

## Estructura

```
config_vars.py       conexiones y reglas (dias de prestamo, maximo, multa por dia)
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

La idea es que los modelos solo arman la consulta (el select, el documento
de mongo o el nombre de la clave de redis) y el DAO es el que la ejecuta.
main.py y el notebook no tocan las bases directamente, solo llaman metodos
del DAO como `dao.prestar_libro(soc_id=1, lib_id=4)`.

## Modelo de datos (Oracle)

```
AUTORES 1---N LIBROS 1---N EJEMPLARES 1---N PRESTAMOS N---1 SOCIOS
                                                |
                                                1---0..1 MULTAS
```

- `socios`: dni y email unicos, tipo ALUMNO / DOCENTE / EXTERNO.
- `libros`: isbn unico, FK al autor.
- `ejemplares`: cada copia fisica, con estado DISPONIBLE / PRESTADO / REPARACION / BAJA.
- `prestamos`: si `fecha_devolucion` es NULL el prestamo sigue activo.
- `multas`: una por prestamo como maximo.

## Reglas

- Un socio dado de baja no puede pedir libros.
- Si tiene multas sin pagar tampoco.
- Maximo 3 prestamos a la vez.
- El prestamo dura 14 dias y por cada dia de atraso se cobran $500.
- Prestar y devolver son transacciones: si algo falla se hace rollback.
- Solo puede resenar un libro quien lo pidio alguna vez, y una sola resena por libro.

## MongoDB y Redis

En Mongo hay dos colecciones:

- `resenas`: un documento por resena con puntaje, comentario y una lista de
  etiquetas. Tiene un indice unique por (lib_id, soc_id).
- `auditoria`: se guarda sola cada vez que se presta, devuelve, paga una multa,
  etc. Cada evento tiene campos distintos.

En Redis hay tres tipos de claves:

- `ranking:prestamos` (sorted set): se suma 1 con ZINCRBY en cada prestamo.
- `disponibilidad:libro:<id>` (hash): guarda cuantas copias hay en cada estado
  durante 60 segundos. Al prestar o devolver se borra para que no quede viejo.
- `actividad:<fecha>` (hash): cantidad de prestamos y devoluciones del dia.

Lo de Redis se puede volver a armar desde Oracle con `dao.inicializar_nosql()`.

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

Datos de conexion:

- SQL Developer: usuario `biblio`, clave `biblio123`, host `localhost`, puerto `1521`, servicio `XEPDB1`.
- MongoDB Compass: `mongodb://biblio:biblio123@localhost:27017/?authSource=admin`, base `biblioteca`.
- Consolas: `docker exec -it mongo-biblio mongosh -u biblio -p biblio123` y `docker exec -it redis-biblio redis-cli`.

## Pruebas

```bash
python -m tests.test_dao
```

No necesitan docker: usan sqlite en lugar de oracle, y mongomock y fakeredis
en lugar de mongo y redis. Hay una prueba que simula que redis se cae para
ver que el prestamo igual se guarda.

## Si no anda docker

```bash
python demo_sqlite.py
$env:BBDD_CONNECTION="sqlite:///biblio_demo.db"; $env:USAR_NOSQL="0"; python main.py
```

Con eso el mismo DAO funciona con sqlite y sin mongo ni redis.

## Errores comunes

- `DPY-6005` o connection refused: oracle todavia esta arrancando, esperar a que `docker ps` diga healthy.
- `ORA-12514`: el servicio tiene que ser `XEPDB1`.
- `ORA-00942`: faltan las tablas, correr `python crear_bd.py`.
- `ORA-00001`: dato repetido (dni, isbn o codigo de inventario).
- `ServerSelectionTimeoutError` o `ConnectionError` de redis: el contenedor de mongo o redis esta apagado.
- `[aviso NoSQL] ...`: mongo o redis no respondio pero la operacion quedo guardada en oracle.
