"""Strato 4 — anagrafica personale (LIV 4).

Persone (PdC, CT, Manovra, Coord), assegnazioni giornaliere ai turni
PdC, indisponibilità (ferie, malattia, congedi, ROL, formazione).

Vedi `docs/SCHEMA-DATI-NATIVO.md` §8.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from colazione.db import Base


class Persona(Base):
    __tablename__ = "persona"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="RESTRICT")
    )
    codice_dipendente: Mapped[str] = mapped_column(String(40))
    nome: Mapped[str] = mapped_column(Text)
    cognome: Mapped[str] = mapped_column(Text)
    profilo: Mapped[str] = mapped_column(String(20), default="PdC")
    sede_residenza_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("depot.id", ondelete="SET NULL")
    )
    qualifiche_json: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    is_matricola_attiva: Mapped[bool] = mapped_column(Boolean, default=True)
    data_assunzione: Mapped[date | None] = mapped_column(Date)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="SET NULL")
    )
    email: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssegnazioneGiornata(Base):
    __tablename__ = "assegnazione_giornata"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    persona_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("persona.id", ondelete="RESTRICT")
    )
    data: Mapped[date] = mapped_column(Date)
    turno_pdc_giornata_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("turno_pdc_giornata.id", ondelete="SET NULL")
    )
    stato: Mapped[str] = mapped_column(String(20), default="pianificato")
    sostituisce_persona_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("persona.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IndisponibilitaPersona(Base):
    __tablename__ = "indisponibilita_persona"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    persona_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("persona.id", ondelete="CASCADE")
    )
    tipo: Mapped[str] = mapped_column(String(20))
    data_inizio: Mapped[date] = mapped_column(Date)
    data_fine: Mapped[date] = mapped_column(Date)
    is_approvato: Mapped[bool] = mapped_column(Boolean, default=False)
    approvato_da_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="SET NULL")
    )
    approvato_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
