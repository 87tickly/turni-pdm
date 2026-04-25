"""Schemas Pydantic — Strato 3 (turno PdC).

Schemi `Read` per turni PdC, giornate (con varianti calendario) e
blocchi (CONDOTTA, VETTURA, REFEZ, CV, ecc.). Vedi `models/turni_pdc.py`.
"""

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict


class TurnoPdcRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    azienda_id: int
    codice: str
    impianto: str
    profilo: str
    ciclo_giorni: int
    valido_da: date
    valido_a: date | None = None
    source_file: str | None = None
    generation_metadata_json: dict[str, Any]
    stato: str
    created_at: datetime
    updated_at: datetime


class TurnoPdcGiornataRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    turno_pdc_id: int
    numero_giornata: int
    variante_calendario: str
    stazione_inizio: str | None = None
    stazione_fine: str | None = None
    inizio_prestazione: time | None = None
    fine_prestazione: time | None = None
    prestazione_min: int
    condotta_min: int
    refezione_min: int
    km: int
    is_notturno: bool
    is_riposo: bool
    is_disponibile: bool
    riposo_min: int


class TurnoPdcBloccoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    turno_pdc_giornata_id: int
    seq: int
    tipo_evento: str
    corsa_commerciale_id: int | None = None
    corsa_materiale_vuoto_id: int | None = None
    giro_blocco_id: int | None = None
    stazione_da_codice: str | None = None
    stazione_a_codice: str | None = None
    ora_inizio: time | None = None
    ora_fine: time | None = None
    durata_min: int | None = None
    is_accessori_maggiorati: bool
    cv_parent_blocco_id: int | None = None
    accessori_note: str | None = None
    fonte_orario: str
