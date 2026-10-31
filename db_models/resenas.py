"""
Coleccion RESENAS (MongoDB).

Cada resena es un documento, por ejemplo:
    {"lib_id": 4, "soc_id": 1, "socio": "Herrera, Lucia",
     "titulo": "Fundamentos de Sistemas de Bases de Datos",
     "puntaje": 5, "comentario": "...",
     "etiquetas": ["bases-de-datos", "teoria"], "fecha": ...}

Las etiquetas son una lista de largo variable, por eso va en mongo y no en
una tabla. Igual que los otros modelos, aca solo se arman los documentos,
filtros y pipelines; los ejecuta el DAO.
"""
from datetime import datetime

PUNTAJE_MIN, PUNTAJE_MAX = 1, 5
CAMPOS_EDITABLES = {"puntaje", "comentario", "etiquetas"}


def _limpiar(etiquetas):
    return [e.strip().lower() for e in etiquetas if e.strip()]


class Resenas:
    coleccion = "resenas"

    # el unique evita que un socio resene dos veces el mismo libro
    indices = [
        ([("lib_id", 1), ("soc_id", 1)], {"unique": True, "name": "uq_resena_libro_socio"}),
        ([("etiquetas", 1)], {"name": "ix_resena_etiquetas"}),
    ]

    @staticmethod
    def documento(*, lib_id, soc_id, socio, titulo, puntaje, comentario, etiquetas):
        # socio y titulo se copian de oracle para no tener que consultarlo al mostrar
        return {
            "lib_id": lib_id,
            "soc_id": soc_id,
            "socio": socio,
            "titulo": titulo,
            "puntaje": puntaje,
            "comentario": comentario,
            "etiquetas": _limpiar(etiquetas),
            "fecha": datetime.now(),
        }

    @staticmethod
    def de_libro(lib_id):
        return {"lib_id": lib_id}

    @staticmethod
    def de_socio_y_libro(soc_id, lib_id):
        return {"soc_id": soc_id, "lib_id": lib_id}

    @staticmethod
    def con_etiqueta(etiqueta):
        # mongo busca el valor dentro de la lista
        return {"etiquetas": etiqueta.strip().lower()}

    @staticmethod
    def cambios(**campos):
        cambios = {k: v for k, v in campos.items() if k in CAMPOS_EDITABLES}
        if "etiquetas" in cambios:
            cambios["etiquetas"] = _limpiar(cambios["etiquetas"])
        cambios["fecha"] = datetime.now()
        return {"$set": cambios}

    @staticmethod
    def mejores_libros(top=5, minimo_resenas=1):
        # promedio de puntaje por libro, parecido a un GROUP BY ... HAVING
        return [
            {"$group": {"_id": "$lib_id",
                        "titulo": {"$first": "$titulo"},
                        "promedio": {"$avg": "$puntaje"},
                        "resenas": {"$sum": 1}}},
            {"$match": {"resenas": {"$gte": minimo_resenas}}},
            {"$sort": {"promedio": -1, "resenas": -1}},
            {"$limit": top},
        ]

    @staticmethod
    def etiquetas_populares(top=10):
        # $unwind separa la lista: queda un documento por etiqueta y despues se cuentan
        return [
            {"$unwind": "$etiquetas"},
            {"$group": {"_id": "$etiquetas", "cantidad": {"$sum": 1}}},
            {"$sort": {"cantidad": -1, "_id": 1}},
            {"$limit": top},
        ]
