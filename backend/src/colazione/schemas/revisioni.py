"""Schemas Pydantic — Strato 2bis (revisioni provvisorie).

Schemi `Read` per revisioni provvisorie del giro materiale e cascading
sui turni PdC. Vedi `models/revisioni.py`.
"""

from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict


class RevisioneProvvisoriaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    giro_materiale_id: int
    codice_revisione: str
    causa: str
    comunicazione_esterna_rif: str | None = None
    descrizione_evento: str
    finestra_da: date
    finestra_a: date
    data_pubblicazione: date
    source_file: str | None = None
    created_at: datetime


class RevisioneProvvisoriaBloccoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    revisione_id: int
    operazione: str
    giro_blocco_originale_id: int | None = None
    seq: int | None = None
    tipo_blocco: str | None = None
    corsa_commerciale_id: int | None = None
    corsa_materiale_vuoto_id: int | None = None
    stazione_da_codice: str | None = None
    stazione_a_codice: str | None = None
    ora_inizio: time | None = None
    ora_fine: time | None = None


class RevisioneProvvisoriaPdcRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    revisione_giro_id: int
    turno_pdc_id: int
    codice_revisione: str
    finestra_da: date
    finestra_a: date
