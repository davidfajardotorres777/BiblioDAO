"""
Coleccion AUDITORIA (MongoDB): un documento por cada operacion.

Cada tipo de evento guarda datos distintos, por ejemplo:
    {"evento": "PRESTAMO", "fecha": ..., "pre_id": 5, "soc_id": 6, "lib_id": 1, "vence": "2026-11-14"}
    {"evento": "DEVOLUCION", "fecha": ..., "pre_id": 2, "dias_atraso": 6, "multa": 3000}
"""
from datetime import datetime

EVENTOS = ("ALTA_SOCIO", "BAJA_SOCIO", "PRESTAMO", "DEVOLUCION",
           "MULTA_PAGADA", "CAMBIO_ESTADO_EJEMPLAR")


class Auditoria:
    coleccion = "auditoria"

    indices = [
        ([("fecha", -1)], {"name": "ix_auditoria_fecha"}),
        ([("evento", 1), ("fecha", -1)], {"name": "ix_auditoria_evento_fecha"}),
    ]

    @staticmethod
    def documento(evento, **datos):
        return {"evento": evento, "fecha": datetime.now(), **datos}

    @staticmethod
    def filtro(evento=None):
        return {"evento": evento} if evento else {}

    @staticmethod
    def por_evento():
        return [
            {"$group": {"_id": "$evento", "cantidad": {"$sum": 1},
                        "ultimo": {"$max": "$fecha"}}},
            {"$sort": {"cantidad": -1}},
        ]
