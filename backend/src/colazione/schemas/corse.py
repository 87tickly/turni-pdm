"""Schemas Pydantic — Strato 1 (corse PdE).

Schemi `Read` per serializzare corse commerciali, composizioni
stagionali, materiale vuoto e tracking import. Vedi `models/corse.py`.
"""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class CorsaImportRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_file: str
    source_hash: str | None = None
    n_corse: int
    n_corse_create: int
    n_corse_update: int
    azienda_id: int
    started_at: datetime
    completed_at: datetime | None = None
    note: str | None = None


class CorsaCommercialeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    azienda_id: int

    numero_treno: str
    rete: str | None = None
    numero_treno_rfi: str | None = None
    numero_treno_fn: str | None = None
    categoria: str | None = None
    codice_linea: str | None = None
    direttrice: str | None = None

    codice_origine: str
    codice_destinazione: str
    codice_inizio_cds: str | None = None
    codice_fine_cds: str | None = None

    ora_partenza: time
    ora_arrivo: time
    ora_inizio_cds: time | None = None
    ora_fine_cds: time | None = None
    min_tratta: int | None = None
    min_cds: int | None = None
    km_tratta: Decimal | None = None
    km_cds: Decimal | None = None

    valido_da: date
    valido_a: date
    codice_periodicita: str | None = None
    periodicita_breve: str | None = None
    is_treno_garantito_feriale: bool
    is_treno_garantito_festivo: bool
    fascia_oraria: str | None = None

    giorni_per_mese_json: dict[str, Any]
    valido_in_date_json: list[Any]

    totale_km: Decimal | None = None
    totale_minuti: int | None = None
    posti_km: Decimal | None = None
    velocita_commerciale: Decimal | None = None

    import_source: str
    import_run_id: int | None = None
    imported_at: datetime


class CorsaComposizioneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    corsa_commerciale_id: int
    stagione: str
    giorno_tipo: str
    categoria_posti: str | None = None
    is_doppia_composizione: bool
    tipologia_treno: str | None = None
    vincolo_dichiarato: str | None = None
    categoria_bici: str | None = None
    categoria_prm: str | None = None


class CorsaMaterialeVuotoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    azienda_id: int
    numero_treno_vuoto: str
    codice_origine: str
    codice_destinazione: str
    ora_partenza: time
    ora_arrivo: time
    min_tratta: int | None = None
    km_tratta: Decimal | None = None
    origine: str
    giro_materiale_id: int | None = None
    valido_in_date_json: list[Any]
    valido_da: date | None = None
    valido_a: date | None = None
    created_at: datetime
