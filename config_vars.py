"""
Configuracion del proyecto.
Los datos de conexion se pueden cambiar con variables de entorno
(o editando los valores por defecto de aca abajo).
"""
import os

from sqlalchemy.engine import URL

# ------------------------- Conexion a Oracle -------------------------
DB_USER = os.getenv("DB_USER", "biblio")
DB_PASSWORD = os.getenv("DB_PASSWORD", "biblio123")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "1521"))
DB_SERVICE = os.getenv("DB_SERVICE", "XEPDB1")   # la PDB de Oracle XE

# Queda: oracle+oracledb://biblio:***@localhost:1521/?service_name=XEPDB1
# Se arma con URL.create para que una contrasena con @ o / no rompa la URL.
BBDD_CONNECTION = os.getenv("BBDD_CONNECTION") or URL.create(
    "oracle+oracledb",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    query={"service_name": DB_SERVICE},
)

# ------------------------- Reglas de negocio -------------------------
DIAS_PRESTAMO = 14          # dias que dura un prestamo
MAX_PRESTAMOS_ACTIVOS = 3   # cuantos libros puede tener un socio a la vez
MULTA_POR_DIA = 500         # pesos por cada dia de atraso
