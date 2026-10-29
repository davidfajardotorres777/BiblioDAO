"""
Paquete de modelos: una clase por tabla.
Importar desde aca:  from db_models import Socios, Libros, ...
"""
from db_models.base import metadata, ModeloBase
from db_models.socios import Socios, TIPOS_SOCIO
from db_models.autores import Autores
from db_models.libros import Libros
from db_models.ejemplares import Ejemplares, ESTADOS_EJEMPLAR
from db_models.prestamos import Prestamos
from db_models.multas import Multas

__all__ = ["metadata", "ModeloBase", "Socios", "Autores", "Libros", "Ejemplares",
           "Prestamos", "Multas", "TIPOS_SOCIO", "ESTADOS_EJEMPLAR"]
