"""Strato 0 — anagrafica.

Entità di base condivise da tutti gli strati: aziende, stazioni,
materiali, località manutenzione, depositi PdC, e tabelle associative.

Vedi `docs/SCHEMA-DATI-NATIVO.md` §3 e migrazione 0001 per i dettagli.
"""

from datetime import date, datetime
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
    # Sede manutentiva di default per il rotabile (Sprint 5.1, migration 0007).
    # Nullable: configurato dal pianificatore via UI/seed. Usato come fallback
    # quando una regola non specifica la sede.
    localita_manutenzione_default_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("localita_manutenzione.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LocalitaManutenzione(Base):
    __tablename__ = "localita_manutenzione"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codice: Mapped[str] = mapped_column(String(80), unique=True)
    # Codice breve (max 8 char, ^[A-Z]{2,8}$) usato per generare il
    # `numero_turno` dei giri secondo convenzione `G-{LOC_BREVE}-{NNN}`.
    # Aggiunto in migration 0006 (Sprint 4.4.5b).
    codice_breve: Mapped[str] = mapped_column(String(8))
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


class LocalitaStazioneVicina(Base):
    """Whitelist M:N stazioni-vicine-sede (Sprint 5.1, migration 0007).

    Per ogni sede manutentiva, l'insieme di stazioni in cui sono ammessi
    i vuoti tecnici di posizionamento. Vedi
    `docs/SPRINT-5-RIPENSAMENTO.md` §3 e §5.3 per la motivazione e la
    logica di consumo nel builder.

    Una stazione può appartenere a più sedi (es. Saronno per NOV+CAM).
    """

    __tablename__ = "localita_stazione_vicina"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    localita_manutenzione_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("localita_manutenzione.id", ondelete="CASCADE")
    )
    stazione_codice: Mapped[str] = mapped_column(
        String(20), ForeignKey("stazione.codice", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FestivitaUfficiale(Base):
    """Calendario ufficiale festività (Sprint 7.7 MR 2, migration 0015).

    Una riga per ogni giorno NON-feriale che NON è pura conseguenza
    del weekday (sabato/domenica si calcolano dal `data.weekday()`).
    Riguarda quindi solo:

    - Festività nazionali italiane (10 fisse + Pasqua + Pasquetta)
    - Festività locali per azienda/regione (Sant'Ambrogio per Trenord)
    - Eventuali ricorrenze speciali per programma (oggi non usate)

    `azienda_id` NULL = festività universale (nazionale).
    `azienda_id` valorizzato = festività specifica per quell'azienda
    (es. patrono locale).

    Il builder usa questa tabella + `domain/calendario.tipo_giorno()`
    per classificare ogni data come feriale/sabato/domenica/festivo,
    propedeutico al refactor "varianti → giri separati" (Sprint 7.7.3).
    """

    __tablename__ = "festivita_ufficiale"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    azienda_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="CASCADE")
    )
    data: Mapped[date] = mapped_column(Date, index=True)
    nome: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(String(20), default="nazionale")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MaterialeAccoppiamentoAmmesso(Base):
    """Coppie ammesse di rotabili in doppia composizione
    (Sprint 5.1, migration 0007).

    Normalizzata lessicograficamente (`materiale_a_codice <=
    materiale_b_codice`) per garantire unicità simmetrica: una sola
    riga per coppia, indipendentemente dall'ordine di inserimento.

    Esempi: ETR421+ETR421, ETR526+ETR526, ETR526+ETR425. La lista cresce
    nel tempo; per ora questi 3 sono il seed Sprint 5.2.

    Override manuale: la regola `programma_regola_assegnazione` può
    avere `is_composizione_manuale=True` per bypassare il check su
    questa tabella (override pianificatore per composizioni custom).
    """

    __tablename__ = "materiale_accoppiamento_ammesso"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    materiale_a_codice: Mapped[str] = mapped_column(
        String(50), ForeignKey("materiale_tipo.codice", ondelete="RESTRICT")
    )
    materiale_b_codice: Mapped[str] = mapped_column(
        String(50), ForeignKey("materiale_tipo.codice", ondelete="RESTRICT")
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
