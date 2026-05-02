"""Strato 1 — corse commerciali (LIV 1).

Sorgente unica autorevole importata dal Programma di Esercizio (PdE).
Contiene corse commerciali, varianti di composizione stagionali, corse
di materiale vuoto (posizionamento) e tracking delle import run.

Vedi `docs/SCHEMA-DATI-NATIVO.md` §4.
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


class CorsaImportRun(Base):
    __tablename__ = "corsa_import_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_file: Mapped[str] = mapped_column(Text)
    source_hash: Mapped[str | None] = mapped_column(String(64))
    n_corse: Mapped[int] = mapped_column(Integer, default=0)
    n_corse_create: Mapped[int] = mapped_column(Integer, default=0)
    n_corse_update: Mapped[int] = mapped_column(Integer, default=0)
    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="RESTRICT")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)


class CorsaCommerciale(Base):
    __tablename__ = "corsa_commerciale"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="RESTRICT")
    )

    # SHA-256 dei campi grezzi della riga PdE — identità naturale per
    # delta-sync (Sprint 3.7). Stabile fra re-import: se la riga del PdE
    # non cambia, il hash non cambia → la corsa resta in DB con stesso id.
    row_hash: Mapped[str] = mapped_column(String(64))

    numero_treno: Mapped[str] = mapped_column(String(20))
    rete: Mapped[str | None] = mapped_column(String(10))
    numero_treno_rfi: Mapped[str | None] = mapped_column(String(20))
    numero_treno_fn: Mapped[str | None] = mapped_column(String(20))
    categoria: Mapped[str | None] = mapped_column(String(20))
    codice_linea: Mapped[str | None] = mapped_column(String(20))
    direttrice: Mapped[str | None] = mapped_column(Text)

    codice_origine: Mapped[str] = mapped_column(String(20), ForeignKey("stazione.codice"))
    codice_destinazione: Mapped[str] = mapped_column(String(20), ForeignKey("stazione.codice"))
    codice_inizio_cds: Mapped[str | None] = mapped_column(String(20), ForeignKey("stazione.codice"))
    codice_fine_cds: Mapped[str | None] = mapped_column(String(20), ForeignKey("stazione.codice"))

    ora_partenza: Mapped[time] = mapped_column(Time)
    ora_arrivo: Mapped[time] = mapped_column(Time)
    ora_inizio_cds: Mapped[time | None] = mapped_column(Time)
    ora_fine_cds: Mapped[time | None] = mapped_column(Time)
    min_tratta: Mapped[int | None] = mapped_column(Integer)
    min_cds: Mapped[int | None] = mapped_column(Integer)
    km_tratta: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    km_cds: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))

    valido_da: Mapped[date] = mapped_column(Date)
    valido_a: Mapped[date] = mapped_column(Date)
    codice_periodicita: Mapped[str | None] = mapped_column(Text)
    periodicita_breve: Mapped[str | None] = mapped_column(Text)
    is_treno_garantito_feriale: Mapped[bool] = mapped_column(Boolean, default=False)
    is_treno_garantito_festivo: Mapped[bool] = mapped_column(Boolean, default=False)
    fascia_oraria: Mapped[str | None] = mapped_column(String(10))

    giorni_per_mese_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    valido_in_date_json: Mapped[list[Any]] = mapped_column(JSONB, default=list)

    totale_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    totale_minuti: Mapped[int | None] = mapped_column(Integer)
    posti_km: Mapped[Decimal | None] = mapped_column(Numeric(15, 3))
    velocita_commerciale: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))

    import_source: Mapped[str] = mapped_column(Text, default="pde")
    import_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("corsa_import_run.id", ondelete="SET NULL")
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CorsaComposizione(Base):
    __tablename__ = "corsa_composizione"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    corsa_commerciale_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("corsa_commerciale.id", ondelete="CASCADE")
    )
    stagione: Mapped[str] = mapped_column(String(20))
    giorno_tipo: Mapped[str] = mapped_column(String(20))
    categoria_posti: Mapped[str | None] = mapped_column(Text)
    is_doppia_composizione: Mapped[bool] = mapped_column(Boolean, default=False)
    tipologia_treno: Mapped[str | None] = mapped_column(Text)
    vincolo_dichiarato: Mapped[str | None] = mapped_column(Text)
    categoria_bici: Mapped[str | None] = mapped_column(String(10))
    categoria_prm: Mapped[str | None] = mapped_column(String(10))


class CorsaMaterialeVuoto(Base):
    __tablename__ = "corsa_materiale_vuoto"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="RESTRICT")
    )
    # Sprint 7.7 MR 4 (migration 0017): allargato a 40 char per coerenza
    # con ``giro_materiale.numero_turno`` (formato ``V-{numero_turno}-{NNN}``).
    numero_treno_vuoto: Mapped[str] = mapped_column(String(40))
    codice_origine: Mapped[str] = mapped_column(String(20), ForeignKey("stazione.codice"))
    codice_destinazione: Mapped[str] = mapped_column(String(20), ForeignKey("stazione.codice"))
    ora_partenza: Mapped[time] = mapped_column(Time)
    ora_arrivo: Mapped[time] = mapped_column(Time)
    min_tratta: Mapped[int | None] = mapped_column(Integer)
    km_tratta: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    origine: Mapped[str] = mapped_column(String(40))
    giro_materiale_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("giro_materiale.id", ondelete="SET NULL")
    )
    valido_in_date_json: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    valido_da: Mapped[date | None] = mapped_column(Date)
    valido_a: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
