"""Strato 0 — anagrafica.

Entità di base condivise da tutti gli strati: aziende, stazioni,
materiali, località manutenzione, depositi PdC, e tabelle associative.

Vedi `docs/SCHEMA-DATI-NATIVO.md` §3 e migrazione 0001 per i dettagli.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from colazione.db import Base


class Azienda(Base):
    __tablename__ = "azienda"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codice: Mapped[str] = mapped_column(String(50), unique=True)
    nome: Mapped[str] = mapped_column(Text)
    normativa_pdc_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_attiva: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Stazione(Base):
    __tablename__ = "stazione"

    codice: Mapped[str] = mapped_column(String(20), primary_key=True)
    nome: Mapped[str] = mapped_column(Text)
    nomi_alternativi_json: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    rete: Mapped[str | None] = mapped_column(String(10))
    is_sede_deposito: Mapped[bool] = mapped_column(Boolean, default=False)
    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MaterialeTipo(Base):
    __tablename__ = "materiale_tipo"

    codice: Mapped[str] = mapped_column(String(50), primary_key=True)
    nome_commerciale: Mapped[str | None] = mapped_column(Text)
    famiglia: Mapped[str | None] = mapped_column(Text)
    componenti_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    velocita_max_kmh: Mapped[int | None] = mapped_column(Integer)
    posti_per_pezzo: Mapped[int | None] = mapped_column(Integer)
    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LocalitaManutenzione(Base):
    __tablename__ = "localita_manutenzione"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codice: Mapped[str] = mapped_column(String(80), unique=True)
    nome_canonico: Mapped[str] = mapped_column(Text)
    nomi_alternativi_json: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    stazione_collegata_codice: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("stazione.codice", ondelete="SET NULL")
    )
    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="RESTRICT")
    )
    is_pool_esterno: Mapped[bool] = mapped_column(Boolean, default=False)
    azienda_proprietaria_esterna: Mapped[str | None] = mapped_column(String(100))
    is_attiva: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LocalitaManutenzioneDotazione(Base):
    __tablename__ = "localita_manutenzione_dotazione"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    localita_manutenzione_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("localita_manutenzione.id", ondelete="CASCADE")
    )
    materiale_tipo_codice: Mapped[str] = mapped_column(
        String(50), ForeignKey("materiale_tipo.codice", ondelete="RESTRICT")
    )
    quantita: Mapped[int] = mapped_column(Integer)
    famiglia_rotabile: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Depot(Base):
    __tablename__ = "depot"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codice: Mapped[str] = mapped_column(String(80), unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="RESTRICT")
    )
    stazione_principale_codice: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("stazione.codice", ondelete="SET NULL")
    )
    tipi_personale_ammessi: Mapped[str] = mapped_column(String(20), default="PdC")
    is_attivo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DepotLineaAbilitata(Base):
    __tablename__ = "depot_linea_abilitata"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    depot_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("depot.id", ondelete="CASCADE"))
    stazione_a_codice: Mapped[str] = mapped_column(String(20), ForeignKey("stazione.codice"))
    stazione_b_codice: Mapped[str] = mapped_column(String(20), ForeignKey("stazione.codice"))


class DepotMaterialeAbilitato(Base):
    __tablename__ = "depot_materiale_abilitato"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    depot_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("depot.id", ondelete="CASCADE"))
    materiale_tipo_codice: Mapped[str] = mapped_column(
        String(50), ForeignKey("materiale_tipo.codice", ondelete="RESTRICT")
    )
