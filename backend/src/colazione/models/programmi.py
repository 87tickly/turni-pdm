"""Strato 1bis — programma materiale (input umano del pianificatore).

Definito in `docs/PROGRAMMA-MATERIALE.md` v0.2 (Sprint 4.0). Il
programma materiale è il registro autorevole delle scelte di
programmazione del pianificatore: per ogni gruppo di corse PdE
(filtrate per linea/direttrice/categoria/orario/giorno_tipo/...),
quale rotabile usare e in quante quantità.

Multi-tenant: ogni `azienda` può avere più programmi (per periodo,
linea, ecc.). Solo i programmi `attivo` sono usati dall'algoritmo
A (PdE → Giro Materiale).

Sprint 7.3: il campo `stagione` è stato rimosso. Il filtro temporale
delle corse è data-driven via `valido_in_date_json` di ogni corsa
(verità del PdE) intersecato con `[valido_da, valido_a]` del programma.
Le 3 stagioni (`invernale/estiva/agosto`) restano solo a livello di
`corsa_composizione.stagione` (composizione-tipo del materiale).
"""

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

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
from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.orm import Mapped, mapped_column, relationship

from colazione.db import Base

if TYPE_CHECKING:
    from colazione.models.auth import AppUser


class ProgrammaMateriale(Base):
    """Intestazione del programma materiale per una azienda + finestra.

    Container di N `ProgrammaRegolaAssegnazione`. Lo stato `bozza` →
    editing, `attivo` → usato dall'algoritmo, `archiviato` → solo storico.
    """

    __tablename__ = "programma_materiale"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="RESTRICT")
    )

    nome: Mapped[str] = mapped_column(Text)
    valido_da: Mapped[date] = mapped_column(Date)
    valido_a: Mapped[date] = mapped_column(Date)
    stato: Mapped[str] = mapped_column(String(20), default="bozza")

    # Sprint 8.0 MR 0 (entry 164, migration 0032): pipeline state machine
    # per la concatenazione tra ruoli. Validazione applicativa via enum
    # ``StatoPipelinePdc`` in ``colazione.domain.pipeline``; lato DB
    # protetto da CHECK constraint ``programma_materiale_stato_pipeline_pdc_check``.
    stato_pipeline_pdc: Mapped[str] = mapped_column(
        String(40),
        default="PDE_IN_LAVORAZIONE",
        server_default="PDE_IN_LAVORAZIONE",
    )
    # Ramo manutenzione, parallelo e indipendente dal ramo PdC. Si attiva
    # quando ``stato_pipeline_pdc >= MATERIALE_CONFERMATO`` ma non blocca
    # le transizioni del ramo principale.
    stato_manutenzione: Mapped[str] = mapped_column(
        String(40), default="IN_ATTESA", server_default="IN_ATTESA"
    )

    # Parametri globali
    km_max_giornaliero: Mapped[int | None] = mapped_column(Integer)
    # Cap km cumulati sul ciclo intero (NON giornaliero). Quando raggiunto,
    # il giro chiude con rientro programmato. Sprint 5.1 (migration 0007).
    # Configurato dal pianificatore per ogni programma; tipici 5000-10000.
    km_max_ciclo: Mapped[int | None] = mapped_column(Integer)
    n_giornate_default: Mapped[int] = mapped_column(Integer, default=1)
    # Sprint 7.8 (migration 0019): range lunghezza giri generati dal
    # builder. `n_giornate_min` è SOFT (il builder scende sotto solo
    # per giri di "chiusura" delle corse residue a fine pool).
    # `n_giornate_max` è HARD (nessun giro supera questo numero).
    # Decisione utente 2026-05-03: default min=4, max=12.
    n_giornate_min: Mapped[int] = mapped_column(Integer, default=4, server_default="4")
    n_giornate_max: Mapped[int] = mapped_column(Integer, default=12, server_default="12")
    fascia_oraria_tolerance_min: Mapped[int] = mapped_column(Integer, default=30)

    # Strict mode granulare (vedi PROGRAMMA-MATERIALE.md §2.7)
    strict_options_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Sprint 5.6 (migration 0008): codici stazione PdE che il pianificatore
    # ammette come SOSTA NOTTURNA del materiale di questo programma, oltre
    # alla whitelist sede e ai depot PdC. La lista finale del builder è
    # whitelist sede ∪ depot PdC ∪ stazioni_sosta_extra. Default `[]`.
    stazioni_sosta_extra_json: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )

    # Tracking
    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    created_by: Mapped["AppUser | None"] = relationship(foreign_keys=[created_by_user_id])
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def created_by_username(self) -> str | None:
        """Username del creatore se la relazione è eager-loaded.

        Restituisce ``None`` se la relazione non è stata caricata
        (per evitare lazy-load implicito in contesto async). Le query
        che vogliono questo campo devono usare `joinedload(...)`.
        Entry 88 (TN-UPDATE).
        """
        try:
            return self.created_by.username if self.created_by is not None else None
        except MissingGreenlet:
            return None


