"""Schemas Pydantic — Strato 2 (giro materiale).

Schemi `Read` per giri materiale, versioni, finestre validità,
giornate, varianti e blocchi. Vedi `models/giri.py`.
"""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class GiroMaterialeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    azienda_id: int
    numero_turno: str
    validita_codice: str | None = None
    tipo_materiale: str
    descrizione_materiale: str | None = None
    materiale_tipo_codice: str | None = None
    numero_giornate: int
    km_media_giornaliera: Decimal | None = None
    km_media_annua: Decimal | None = None
    posti_1cl: int
    posti_2cl: int
    localita_manutenzione_partenza_id: int
    localita_manutenzione_arrivo_id: int
    stato: str
    generation_metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class VersioneBaseGiroRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    giro_materiale_id: int
    data_deposito: date | None = None
    source_file: str | None = None
    imported_at: datetime


class GiroFinestraValiditaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    versione_base_giro_id: int
    valido_da: date
    valido_a: date
    seq: int


class GiroGiornataRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    giro_materiale_id: int
    numero_giornata: int


class GiroVarianteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    giro_giornata_id: int
    variant_index: int
    validita_testo: str
    validita_dates_apply_json: list[Any]
    validita_dates_skip_json: list[Any]


class GiroBloccoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    giro_variante_id: int
    seq: int
    tipo_blocco: str
    corsa_commerciale_id: int | None = None
    corsa_materiale_vuoto_id: int | None = None
    stazione_da_codice: str | None = None
    stazione_a_codice: str | None = None
    ora_inizio: time | None = None
    ora_fine: time | None = None
    descrizione: str | None = None
