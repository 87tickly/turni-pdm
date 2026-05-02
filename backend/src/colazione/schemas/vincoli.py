"""Pydantic schemas for vincoli inviolabili API responses."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CorsaProblematica(BaseModel):
    numero_treno: str
    origine: str
    destinazione: str


class VincoloViolato(BaseModel):
    """Una violazione di un vincolo HARD su una regola."""

    vincolo_id: str
    vincolo_nome: str
    vincolo_tipo: str = Field(
        description="tecnico_alimentazione | contrattuale_omologazione | operativo_turistico"
    )
    materiale_tipo_codice: str
    descrizione: str
    corse_problematiche: list[CorsaProblematica] = Field(
        default_factory=list,
        description="Esempi (max 5) di corse del programma che violerebbero il vincolo",
    )


class VincoliViolatiResponse(BaseModel):
    """Body 400 quando una regola viola uno o più vincoli inviolabili."""

    detail: str = "La regola viola uno o più vincoli inviolabili a livello tipo materiale."
    violazioni: list[VincoloViolato]
