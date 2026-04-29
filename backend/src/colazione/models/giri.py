"""Strato 2 — giro materiale (LIV 2).

Costruzione del ciclo di rotazione del materiale fisico: N giornate
× M varianti calendario × sequenza di blocchi (corse, materiale
vuoto, soste, manovre).

Vedi `docs/SCHEMA-DATI-NATIVO.md` §5 e `docs/LOGICA-COSTRUZIONE.md`.
"""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from colazione.db import Base


class GiroMateriale(Base):
    __tablename__ = "giro_materiale"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="RESTRICT")
    )
    # Migration 0010: il programma_id è ora colonna esplicita (prima
    # era solo dentro generation_metadata_json). UNIQUE su
    # (azienda_id, programma_id, numero_turno) — due programmi diversi
    # possono avere ognuno il proprio G-FIO-001.
    programma_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("programma_materiale.id", ondelete="CASCADE")
    )
    numero_turno: Mapped[str] = mapped_column(String(20))
    validita_codice: Mapped[str | None] = mapped_column(String(10))
    tipo_materiale: Mapped[str] = mapped_column(Text)
    descrizione_materiale: Mapped[str | None] = mapped_column(Text)
    materiale_tipo_codice: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("materiale_tipo.codice")
    )
    numero_giornate: Mapped[int] = mapped_column(Integer)
    km_media_giornaliera: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    km_media_annua: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    posti_1cl: Mapped[int] = mapped_column(Integer, default=0)
    posti_2cl: Mapped[int] = mapped_column(Integer, default=0)
    localita_manutenzione_partenza_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("localita_manutenzione.id", ondelete="RESTRICT")
    )
    localita_manutenzione_arrivo_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("localita_manutenzione.id", ondelete="RESTRICT")
    )
    stato: Mapped[str] = mapped_column(String(20), default="bozza")
    generation_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VersioneBaseGiro(Base):
    __tablename__ = "versione_base_giro"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    giro_materiale_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("giro_materiale.id", ondelete="CASCADE"),
        unique=True,
    )
    data_deposito: Mapped[date | None] = mapped_column(Date)
    source_file: Mapped[str | None] = mapped_column(Text)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GiroFinestraValidita(Base):
    __tablename__ = "giro_finestra_validita"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    versione_base_giro_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("versione_base_giro.id", ondelete="CASCADE")
    )
    valido_da: Mapped[date] = mapped_column(Date)
    valido_a: Mapped[date] = mapped_column(Date)
    seq: Mapped[int] = mapped_column(Integer, default=1)


class GiroGiornata(Base):
    __tablename__ = "giro_giornata"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    giro_materiale_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("giro_materiale.id", ondelete="CASCADE")
    )
    numero_giornata: Mapped[int] = mapped_column(Integer)


class GiroVariante(Base):
    __tablename__ = "giro_variante"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    giro_giornata_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("giro_giornata.id", ondelete="CASCADE")
    )
    variant_index: Mapped[int] = mapped_column(Integer, default=0)
    validita_testo: Mapped[str] = mapped_column(Text, default="GG")
    validita_dates_apply_json: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    validita_dates_skip_json: Mapped[list[Any]] = mapped_column(JSONB, default=list)


class GiroBlocco(Base):
    __tablename__ = "giro_blocco"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    giro_variante_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("giro_variante.id", ondelete="CASCADE")
    )
    seq: Mapped[int] = mapped_column(Integer)
    tipo_blocco: Mapped[str] = mapped_column(String(40))
    corsa_commerciale_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("corsa_commerciale.id", ondelete="RESTRICT")
    )
    corsa_materiale_vuoto_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("corsa_materiale_vuoto.id", ondelete="RESTRICT")
    )
    stazione_da_codice: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("stazione.codice")
    )
    stazione_a_codice: Mapped[str | None] = mapped_column(String(20), ForeignKey("stazione.codice"))
    ora_inizio: Mapped[time | None] = mapped_column(Time)
    ora_fine: Mapped[time | None] = mapped_column(Time)
    descrizione: Mapped[str | None] = mapped_column(Text)
    # Sprint 4.1: per blocchi 'aggancio'/'sgancio' proposti dal builder,
    # `is_validato_utente=False` finché il pianificatore non conferma in
    # editor giro. `metadata_json` contiene es. {pezzi_delta: 3,
    # note_builder: "...", stazione_proposta_originale: "S01066"}.
    is_validato_utente: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
