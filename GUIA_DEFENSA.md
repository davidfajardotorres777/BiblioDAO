# Guía para defender y modificar BiblioDAO

El profe va a pedir dos cosas: **explicarlo** y **modificarlo en el momento**
(agregar una variable, una función, una tabla). Esta guía tiene las dos.

---

## PARTE 1 — Cómo explicarlo (en 2 minutos)

1. **Qué es:** un sistema de préstamos de biblioteca. La parte importante es la
   **capa de acceso a datos** hecha con el patrón **DAO**.

2. **Qué es un DAO:** un objeto que **encapsula todo el acceso a la base**. El resto
   del programa llama `dao.prestar_libro(soc_id=1, lib_id=4)` y no sabe nada de SQL,
   de Oracle ni de conexiones. Si mañana cambio Oracle por PostgreSQL, solo cambio la
   URL en `config_vars.py`: el menú y el notebook no se tocan.
   *(Lo demuestro: las pruebas corren el mismo DAO sobre SQLite.)*

3. **Las 3 capas:**
   - `db_models/` → **qué consulta** hago. Cada clase representa una tabla y tiene
     métodos que **arman** la consulta (`select`, `insert`, `update`) pero **no la ejecutan**.
   - `dao.py` → **cómo la ejecuto**: abre la conexión, ejecuta, maneja transacciones,
     aplica las reglas de negocio y devuelve diccionarios.
   - `main.py` / notebook → la interfaz que usa el DAO.

4. **SQLAlchemy:** es la librería que traduce Python a SQL. `select(socios).where(socios.c.dni == dni)`
   se convierte en `SELECT ... FROM socios WHERE socios.dni = :dni`.
   Los valores van como **parámetros (bind variables)** → no hay **inyección SQL**
   y Oracle reutiliza el plan de ejecución.
   `oracledb` es el driver que habla con Oracle (modo *thin*: no necesita Instant Client).

5. **Transacciones:** `prestar_libro` hace 5 pasos (verificar socio, multas, máximo,
   ocupar ejemplar, insertar préstamo) dentro de `with self.engine.begin() as con:`.
   Si todo sale bien → **COMMIT**. Si se lanza un error en cualquier paso → **ROLLBACK**
   automático y no queda nada a medias. Eso es **atomicidad (la A de ACID)**.

6. **Concurrencia:** para ocupar una copia hago
   `UPDATE ejemplares SET estado='PRESTADO' WHERE eje_id=:id AND estado='DISPONIBLE'`.
   Si dos personas piden la misma copia al mismo tiempo, Oracle bloquea la fila: el
   segundo UPDATE encuentra el estado ya cambiado y modifica **0 filas** (`rowcount == 0`),
   así que el DAO prueba con la siguiente copia. Nunca se presta la misma copia dos veces.

7. **Integridad en la base (dbscripts.sql):** PK, FK, UNIQUE (dni, isbn, email,
   código de inventario), CHECK (tipo de socio, estado del ejemplar, monto > 0),
   índices sobre las FK (Oracle no los crea solos) y columnas IDENTITY para los IDs.

---

## PARTE 2 — Recorrido de una llamada (para dibujar en el pizarrón)

```
main.py                     dao.prestar_libro(soc_id=1, lib_id=4)
dao.py                      with engine.begin() as con:            ← BEGIN
  db_models/socios.py         Socios.por_id(1)        → SELECT ... FROM socios WHERE soc_id = :1
  db_models/multas.py         Multas.contar_pendientes(1) → SELECT COUNT(*) ...
  db_models/prestamos.py      Prestamos.contar_activos(1) → SELECT COUNT(*) ...
  db_models/ejemplares.py     Ejemplares.ocupar(6)    → UPDATE ejemplares SET estado='PRESTADO' ...
  db_models/prestamos.py      Prestamos.insertar(...) → INSERT INTO prestamos ... RETURNING pre_id
                            fin del with                            ← COMMIT
```
Para ver el SQL real: `BibliotecaDAO(echo=True)`.

---

## PARTE 3 — Cómo modificarlo (ejemplos probados)

### Regla de oro
| Si querés... | Tocás... |
|---|---|
| cambiar un número (días, máximo, multa) | solo `config_vars.py` |
| agregar una **columna** | `dbscripts.sql` + el modelo en `db_models/` (+ el DAO si se carga desde ahí) |
| agregar una **consulta/función** | un método en el modelo + un método en el DAO (+ opción en `main.py`) |
| agregar una **tabla** | `dbscripts.sql` + un archivo nuevo en `db_models/` + `__init__.py` + métodos en el DAO |

