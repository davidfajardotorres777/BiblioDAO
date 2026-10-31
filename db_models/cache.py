"""
Nombres de las claves de Redis.

  ranking:prestamos            sorted set, libro -> cantidad de prestamos
  disponibilidad:libro:<id>    hash con las copias por estado, vence a los 60 seg
  actividad:<fecha>            hash con los prestamos y devoluciones del dia

Todo esto se puede volver a armar desde oracle (dao.inicializar_nosql()).
"""
from datetime import date

PREFIJOS = ("ranking:*", "disponibilidad:*", "actividad:*")

RANKING_PRESTAMOS = "ranking:prestamos"
ACTIVIDAD_TTL_SEGUNDOS = 7 * 24 * 3600   # una semana


def disponibilidad(lib_id):
    return f"disponibilidad:libro:{lib_id}"


def actividad(dia=None):
    return f"actividad:{(dia or date.today()).isoformat()}"
