# BiblioDAO — Sistema de Préstamos de la Biblioteca UNdeC

**Base de Datos II · Universidad Nacional de Chilecito**
Alumno: Alesandro David Fajardo Torres

Capa de acceso a datos (patrón **DAO**) en Python para una biblioteca:
socios, libros, ejemplares, préstamos y multas, sobre **Oracle XE** con **SQLAlchemy**.

---

## Arquitectura

```
main.py / demo_dao.ipynb      ← interfaz (menú de consola / notebook)
        │  llama métodos: dao.prestar_libro(...)
        ▼
dao.py  (BibliotecaDAO)       ← ÚNICA puerta a la BD: conexión, transacciones, reglas de negocio
        │  pide la consulta armada: Prestamos.vencidos(hoy)
        ▼
db_models/                    ← una clase por tabla: define la tabla y ARMA las consultas
        │
        ▼
Oracle XE (esquema BIBLIO)    ← tablas creadas con dbscripts.sql
```

## Modelo de datos

```
AUTORES 1───N LIBROS 1───N EJEMPLARES 1───N PRESTAMOS N───1 SOCIOS
                                                │
                                                1───0..1 MULTAS
```

| Tabla | Para qué | Claves / restricciones |
|---|---|---|
| `socios` | Personas que piden libros | PK `soc_id`, UNIQUE `dni` y `email`, CHECK `tipo` |
| `autores` | Autores | PK `aut_id` |
| `libros` | La obra (título, ISBN) | PK `lib_id`, UNIQUE `isbn`, FK → autores |
| `ejemplares` | Cada copia física | PK `eje_id`, FK → libros, CHECK `estado` |
| `prestamos` | Quién se llevó qué copia | FK → ejemplares y socios; `fecha_devolucion` NULL = activo |
| `multas` | Atrasos | FK UNIQUE → prestamos (una multa por préstamo) |

## Reglas de negocio (en `dao.py`)

* Un socio dado de baja **no** puede pedir libros.
* Con **multas sin pagar** no puede pedir libros.
* Máximo **3 préstamos activos** por socio (`MAX_PRESTAMOS_ACTIVOS`).
* El préstamo dura **14 días** (`DIAS_PRESTAMO`).
* Si devuelve tarde: multa de **$500 por día** (`MULTA_POR_DIA`).
* Prestar y devolver son **transacciones**: o se guarda todo, o nada (ROLLBACK).

---

## Cómo ejecutarlo

Requisitos: Docker Desktop, Python 3.12.

```bash
# 1. Levantar Oracle (la primera vez descarga la imagen, tarda unos minutos)
docker compose up -d
docker logs -f oracle-biblio          # esperar: DATABASE IS READY TO USE!  (Ctrl+C para salir)

# 2. Entorno de Python
python -m venv venv
venv\Scripts\activate                 # Windows   |   source venv/bin/activate  (Linux)
pip install -r requirements.txt

# 3. Probar conexión y crear tablas + datos
python probar_conexion.py
python crear_bd.py                    # o abrir dbscripts.sql en SQL Developer y F5

# 4. Usarlo
python main.py                        # menú de consola
jupyter notebook demo_dao.ipynb       # demo paso a paso
```

Conexión en SQL Developer: usuario `biblio`, contraseña `biblio123`, host `localhost`,
puerto `1521`, **Nombre del servicio** `XEPDB1`.

### Pruebas automáticas (no necesitan Oracle)

```bash
python -m tests.test_dao
```

### Plan B: si Oracle no arranca el día del final

```bash
python demo_sqlite.py                                         # crea biblio_demo.db con los mismos datos
$env:BBDD_CONNECTION="sqlite:///biblio_demo.db"; python main.py   # PowerShell
```
El DAO es exactamente el mismo; solo cambia la URL de conexión.

---

## Problemas comunes

| Error | Causa | Solución |
|---|---|---|
| `DPY-6005` / `connection refused` | Oracle todavía arrancando o contenedor apagado | `docker ps`, esperar `DATABASE IS READY TO USE!` |
| `ORA-12514` | Servicio equivocado | Usar `XEPDB1` (no `XE`) |
| `ORA-01017` | Usuario/contraseña | `biblio` / `biblio123` (ver `docker-compose.yml`) |
| `ORA-00942` | Tablas no creadas | `python crear_bd.py` |
| `ORA-00001` | Dato duplicado (DNI, ISBN, código) | Es una restricción UNIQUE: usar otro valor |
| Puerto 1521 ocupado | Otro Oracle corriendo | `docker stop` del otro contenedor |
| `ModuleNotFoundError` | No se activó el venv | Activar `venv` y `pip install -r requirements.txt` |

## Estructura

```
BiblioDAO/
├── config_vars.py        conexión + constantes de negocio
├── dao.py                clase BibliotecaDAO
├── db_models/
│   ├── base.py           metadata + ModeloBase (CRUD genérico)
│   ├── socios.py  autores.py  libros.py  ejemplares.py  prestamos.py  multas.py
├── dbscripts.sql         DDL + índices + datos de prueba (Oracle)
├── crear_bd.py           ejecuta dbscripts.sql desde Python
├── probar_conexion.py    verifica la conexión
├── main.py               menú de consola
├── demo_dao.ipynb        demo en notebook
├── demo_sqlite.py        plan B sin Oracle
├── tests/test_dao.py     pruebas automáticas
├── docker-compose.yml    Oracle XE 21c
└── GUIA_DEFENSA.md       cómo explicarlo y cómo modificarlo
```