---

### Ejemplo A — Cambiar una regla: máximo 5 libros y multa de $800

`config_vars.py`:
```python
MAX_PRESTAMOS_ACTIVOS = 5
MULTA_POR_DIA = 800
```
Listo. El DAO lee esas constantes; no hay que tocar nada más.

---

### Ejemplo B — Agregar una variable (columna): `telefono` en socios

**1. En la base** (SQL Developer, conectado como biblio):
```sql
ALTER TABLE socios ADD telefono VARCHAR2(20);
```
y agregar la misma línea dentro del `CREATE TABLE socios` de `dbscripts.sql`
(para que quede si se recrea):
```sql
  telefono    VARCHAR2(20),
```

**2. En el modelo** `db_models/socios.py`, dentro de `Table("socios", ...)`:
```python
    Column("telefono", String(20)),
```

**3. En el DAO** `dao.py`, en `crear_socio` agregar el parámetro y pasarlo:
```python
    def crear_socio(self, *, dni, nombre, apellido, tipo, email=None, telefono=None):
        ...
        return self._insertar(Socios.insertar(
            dni=dni, nombre=nombre, apellido=apellido, email=email, telefono=telefono,
            tipo=tipo, fecha_alta=date.today(), activo=1))
```

**4. Probar:**
```python
dao.crear_socio(dni="44000111", nombre="Juan", apellido="Paz", tipo="ALUMNO", telefono="3825-123456")
dao.actualizar_socio(1, telefono="3825-999999")   # actualizar ya funciona sin tocar nada
```
`listar_socios()` ya devuelve la columna nueva porque hace `select(socios)` (todas las columnas).

---

### Ejemplo C — Agregar una función: libros que **nunca** se prestaron

**1. Modelo** — en `db_models/libros.py`, dentro de la clase `Libros`.
Los imports van *dentro* del método porque `prestamos.py` ya importa `libros.py`
(si los pongo arriba se produce un import circular):
```python
    @staticmethod
    def nunca_prestados():
        """Libros sin ningun prestamo: LEFT JOIN + IS NULL"""
        from db_models.ejemplares import ejemplares
        from db_models.prestamos import prestamos
        return (
            select(libros.c.lib_id, libros.c.titulo)
            .select_from(libros)
            .outerjoin(ejemplares, ejemplares.c.lib_id == libros.c.lib_id)
            .outerjoin(prestamos, prestamos.c.eje_id == ejemplares.c.eje_id)
            .group_by(libros.c.lib_id, libros.c.titulo)
            .having(func.count(prestamos.c.pre_id) == 0)
            .order_by(libros.c.titulo)
        )
```
SQL equivalente:
```sql
SELECT l.lib_id, l.titulo
  FROM libros l
  LEFT JOIN ejemplares e ON e.lib_id = l.lib_id
  LEFT JOIN prestamos  p ON p.eje_id = e.eje_id
 GROUP BY l.lib_id, l.titulo
HAVING COUNT(p.pre_id) = 0
 ORDER BY l.titulo;
```

**2. DAO** — en `dao.py`, sección REPORTES:
```python
    def libros_nunca_prestados(self):
        return self._todos(Libros.nunca_prestados())
```

**3. Menú** — en `main.py` agregar al texto `14. Libros nunca prestados` y:
```python
                elif opcion == "14":
                    mostrar(dao.libros_nunca_prestados(), ["lib_id", "titulo"])
```

---

### Ejemplo D — Otra función: socios con más préstamos (ranking)

Modelo (`db_models/prestamos.py`, clase `Prestamos`):
```python
    @staticmethod
    def ranking_socios(top=5):
        cantidad = func.count(prestamos.c.pre_id).label("cantidad")
        return (
            select(socios.c.soc_id,
                   (socios.c.apellido + ", " + socios.c.nombre).label("socio"),
                   cantidad)
            .select_from(prestamos)
            .join(socios, socios.c.soc_id == prestamos.c.soc_id)
            .group_by(socios.c.soc_id, socios.c.apellido, socios.c.nombre)
            .order_by(desc(cantidad))
            .limit(top)
        )
```
DAO:
```python
    def ranking_socios(self, top=5):
        return self._todos(Prestamos.ranking_socios(top))
```

