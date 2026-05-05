"""Simulazione read-only del builder PdC — Sprint 7.9 MR η.1.

Stima il numero di dormite FR e le violazioni cap che risulterebbero
per una coppia (giro, deposito) **senza persistere** alcun TurnoPdc.

Usato dall'endpoint ``POST /api/giri/{id}/suggerisci-depositi`` per
proporre il top-N depositi che minimizzano i pernotti fuori sede.

Read-only: nessun DELETE, nessun INSERT, nessun commit. Riusa le
funzioni pure ``_aggiungi_dormite_fr`` e ``_calcola_violazioni_cap_fr``
del builder, e la pipeline di costruzione drafts via ``split_cv``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.domain.builder_pdc.builder import (
    DepositoPdcNonTrovatoError,
    GiroNonTrovatoError,
    GiroVuotoError,
    _aggiungi_dormite_fr,
    _calcola_violazioni_cap_fr,
    _GiornataPdcDraft,
)
from colazione.domain.builder_pdc.split_cv import (
    lista_stazioni_cv_ammesse,
    split_e_build_giornata,
)
from colazione.models.anagrafica import Depot, LocalitaManutenzione
from colazione.models.giri import (
    GiroBlocco,
    GiroGiornata,
    GiroMateriale,
    GiroVariante,
)


@dataclass
class SimulazioneFRResult:
    """Esito di una simulazione builder PdC su una coppia (giro, deposito).

    Tutti i numeri sono calcolati in memoria, nessun TurnoPdc viene
    creato. ``stazione_sede_usata`` riflette la stazione effettivamente
    utilizzata per identificare i FR (deposito.stazione_principale_codice
    se valorizzata, altrimenti fallback alla stazione del materiale).
    """

    n_dormite_fr: int
    fr_cap_violazioni: list[str]
    prestazione_totale_min: int
    condotta_totale_min: int
    n_giornate: int
    stazione_sede_usata: str | None
    stazione_sede_fallback: bool
    """True se ``deposito.stazione_principale_codice`` era NULL e
    abbiamo dovuto usare la sede del materiale come fallback. Quando
    questo è True, il calcolo FR è meno significativo perché la
    geografia "deposito vs giro" non è stata applicata davvero."""
    avvertimenti: list[str] = field(default_factory=list)


async def simula_turno_pdc_fr(
    *,
    session: AsyncSession,
    azienda_id: int,
    giro_id: int,
    deposito_pdc_id: int | None,
) -> SimulazioneFRResult:
    """Stima FR + cap violazioni per (giro, deposito) senza persistere.

    Riusa la stessa pipeline di ``genera_turno_pdc`` (caricamento giro,
    blocchi varianti canoniche, ``split_e_build_giornata``,
    ``_aggiungi_dormite_fr``, ``_calcola_violazioni_cap_fr``) ma si
    ferma prima di qualsiasi DELETE/INSERT su ``turno_pdc``.

    Raises:
        GiroNonTrovatoError, GiroVuotoError, DepositoPdcNonTrovatoError.
    """
    giro = (
        await session.execute(
            select(GiroMateriale).where(
                GiroMateriale.id == giro_id,
                GiroMateriale.azienda_id == azienda_id,
            )
        )
    ).scalar_one_or_none()
    if giro is None:
        raise GiroNonTrovatoError(
            f"Giro {giro_id} non trovato per azienda {azienda_id}"
        )

    depot_target: Depot | None = None
    if deposito_pdc_id is not None:
        depot_target = (
            await session.execute(
                select(Depot).where(
                    Depot.id == deposito_pdc_id,
                    Depot.azienda_id == azienda_id,
                    Depot.is_attivo,
                )
            )
        ).scalar_one_or_none()
        if depot_target is None:
            raise DepositoPdcNonTrovatoError(
                f"Deposito PdC {deposito_pdc_id} non trovato o non attivo "
                f"per azienda {azienda_id}"
            )

    giornate_giro = list(
        (
            await session.execute(
                select(GiroGiornata)
                .where(GiroGiornata.giro_materiale_id == giro_id)
                .order_by(GiroGiornata.numero_giornata)
            )
        ).scalars()
    )
    if not giornate_giro:
        raise GiroVuotoError(f"Giro {giro_id} non ha giornate")

    giornata_ids = [gg.id for gg in giornate_giro]

    canonica_per_giornata: dict[int, GiroVariante] = {}
    for v in (
        await session.execute(
            select(GiroVariante)
            .where(GiroVariante.giro_giornata_id.in_(giornata_ids))
            .order_by(GiroVariante.giro_giornata_id, GiroVariante.variant_index)
        )
    ).scalars():
        canonica_per_giornata.setdefault(v.giro_giornata_id, v)

    canonica_ids = [v.id for v in canonica_per_giornata.values()]
    blocchi_per_giornata: dict[int, list[GiroBlocco]] = {}
    if canonica_ids:
        var_to_gg = {v.id: v.giro_giornata_id for v in canonica_per_giornata.values()}
        for b in (
            await session.execute(
                select(GiroBlocco)
                .where(GiroBlocco.giro_variante_id.in_(canonica_ids))
                .order_by(GiroBlocco.giro_variante_id, GiroBlocco.seq)
            )
        ).scalars():
            gg_id = var_to_gg[b.giro_variante_id]
            blocchi_per_giornata.setdefault(gg_id, []).append(b)

    stazione_sede: str | None = None
    stazione_sede_fallback = False
    avvertimenti: list[str] = []
    if depot_target is not None and depot_target.stazione_principale_codice is not None:
        stazione_sede = depot_target.stazione_principale_codice
    else:
        if depot_target is not None:
            stazione_sede_fallback = True
            avvertimenti.append(
                f"Deposito {depot_target.codice} non ha "
                f"stazione_principale_codice popolata; uso sede materiale."
            )
        if giro.localita_manutenzione_partenza_id is not None:
            loc = (
                await session.execute(
                    select(LocalitaManutenzione).where(
                        LocalitaManutenzione.id
                        == giro.localita_manutenzione_partenza_id
                    )
                )
            ).scalar_one_or_none()
            if loc is not None and loc.stazione_collegata_codice is not None:
                stazione_sede = loc.stazione_collegata_codice

    stazioni_cv = await lista_stazioni_cv_ammesse(session, azienda_id)

    drafts_per_giornata: list[list[_GiornataPdcDraft]] = []
    for gg in giornate_giro:
        blocchi = blocchi_per_giornata.get(gg.id, [])
        canonica = canonica_per_giornata.get(gg.id)
        validita = (canonica.validita_testo if canonica is not None else None) or "GG"
        rami = split_e_build_giornata(
            numero_giornata=gg.numero_giornata,
            variante_calendario=validita,
            blocchi_giro=blocchi,
            stazioni_cv=stazioni_cv,
        )
        if rami:
            drafts_per_giornata.append(rami)

    if not drafts_per_giornata:
        return SimulazioneFRResult(
            n_dormite_fr=0,
            fr_cap_violazioni=[],
            prestazione_totale_min=0,
            condotta_totale_min=0,
            n_giornate=0,
            stazione_sede_usata=stazione_sede,
            stazione_sede_fallback=stazione_sede_fallback,
            avvertimenti=avvertimenti,
        )

    drafts_principali: list[_GiornataPdcDraft] = []
    for rami in drafts_per_giornata:
        if len(rami) == 1:
            drafts_principali.append(rami[0])

    if not drafts_principali:
        return SimulazioneFRResult(
            n_dormite_fr=0,
            fr_cap_violazioni=[],
            prestazione_totale_min=sum(
                r.prestazione_min for rami in drafts_per_giornata for r in rami
            ),
            condotta_totale_min=sum(
                r.condotta_min for rami in drafts_per_giornata for r in rami
            ),
            n_giornate=len(drafts_per_giornata),
            stazione_sede_usata=stazione_sede,
            stazione_sede_fallback=stazione_sede_fallback,
            avvertimenti=avvertimenti,
        )

    primo_draft = drafts_principali[0]
    stazione_sede_eff = (
        stazione_sede if stazione_sede is not None else primo_draft.stazione_inizio
    )

    fr_giornate = _aggiungi_dormite_fr(drafts_principali, stazione_sede_eff)
    n_fr = len(fr_giornate)
    cap_violazioni = _calcola_violazioni_cap_fr(
        n_dormite_fr=n_fr,
        ciclo_giorni=giro.numero_giornate,
    )

    return SimulazioneFRResult(
        n_dormite_fr=n_fr,
        fr_cap_violazioni=cap_violazioni,
        prestazione_totale_min=sum(d.prestazione_min for d in drafts_principali),
        condotta_totale_min=sum(d.condotta_min for d in drafts_principali),
        n_giornate=len(drafts_principali),
        stazione_sede_usata=stazione_sede_eff,
        stazione_sede_fallback=stazione_sede_fallback,
        avvertimenti=avvertimenti,
    )


@dataclass
class DepositoSuggerimento:
    """Una opzione del top-N per il dialog di generazione PdC."""

    deposito_pdc_id: int
    deposito_pdc_codice: str
    deposito_pdc_display: str
    stazione_principale_codice: str | None
    n_dormite_fr: int
    n_fr_cap_violazioni: int
    fr_cap_violazioni: list[str]
    prestazione_totale_min: int
    condotta_totale_min: int
    n_giornate: int
    stazione_sede_fallback: bool
    motivo: str
    """Stringa human-readable per la UI: 'Migliore — 0 FR' /
    '1 FR — secondo miglior match' / 'Cap settimanale violato' / etc."""


async def suggerisci_depositi(
    *,
    session: AsyncSession,
    azienda_id: int,
    giro_id: int,
    top_n: int = 3,
) -> list[DepositoSuggerimento]:
    """Calcola top-N depositi PdC ordinati per minor numero di FR.

    Scorre tutti i depositi attivi dell'azienda, simula
    ``genera_turno_pdc`` per ciascuno (read-only), e classifica:

    1. ``n_fr_cap_violazioni`` ascendente (zero violazioni cap meglio)
    2. ``n_dormite_fr`` ascendente (meno pernotti meglio)
    3. ``codice`` ascendente (deterministico a parità)

    I depositi senza ``stazione_principale_codice`` vengono comunque
    inclusi ma con flag ``stazione_sede_fallback=True``: il calcolo FR
    cade sulla sede del materiale e potrebbe essere meno significativo.

    Args:
        top_n: numero massimo di suggerimenti. Default 3. Clampato a [1, 25].

    Raises:
        GiroNonTrovatoError, GiroVuotoError.
    """
    top_n = max(1, min(top_n, 25))

    giro_check = (
        await session.execute(
            select(GiroMateriale.id).where(
                GiroMateriale.id == giro_id,
                GiroMateriale.azienda_id == azienda_id,
            )
        )
    ).scalar_one_or_none()
    if giro_check is None:
        raise GiroNonTrovatoError(
            f"Giro {giro_id} non trovato per azienda {azienda_id}"
        )

    depots = list(
        (
            await session.execute(
                select(Depot)
                .where(
                    Depot.azienda_id == azienda_id,
                    Depot.is_attivo,
                    Depot.tipi_personale_ammessi == "PdC",
                )
                .order_by(Depot.codice)
            )
        ).scalars()
    )

    if not depots:
        return []

    risultati: list[DepositoSuggerimento] = []
    for d in depots:
        sim = await simula_turno_pdc_fr(
            session=session,
            azienda_id=azienda_id,
            giro_id=giro_id,
            deposito_pdc_id=d.id,
        )
        risultati.append(
            DepositoSuggerimento(
                deposito_pdc_id=d.id,
                deposito_pdc_codice=d.codice,
                deposito_pdc_display=d.display_name,
                stazione_principale_codice=d.stazione_principale_codice,
                n_dormite_fr=sim.n_dormite_fr,
                n_fr_cap_violazioni=len(sim.fr_cap_violazioni),
                fr_cap_violazioni=sim.fr_cap_violazioni,
                prestazione_totale_min=sim.prestazione_totale_min,
                condotta_totale_min=sim.condotta_totale_min,
                n_giornate=sim.n_giornate,
                stazione_sede_fallback=sim.stazione_sede_fallback,
                motivo="",  # popolato sotto dopo l'ordinamento
            )
        )

    risultati.sort(
        key=lambda r: (
            r.n_fr_cap_violazioni,
            r.n_dormite_fr,
            1 if r.stazione_sede_fallback else 0,
            r.deposito_pdc_codice,
        )
    )

    top = risultati[:top_n]
    for idx, r in enumerate(top):
        r.motivo = _motivo(idx, r)
    return top


def _motivo(rank: int, r: DepositoSuggerimento) -> str:
    """Spiegazione human-readable per la UI del suggerimento."""
    if r.n_fr_cap_violazioni > 0:
        return f"⚠ Cap FR violato ({r.n_fr_cap_violazioni}) — sconsigliato"
    if r.stazione_sede_fallback:
        return (
            "⚠ Stazione principale del deposito non configurata — "
            "stima approssimativa"
        )
    if r.n_dormite_fr == 0:
        return "Migliore — nessuna dormita FR" if rank == 0 else "Nessuna dormita FR"
    if rank == 0:
        return f"Migliore disponibile — {r.n_dormite_fr} FR"
    return f"{r.n_dormite_fr} FR nel ciclo"
