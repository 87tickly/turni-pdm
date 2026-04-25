"""Schemas Pydantic — Strato 0 (anagrafica).

Schemi `Read` per serializzare entità anagrafica verso JSON. Costruiti
da modelli ORM tramite `from_attributes=True`. Vedi `models/anagrafica.py`.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AziendaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codice: str
    nome: str
    normativa_pdc_json: dict[str, Any]
    is_attiva: bool
    created_at: datetime


class StazioneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codice: str
    nome: str
    nomi_alternativi_json: list[Any]
    rete: str | None = None
    is_sede_deposito: bool
    azienda_id: int
    created_at: datetime


class MaterialeTipoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codice: str
    nome_commerciale: str | None = None
    famiglia: str | None = None
    componenti_json: dict[str, Any]
    velocita_max_kmh: int | None = None
    posti_per_pezzo: int | None = None
    azienda_id: int
    created_at: datetime


class LocalitaManutenzioneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codice: str
    nome_canonico: str
    nomi_alternativi_json: list[Any]
    stazione_collegata_codice: str | None = None
    azienda_id: int
    is_pool_esterno: bool
    azienda_proprietaria_esterna: str | None = None
    is_attiva: bool
    created_at: datetime


class LocalitaManutenzioneDotazioneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    localita_manutenzione_id: int
    materiale_tipo_codice: str
    quantita: int
    famiglia_rotabile: str | None = None
    note: str | None = None
    updated_at: datetime


class DepotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codice: str
    display_name: str
    azienda_id: int
    stazione_principale_codice: str | None = None
    tipi_personale_ammessi: str
    is_attivo: bool
    created_at: datetime


class DepotLineaAbilitataRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    depot_id: int
    stazione_a_codice: str
    stazione_b_codice: str


class DepotMaterialeAbilitatoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    depot_id: int
    materiale_tipo_codice: str
