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


class PersonaWithDepositoRead(BaseModel):
    """Persona arricchita con i dati del deposito di residenza (join)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    codice_dipendente: str
    nome: str
    cognome: str
    profilo: str
    is_matricola_attiva: bool
    data_assunzione: date | None = None
    depot_codice: str | None = None
    depot_display_name: str | None = None
    qualifiche: list[str] = []
    # Indisponibilità in corso oggi (tipo: ferie/malattia/ROL/...): None se in servizio.
    indisponibilita_oggi: str | None = None


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


class IndisponibilitaWithPersonaRead(BaseModel):
    """Indisponibilità arricchita con anagrafica persona (per liste ferie/malattie)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    persona_id: int
    persona_nome: str
    persona_cognome: str
    persona_codice_dipendente: str
    depot_codice: str | None = None
    depot_display_name: str | None = None
    tipo: str
    data_inizio: date
    data_fine: date
    giorni_totali: int
    is_approvato: bool
    note: str | None = None


class GestionePersonaleKpiRead(BaseModel):
    """KPI riepilogativi per dashboard Gestione Personale (cross-azienda).

    Calcolati a partire da:
    - ``persona.is_matricola_attiva = TRUE`` (totale attivi)
    - ``indisponibilita_persona`` con ``data_inizio <= oggi <= data_fine``
      (in corso) e ``is_approvato = TRUE``
    - In servizio = totale attivi − indisponibili oggi
    - Copertura % = in servizio / totale attivi (se > 0)
    """

    model_config = ConfigDict(from_attributes=True)

    persone_attive: int
    in_servizio_oggi: int
    in_ferie: int
    in_malattia: int
    in_rol: int
    in_altra_assenza: int  # sciopero/formazione/congedo
    copertura_pct: float


class GestionePersonaleKpiPerDepositoRead(BaseModel):
    """KPI per singolo deposito PdC (drilldown dashboard)."""

    model_config = ConfigDict(from_attributes=True)

    depot_codice: str
    depot_display_name: str
    persone_attive: int
    in_servizio_oggi: int
    indisponibili_oggi: int
    copertura_pct: float