class ProgrammaRegolaAssegnazione(Base):
    """Singola regola di assegnazione: filtri AND → (tipo, n_pezzi).

    Una regola matcha una corsa se TUTTI i filtri in `filtri_json`
    sono soddisfatti. Vedi `risolvi_corsa()` in `domain/builder_giro/`
    per l'algoritmo (Sprint 4.2).

    Schema `filtri_json`:
        [
          {"campo": "codice_linea", "op": "eq", "valore": "S5"},
          {"campo": "fascia_oraria", "op": "between", "valore": ["04:00", "15:59"]},
          {"campo": "giorno_tipo", "op": "in", "valore": ["feriale"]}
        ]

    Validazione applicativa via Pydantic in `schemas/programmi.py`.
    """

    __tablename__ = "programma_regola_assegnazione"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    programma_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("programma_materiale.id", ondelete="CASCADE")
    )

    filtri_json: Mapped[list[Any]] = mapped_column(JSONB, default=list)

    # Composizione del rotabile: lista
    # `[{materiale_tipo_codice, n_pezzi}, ...]` (Sprint 5.1, migration
    # 0007). Sostituisce a regime i campi legacy `materiale_tipo_codice`
    # + `numero_pezzi`. Lista di 1 elemento per regola single-material;
    # 2+ elementi per composizione mista (es. ETR526+ETR425). Validata
    # da `ComposizioneItem` in schemas/programmi.py.
    composizione_json: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    # Override manuale: se True, bypass del check
    # `materiale_accoppiamento_ammesso` per composizioni custom decise
    # dal pianificatore (Sprint 5.1).
    is_composizione_manuale: Mapped[bool] = mapped_column(Boolean, default=False)

    # Campi LEGACY (deprecati ma non rimossi). Resi nullable in 0007.
    # Letti ancora da `risolvi_corsa()` fino a Sprint 5.5; sulle nuove
    # righe popolati dal primo elemento di `composizione_json` (handler
    # API) per retrocompat.
    materiale_tipo_codice: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("materiale_tipo.codice", ondelete="RESTRICT")
    )
    numero_pezzi: Mapped[int | None] = mapped_column(Integer)

    priorita: Mapped[int] = mapped_column(Integer, default=60)
    # Sprint 7.7 MR 1 (migration 0014): cap km del ciclo specifico per
    # questa regola/materiale. Il builder usa
    # `regola.km_max_ciclo OR programma.km_max_ciclo OR DEFAULT_*` come
    # cap effettivo del giro generato da questa regola. Ogni materiale
    # ha autonomie diverse (ETR526 ~4500, E464 ~6000, ATR803 ~ecc).
    km_max_ciclo: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BuilderRun(Base):
    """Esito persistito di una run del builder (Sprint 7.9 MR 11C, entry 116).

    Ogni invocazione di ``genera_giri`` produce una riga in questa
    tabella che conserva stats + warnings, così il pianificatore può:
    - Vedere perché il run ha prodotto 0 giri (warnings espliciti tipo
      "sede non coerente con la regola").
    - Confrontare run successivi (regole modificate, sede cambiata).
    - Esporre la copertura PdE (corse_processate / corse_residue).

    Decisione utente 2026-05-04: warning del builder oggi sono persi
    dopo la response. La persistenza permette di mostrare dashboard
    "Ultimo run" + storico run senza re-eseguire.
    """

    __tablename__ = "builder_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    programma_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("programma_materiale.id", ondelete="CASCADE"),
        nullable=False,
    )
    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="CASCADE"), nullable=False
    )
    localita_codice: Mapped[str] = mapped_column(String(64), nullable=False)
    eseguito_da_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    eseguito_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    n_giri_creati: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    n_giri_chiusi: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    n_giri_non_chiusi: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    n_corse_processate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    n_corse_residue: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    n_eventi_composizione: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    n_incompatibilita_materiale: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    warnings_json: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    force: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