---

### Ejemplo E — Agregar una tabla nueva: `reservas`

**1. SQL** (`dbscripts.sql`, y agregar `'RESERVAS'` a la lista del DROP):
```sql
CREATE TABLE reservas (
  res_id        NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY,
  lib_id        NUMBER NOT NULL,
  soc_id        NUMBER NOT NULL,
  fecha_reserva DATE   DEFAULT TRUNC(SYSDATE) NOT NULL,
  CONSTRAINT pk_reservas       PRIMARY KEY (res_id),
  CONSTRAINT fk_reservas_libro FOREIGN KEY (lib_id) REFERENCES libros (lib_id),
  CONSTRAINT fk_reservas_socio FOREIGN KEY (soc_id) REFERENCES socios (soc_id)
);
```

**2. Modelo** nuevo `db_models/reservas.py`:
```python
from sqlalchemy import Table, Column, Integer, Date, Identity, ForeignKey, select
from db_models.base import metadata, ModeloBase

reservas = Table(
    "reservas", metadata,
    Column("res_id", Integer, Identity(), primary_key=True),
    Column("lib_id", Integer, ForeignKey("libros.lib_id"), nullable=False),
    Column("soc_id", Integer, ForeignKey("socios.soc_id"), nullable=False),
    Column("fecha_reserva", Date, nullable=False),
)

class Reservas(ModeloBase):
    tabla = reservas
    pk = "res_id"

    @staticmethod
    def de_libro(lib_id):
        return select(reservas).where(reservas.c.lib_id == lib_id).order_by(reservas.c.fecha_reserva)
```
Gracias a `ModeloBase`, ya tiene gratis `todos()`, `por_id()`, `insertar()`, `actualizar()` y `eliminar()`.

**3.** En `db_models/__init__.py`: `from db_models.reservas import Reservas`

**4. DAO:**
```python
    def reservar(self, *, soc_id, lib_id):
        return self._insertar(Reservas.insertar(soc_id=soc_id, lib_id=lib_id,
                                                fecha_reserva=date.today()))
```

---

## PARTE 4 — Preguntas probables

**¿Por qué separar modelos y DAO?**
Responsabilidad única: el modelo sabe *qué* SQL armar, el DAO sabe *cuándo y cómo*
ejecutarlo (conexión, transacción, errores). Puedo cambiar una consulta sin tocar la
conexión, o cambiar de motor sin tocar las consultas.

**¿Qué es `metadata`?**
El catálogo en Python de todas las tablas. SQLAlchemy lo usa para conocer columnas
y FK. En las pruebas, `metadata.create_all()` crea las tablas en SQLite.

**¿Qué hace `engine`?**
Administra un *pool* de conexiones: las abre cuando hacen falta y las reutiliza.
`engine.connect()` = solo lectura (al cerrar hace ROLLBACK porque no hubo cambios);
`engine.begin()` = transacción con COMMIT automático.

**¿Por qué `RETURNING`?**
Para obtener el ID generado por la columna IDENTITY en el mismo INSERT, sin hacer otro SELECT.

**¿Por qué baja lógica de socios (`activo = 0`) y no DELETE?**
Porque tiene préstamos asociados (la FK lo impediría) y se pierde el historial.

**¿Qué pasa si devuelvo un libro dos veces?**
El DAO verifica `fecha_devolucion IS NOT NULL` y lanza `BibliotecaError`.

**¿Qué pasa si se duplica un DNI?**
La restricción UNIQUE de Oracle tira ORA-00001; el DAO captura `IntegrityError` y lo
convierte en un `BibliotecaError` con un mensaje claro.

**¿Por qué índices en las FK?**
Oracle crea índice automático solo para PK y UNIQUE. Los JOIN por FK y los DELETE
en la tabla padre son mucho más rápidos con índice.

**¿Por qué guardar `fecha_vencimiento` si se puede calcular?**
Porque la duración del préstamo puede cambiar (config) y los préstamos viejos deben
mantener el vencimiento con el que se hicieron.

**¿Qué diferencia hay con un ORM completo?**
Uso **SQLAlchemy Core** (tablas y consultas), no el ORM con clases mapeadas. Es más
cercano al SQL y se ve exactamente qué consulta se ejecuta, igual que en la guía de la cátedra.
