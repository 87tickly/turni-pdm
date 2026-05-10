"""Registro vetture cross-PdC §15 — Sprint 8.2 MR-PD-FIX-SEVERO 3b A1.

Implementa il vincolo NORMATIVA-PDC §15.1-§15.2: "ogni segmento di treno
si assegna a UN solo PdC, sempre". Per il caso VETTURA (treni commerciali
usati come deadhead per il rientro al deposito), il registro tiene
traccia delle vetture già "prenotate" da turni PdC esistenti, in modo
che il :func:`vettura_resolver.risolvi_rientro` possa escluderle dalle
candidate per i nuovi turni.

Chiave registro: tupla ``(numero_treno, operatore, data_operativa)``.
- ``operatore`` può essere ``None`` (es. dati legacy senza operatore noto):
  il match è strict (None matcha solo None).
- ``data_operativa`` è la data del **turno PdC** che usa la vettura
  (decisione NINO conservativa, vedi piano riga 220+ docs/piani/SPRINT-8.2-MR-PD-FIX-SEVERO-3b-piano.md).
- ``data_operativa = None`` nel registro funziona come **wild card match**
  (collide con qualunque data) — usato dal ``from_db`` MVP finché
  ``enumera_date_giornata`` non viene scritto (S4 SEVERO TODO).

NB: scope MVP = solo VETTURA. Le corse commerciali CONDOTTA sono già
unicizzate dal modello giro 1:1 PdC + da ``MR-PD7a`` §15 intra-turno
(entry 274). Cross-turno per CONDOTTA è scope MR-PD7+ globale.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.models.giri import GiroMateriale
from colazione.models.turni_pdc import TurnoPdc, TurnoPdcBlocco, TurnoPdcGiornata

logger = logging.getLogger(__name__)


@dataclass
class RegistroVettureAssegnate:
    """Registro stateful delle vetture rientro già prenotate.

    Stato pubblico minimo: una mappa ``(numero, operatore) →
    set[date | None]``. La data ``None`` significa "wild card" =
    collide con qualunque data operativa (usato per backfill di turni
    storici quando ``enumera_date_giornata`` non è ancora implementato).
    """

    _vetture: dict[tuple[str, str | None], set[date | None]] = field(
        default_factory=dict
    )
    """Storage interno: chiave (numero_treno, operatore) → set di date
    (None = wild card). Privato perché l'accesso passa via metodi che
    incapsulano la semantica wild-card."""

    def assegna(
        self,
        *,
        numero_treno: str,
        operatore: str | None,
        data_operativa: date | None,
    ) -> None:
        """Marca la vettura ``(numero, operatore)`` come assegnata
        nella ``data_operativa``. Idempotente.

        Args:
            numero_treno: Numero treno commerciale (es. ``"2425"``,
                ``"28335i"``). Stringa esattamente come in ``TrenoVettura.numero``.
            operatore: Operatore (es. ``"TN"``, ``"TILO"``). ``None`` per
                dati legacy o operatore non noto.
            data_operativa: Data del turno PdC che usa la vettura, in
                formato ``date``. ``None`` per wild card (= la vettura
                è registrata per qualsiasi data, usato dal ``from_db``
                MVP per turni storici).
        """
        chiave = (numero_treno, operatore)
        self._vetture.setdefault(chiave, set()).add(data_operativa)

    def is_assegnata(
        self,
        *,
        numero_treno: str,
        operatore: str | None,
        data_operativa: date,
    ) -> bool:
        """Verifica se ``(numero, operatore)`` è già assegnata nella
        ``data_operativa``. Match con wild card: se nel registro c'è
        ``data_operativa=None`` per la chiave, ritorna True (la vettura
        è bloccata per qualsiasi data).

        Args:
            numero_treno: Vedi :meth:`assegna`.
            operatore: Vedi :meth:`assegna`. Match strict (None matcha
                solo None).
            data_operativa: Data concreta da verificare (NON nullable
                qui: il chiamante resolver SA la data del turno corrente).

        Returns:
            ``True`` se la vettura è prenotata per quella data (anche
            via wild card), ``False`` altrimenti.
        """
        chiave = (numero_treno, operatore)
        date_assegnate = self._vetture.get(chiave)
        if date_assegnate is None:
            return False
        return data_operativa in date_assegnate or None in date_assegnate

    def numeri_da_escludere(
        self, *, data_operativa: date
    ) -> frozenset[tuple[str, str | None]]:
        """Restituisce l'insieme di chiavi ``(numero, operatore)`` che
        il resolver deve escludere dalle candidate vettura per la
        ``data_operativa``. Include anche le entry wild card (``None``).

        Usato dal ``vettura_resolver.risolvi_rientro`` per filtrare i
        candidati PRIMA dell'ordinamento (vs loop esterno con
        ``ora_min_partenza+1``, anti-pattern raccomandato da SEVERO S7).

        Args:
            data_operativa: Data concreta del turno corrente.

        Returns:
            Set frozen delle chiavi da escludere. Vuoto se nessuna
            vettura è prenotata per quella data.
        """
        out: set[tuple[str, str | None]] = set()
        for chiave, date_assegnate in self._vetture.items():
            if data_operativa in date_assegnate or None in date_assegnate:
                out.add(chiave)
        return frozenset(out)

    @property
    def n_assegnate(self) -> int:
        """Numero totale di entry (chiave, data) registrate. Utile per
        log/diagnostica."""
        return sum(len(s) for s in self._vetture.values())

    @classmethod
    async def from_db(
        cls,
        db: AsyncSession,
        *,
        programma_id: int,
    ) -> RegistroVettureAssegnate:
        """Factory che popola il registro dai turni PdC già esistenti
        in DB per il programma indicato.

        MVP wild card: legge i blocchi ``tipo_evento='VETTURA'`` con
        ``numero_treno_vettura IS NOT NULL`` (campo introdotto da
        migration 0046, MR-PD-FIX-SEVERO 3b A1). I blocchi storici
        senza il campo popolato vengono ignorati (campo nullable, OK).

        La ``data_operativa`` viene impostata a ``None`` (wild card)
        perché ``TurnoPdcGiornata`` non ha ancora ``data: date``: è
        identificato da numero giornata + variante calendariale, che
        materializza in N date concrete via helper
        ``enumera_date_giornata`` (TODO S4 SEVERO, scope MR-PD7+).

        Per MVP è una scelta **conservativa**: una vettura registrata
        wild-card collide con qualsiasi data operativa = il resolver
        la esclude sempre. Effetto pratico: nessun turno PdC futuro
        può usare una vettura già usata da un turno qualsiasi del
        programma. Sovra-strict ma sicuro (no doppioni).

        Quando ``enumera_date_giornata`` sarà disponibile, il
        ``from_db`` userà la data concreta invece di ``None``, allenando
        il match.

        **Sprint 8.3 S4** (post-SEVERO post-Sprint entry 285): la query
        ora **filtra effettivamente per programma_id** via JOIN
        multi-tabella. La catena è: ``turno_pdc_blocco → turno_pdc_giornata
        → turno_pdc → generation_metadata_json.giro_materiale_id →
        giro_materiale.programma_id``. ``giro_materiale_id`` è in
        ``generation_metadata_json`` JSONB (cast a Integer per il filtro
        IN sui giri del programma).

        Args:
            db: Sessione AsyncSession per la query.
            programma_id: ID del programma del quale caricare i turni.

        Returns:
            Registro popolato con SOLO le vetture dei turni del
            programma indicato (può essere vuoto se nessun turno
            esistente per quel programma).
        """
        registro = cls()

        # Subquery 1: ID dei giri del programma indicato.
        giri_ids_subq = (
            select(GiroMateriale.id)
            .where(GiroMateriale.programma_id == programma_id)
            .scalar_subquery()
        )

        # Subquery 2: ID dei turni PdC che riferiscono uno di quei giri
        # via generation_metadata_json.giro_materiale_id (JSONB cast).
        # NB: usa ``jsonb_extract_path_text`` invece di ``[key].astext``
        # perché quest'ultimo parametrizza il nome chiave come bind
        # variable (``->> %(param)s::TEXT``), causando ProgrammingError
        # Postgres su subquery. ``jsonb_extract_path_text`` accetta
        # literal stringa.
        turni_ids_subq = (
            select(TurnoPdc.id)
            .where(
                cast(
                    func.jsonb_extract_path_text(
                        TurnoPdc.generation_metadata_json, "giro_materiale_id"
                    ),
                    Integer,
                ).in_(giri_ids_subq)
            )
            .scalar_subquery()
        )

        # Subquery 3: ID delle giornate dei turni filtrati.
        giornate_ids_subq = (
            select(TurnoPdcGiornata.id)
            .where(TurnoPdcGiornata.turno_pdc_id.in_(turni_ids_subq))
            .scalar_subquery()
        )

        # Final: blocchi VETTURA dei turni del programma con campo non null.
        stmt = select(TurnoPdcBlocco.numero_treno_vettura).where(
            TurnoPdcBlocco.turno_pdc_giornata_id.in_(giornate_ids_subq),
            TurnoPdcBlocco.tipo_evento == "VETTURA",
            TurnoPdcBlocco.numero_treno_vettura.is_not(None),
        )
        result = await db.execute(stmt)
        rows = result.all()
        for row in rows:
            numero = row[0]
            if numero is None:  # defensive
                continue
            # Operatore non recuperato dal DB MVP: chiave wild su
            # operatore (None). Quando la migration aggiungerà
            # operatore_treno_vettura, questo sarà raffinato.
            registro.assegna(
                numero_treno=numero,
                operatore=None,
                data_operativa=None,  # wild card S4 TODO
            )
        logger.info(
            "RegistroVettureAssegnate.from_db: %d vetture caricate "
            "per programma_id=%d (scope wild-card data, S4 chiuso)",
            registro.n_assegnate,
            programma_id,
        )
        return registro


__all__ = ["RegistroVettureAssegnate"]
