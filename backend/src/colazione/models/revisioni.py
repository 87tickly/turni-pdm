"""Strato 2bis — revisioni provvisorie del giro materiale.

Override temporanei al giro materiale base, con cascading sui turni
PdC nella stessa finestra.

Vedi `docs/SCHEMA-DATI-NATIVO.md` §6 e `docs/LOGICA-COSTRUZIONE.md` §5.
"""

from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from colazione.db import Base


class RevisioneProvvisoria(Base):
    __tablename__ = "revisione_provvisoria"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    giro_materiale_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("giro_materiale.id", ondelete="CASCADE")
    )
    codice_revisione: Mapped[str] = mapped_column(String(50))
    causa: Mapped[str] = mapped_column(String(40))
    comunicazione_esterna_rif: Mapped[str | None] = mapped_column(Text)
    descrizione_evento: Mapped[str] = mapped_column(Text)
    finestra_da: Mapped[date] = mapped_column(Date)
    finestra_a: Mapped[date] = mapped_column(Date)
    data_pubblicazione: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    source_file: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RevisioneProvvisoriaBlocco(Base):
    __tablename__ = "revisione_provvisoria_blocco"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    revisione_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("revisione_provvisoria.id", ondelete="CASCADE")
    )
    operazione: Mapped[str] = mapped_column(String(20))
    giro_blocco_originale_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("giro_blocco.id", ondelete="SET NULL")
    )
    seq: Mapped[int | None] = mapped_column(Integer)
    tipo_blocco: Mapped[str | None] = mapped_column(String(40))
    corsa_commerciale_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("corsa_commerciale.id")
    )
    corsa_materiale_vuoto_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("corsa_materiale_vuoto.id")
    )
    stazione_da_codice: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("stazione.codice")
    )
    stazione_a_codice: Mapped[str | None] = mapped_column(String(20), ForeignKey("stazione.codice"))
    ora_inizio: Mapped[time | None] = mapped_column(Time)
    ora_fine: Mapped[time | None] = mapped_column(Time)


class RevisioneProvvisoriaPdc(Base):
    __tablename__ = "revisione_provvisoria_pdc"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    revisione_giro_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("revisione_provvisoria.id", ondelete="CASCADE")
    )
    turno_pdc_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("turno_pdc.id", ondelete="CASCADE")
    )
    codice_revisione: Mapped[str] = mapped_column(String(50))
    finestra_da: Mapped[date] = mapped_column(Date)
    finestra_a: Mapped[date] = mapped_column(Date)
