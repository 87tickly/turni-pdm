"""Strato 2 — giro materiale (LIV 2).

Ciclo di rotazione del materiale fisico: N giornate × M varianti
calendariali per giornata × sequenza di blocchi (corse, materiali
vuoti, soste, manovre).

Sprint 7.7 MR 5 (migration 0018, decisione utente "B1"): aggregazione
A2 per chiave ``(materiale_tipo_codice, localita_manutenzione,
n_giornate)``. UN giro materiale = UN ciclo fisico per quel materiale,
in cui le sequenze di blocchi possono variare per giornata-tipo
(varianti calendariali). Il modello rispecchia il PDF Trenord
(esempio turno 1134: ETR204 FIO 8 giornate, giornata 9 ha 4 varianti
"LV 1:5", "F", "LV 6 escl. 21-28/3, 11/4", "Si eff. 21-28/3, 11/4").

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
    # Sprint 7.7 MR 4 (migration 0017): allargato a 40 char per
    # accogliere il suffisso ``-{materiale_tipo_codice}``
    # (formato ``G-{LOC_BREVE}-{SEQ}-{MAT}``).
    numero_turno: Mapped[str] = mapped_column(String(40))
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
    # Sprint 7.6 MR 3.2 (migration 0013): somma km_tratta delle corse
    # commerciali di questa giornata. Sprint 7.7 MR 5: con varianti
    # multiple per giornata, ``km_giornata`` rappresenta i km della
    # variante CANONICA (variant_index=0). Per i km totali per
    # giornata distinti per variante, sommare le corse della singola
    # variante.
    km_giornata: Mapped[float | None] = mapped_column(Numeric(8, 2))


class GiroVariante(Base):
    """Sprint 7.7 MR 5 (migration 0018) — re-introdotta.

    Una variante calendariale di una giornata-tipo. Più varianti per
    la stessa giornata significano "in periodi diversi il convoglio
    fa giri diversi perché in quei giorni quei treni non ci sono"
    (decisione utente B1). Le varianti hanno sequenze di blocchi
    distinte e ``dates_apply_json`` disgiunte (per costruzione del
    clustering A1 a monte).
    """

    __tablename__ = "giro_variante"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    giro_giornata_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("giro_giornata.id", ondelete="CASCADE")
    )
    variant_index: Mapped[int] = mapped_column(Integer, default=0)
    # Periodicità testuale del PdE per la prima corsa della variante
    # (es. ``"LV 1:5"``, ``"F"``, ``"Si eff. 21-28/3, 11/4"``).
    # Letterale dal PdE Trenord — niente parser DSL (memoria
    # ``feedback_pde_periodicita_verita.md``).
    validita_testo: Mapped[str | None] = mapped_column(Text)
    # Date concrete (ISO ``YYYY-MM-DD``) in cui la variante si
    # applica nel periodo del programma. Per costruzione disgiunto
    # dalle altre varianti della stessa giornata.
    dates_apply_json: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    # Date escluse (sospensioni). Oggi sempre vuoto, riservato per
    # gestione "soppresso il NN/MM" futura.
    dates_skip_json: Mapped[list[Any]] = mapped_column(JSONB, default=list)


class GiroBlocco(Base):
    __tablename__ = "giro_blocco"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Sprint 7.7 MR 5 (migration 0018): la FK torna a ``giro_variante``
    # (era stata redirected su ``giro_giornata`` in MR 0016, è ora
    # invertita).
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
