"""Strato 3 — turno PdC (LIV 3).

Ciclo di lavoro del macchinista. N giornate × M varianti × sequenza
di blocchi (CONDOTTA, VETTURA, REFEZ, ACCp, ACCa, CV, PK, S.COMP, ecc.).

Vedi `docs/SCHEMA-DATI-NATIVO.md` §7, `docs/NORMATIVA-PDC.md`,
`docs/LOGICA-COSTRUZIONE.md` §4.
"""

from datetime import date, datetime, time
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from colazione.db import Base


class TurnoPdc(Base):
    __tablename__ = "turno_pdc"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="RESTRICT")
    )
    codice: Mapped[str] = mapped_column(String(50))
    impianto: Mapped[str] = mapped_column(String(80))
    profilo: Mapped[str] = mapped_column(String(40), default="Condotta")
    ciclo_giorni: Mapped[int] = mapped_column(Integer, default=7)
    valido_da: Mapped[date] = mapped_column(Date)
    valido_a: Mapped[date | None] = mapped_column(Date)
    source_file: Mapped[str | None] = mapped_column(Text)
    generation_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    stato: Mapped[str] = mapped_column(String(20), default="bozza")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TurnoPdcGiornata(Base):
    __tablename__ = "turno_pdc_giornata"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    turno_pdc_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("turno_pdc.id", ondelete="CASCADE")
    )
    numero_giornata: Mapped[int] = mapped_column(Integer)
    variante_calendario: Mapped[str] = mapped_column(String(20), default="LMXGV")
    stazione_inizio: Mapped[str | None] = mapped_column(String(20), ForeignKey("stazione.codice"))
    stazione_fine: Mapped[str | None] = mapped_column(String(20), ForeignKey("stazione.codice"))
    inizio_prestazione: Mapped[time | None] = mapped_column(Time)
    fine_prestazione: Mapped[time | None] = mapped_column(Time)
    prestazione_min: Mapped[int] = mapped_column(Integer, default=0)
    condotta_min: Mapped[int] = mapped_column(Integer, default=0)
    refezione_min: Mapped[int] = mapped_column(Integer, default=0)
    km: Mapped[int] = mapped_column(Integer, default=0)
    is_notturno: Mapped[bool] = mapped_column(Boolean, default=False)
    is_riposo: Mapped[bool] = mapped_column(Boolean, default=False)
    is_disponibile: Mapped[bool] = mapped_column(Boolean, default=False)
    riposo_min: Mapped[int] = mapped_column(Integer, default=0)


class TurnoPdcBlocco(Base):
    __tablename__ = "turno_pdc_blocco"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    turno_pdc_giornata_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("turno_pdc_giornata.id", ondelete="CASCADE")
    )
    seq: Mapped[int] = mapped_column(Integer)
    tipo_evento: Mapped[str] = mapped_column(String(20))
    corsa_commerciale_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("corsa_commerciale.id", ondelete="RESTRICT")
    )
    corsa_materiale_vuoto_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("corsa_materiale_vuoto.id", ondelete="RESTRICT")
    )
    giro_blocco_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("giro_blocco.id", ondelete="SET NULL")
    )
    stazione_da_codice: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("stazione.codice")
    )
    stazione_a_codice: Mapped[str | None] = mapped_column(String(20), ForeignKey("stazione.codice"))
    ora_inizio: Mapped[time | None] = mapped_column(Time)
    ora_fine: Mapped[time | None] = mapped_column(Time)
    durata_min: Mapped[int | None] = mapped_column(Integer)
    is_accessori_maggiorati: Mapped[bool] = mapped_column(Boolean, default=False)
    cv_parent_blocco_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("turno_pdc_blocco.id", ondelete="SET NULL")
    )
    accessori_note: Mapped[str | None] = mapped_column(Text)
    fonte_orario: Mapped[str] = mapped_column(String(20), default="parsed")
