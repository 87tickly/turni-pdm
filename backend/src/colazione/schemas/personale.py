"""Schemas Pydantic — Strato 4 (personale).

Schemi `Read` per persone, assegnazioni giornaliere e indisponibilità.
Vedi `models/personale.py`.
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class PersonaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    azienda_id: int
    codice_dipendente: str
    nome: str
    cognome: str
    profilo: str
    sede_residenza_id: int | None = None
    qualifiche_json: list[Any]
    is_matricola_attiva: bool
    data_assunzione: date | None = None
    user_id: int | None = None
    email: str | None = None
    created_at: datetime


class AssegnazioneGiornataRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    persona_id: int
    data: date
    turno_pdc_giornata_id: int | None = None
    stato: str
    sostituisce_persona_id: int | None = None
    note: str | None = None
    created_at: datetime
    updated_at: datetime


class IndisponibilitaPersonaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    persona_id: int
    tipo: str
    data_inizio: date
    data_fine: date
    is_approvato: bool
    approvato_da_user_id: int | None = None
    approvato_at: datetime | None = None
    note: str | None = None
    created_at: datetime
