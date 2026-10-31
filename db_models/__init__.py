"""
Modelos: una clase por tabla de oracle o coleccion de mongo, y en cache.py
las claves de redis.
"""
from db_models.base import metadata, ModeloBase
from db_models.socios import Socios, TIPOS_SOCIO
from db_models.autores import Autores
from db_models.libros import Libros
from db_models.ejemplares import Ejemplares, ESTADOS_EJEMPLAR
from db_models.prestamos import Prestamos
from db_models.multas import Multas
from db_models.resenas import Resenas, PUNTAJE_MIN, PUNTAJE_MAX
from db_models.auditoria import Auditoria
from db_models import cache

__all__ = ["metadata", "ModeloBase", "Socios", "Autores", "Libros", "Ejemplares",
           "Prestamos", "Multas", "TIPOS_SOCIO", "ESTADOS_EJEMPLAR",
           "Resenas", "PUNTAJE_MIN", "PUNTAJE_MAX", "Auditoria", "cache"]
