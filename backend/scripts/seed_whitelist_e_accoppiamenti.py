"""Seed whitelist stazioni-vicine-sede + accoppiamenti materiali — Sprint 5.2.

Popola le tabelle introdotte da migration 0007 con i dati operativi di
Trenord, in 3 sezioni atomiche e idempotenti:

1. **Materiali famiglia ETR**: aggiunge `materiale_tipo` aggregati per
   le 2 famiglie operative Trenord (decisione utente 2026-04-27):
     - **Coradia Meridian** (Alstom): ETR425 (5 casse), ETR526 (6 casse)
     - **Caravaggio** (Hitachi, anche detto **Rock**):
       ETR421 (4 casse), ETR521 (5 casse, **solo singola, non
       accoppiabile**), ETR522 (5 casse)
   Il `componenti_json` include `n_casse` (lunghezza tipica del
   convoglio) e `pezzi_inventario` (codici pezzi nominali dal seed
   0002 — varianti di motrici/rimorchiate). Senza queste famiglie non
   si può rappresentare un convoglio intero in una regola
   `programma_regola_assegnazione.composizione_json`.

   **Sub 5.2 parte 1** inserisce solo i 5 materiali con dati certi.
   Altri (Donizetti ETR103/104/204, ATR 803/125/115, ALn668, E464,
   ALe245, ALe711 TSR, TAF, locomotori manovra D520/D744) saranno
   aggiunti in Sub 5.2 parte 2 dopo conferma utente sui dati
   `n_casse` e `famiglia`.

2. **Whitelist stazioni-vicine-sede** (`localita_stazione_vicina`):
   per ogni sede manutentiva (FIO/NOV/CAM/LEC/CRE/ISE) un set di
   stazioni in cui sono ammessi i vuoti tecnici (vedi
   `docs/SPRINT-5-RIPENSAMENTO.md` §3). Le stazioni sono cercate per
   **nome** con pattern `ILIKE` — più resiliente di hardcodare codici
   (multi-tenant, robusto a rinumerazioni del PdE annuale).

3. **Accoppiamenti materiali ammessi**
   (`materiale_accoppiamento_ammesso`): coppie ammesse di rotabili in
   doppia composizione. Normalizzate lessicograficamente
   (`materiale_a_codice <= materiale_b_codice`).

Uso::

    cd backend
    PYTHONPATH=src uv run python scripts/seed_whitelist_e_accoppiamenti.py
    PYTHONPATH=src uv run python scripts/seed_whitelist_e_accoppiamenti.py --dry-run
    PYTHONPATH=src uv run python scripts/seed_whitelist_e_accoppiamenti.py --azienda trenord -v

Prerequisiti:
- migration 0007 applicata (`alembic upgrade head`)
- per la sezione 2: stazioni Trenord nel DB (import PdE eseguito)
- per la sezione 3: nessuno; lo script crea le famiglie ETR* in sezione 1

Comportamento:
- **Idempotente**: rilancialo quante volte vuoi, ON CONFLICT DO NOTHING
  ovunque. Counter finale distingue inseriti vs già presenti.
- **Atomico**: le 3 sezioni vivono in una sola transazione. Se la
  sezione 2 fallisce per pattern ambiguo, niente viene scritto.
- **Fail-fast**: pattern stazione 0-match o >1-match → exit 1 con
  messaggio chiaro (lista delle stazioni trovate per >1, suggerimento
  per 0).
- **Multi-tenant**: `--azienda <codice>` per scegliere l'azienda;
  default `trenord`.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.db import session_scope
from colazione.models.anagrafica import (
    Azienda,
    LocalitaManutenzione,
    LocalitaStazioneVicina,
    MaterialeAccoppiamentoAmmesso,
    MaterialeTipo,
    Stazione,
)

logger = logging.getLogger("seed_whitelist_e_accoppiamenti")


# =====================================================================
# Configurazione Trenord (dati di seed)
# =====================================================================


#: Materiali famiglia ETR aggregati. Ogni record corrisponde al
#: convoglio intero (es. ETR526 = 6 casse). Il `componenti_json` include
#: `n_casse` (lunghezza tipica del convoglio) e `pezzi_inventario`
#: (codici pezzi nominali dal seed 0002 — inventario Trenord, varianti
#: di motrici/rimorchiate disponibili). I pezzi specifici di un singolo
#: convoglio fisico sono un sottoinsieme di `pezzi_inventario` con
#: cardinalità `n_casse`; la configurazione esatta è scope futuro.
#:
#: Le 2 famiglie operative confermate dall'utente (2026-04-27):
#:   - Coradia Meridian (Alstom): ETR425 (5 casse) + ETR526 (6 casse)
#:   - Caravaggio (Hitachi, anche detto Rock):
#:     ETR421 (4 casse) + ETR521 (5 casse, NON accoppiabile) +
#:     ETR522 (5 casse)
@dataclass(frozen=True)
class _MaterialeFamiglia:
    codice: str
    nome_commerciale: str
    famiglia: str
    n_casse: int
    pezzi_inventario: list[str]


MATERIALI_FAMIGLIA_TRENORD: list[_MaterialeFamiglia] = [
    _MaterialeFamiglia(
        codice="ETR421",
        nome_commerciale="ETR421",
        famiglia="Caravaggio (Rock)",
        n_casse=4,
        pezzi_inventario=[
            "TN-Ale421-DM1",
            "TN-Ale421-DM2",
            "TN-Le421-TA",
            "TN-Le421-TB",
            "TN-Le421-TB1",
        ],
    ),
    _MaterialeFamiglia(
        # ETR521 = ROCK 5 casse, NON accoppiabile (solo singola).
        # L'assenza in `ACCOPPIAMENTI_TRENORD` enforça il vincolo:
        # `materiale_accoppiamento_ammesso` registra solo coppie ammesse.
        codice="ETR521",
        nome_commerciale="ETR521 (Rock)",
        famiglia="Caravaggio (Rock)",
        n_casse=5,
        pezzi_inventario=[
            "TN-Ale521-DM1",
            "TN-Ale521-DM2",
            "TN-Le521-TA",
            "TN-Le521-TB",
            "TN-Le521-TX",
        ],
    ),
    _MaterialeFamiglia(
        codice="ETR522",
        nome_commerciale="ETR522",
        famiglia="Caravaggio (Rock)",
        n_casse=5,
        pezzi_inventario=[
            "TN-Ale522-DM1",
            "TN-Ale522-DM2",
            "TN-Le522-TA",
            "TN-Le522-TB",
            "TN-Le522-TB1",
            "TN-Le522-TX",
        ],
    ),
    _MaterialeFamiglia(
        codice="ETR425",
        nome_commerciale="ETR425",
        famiglia="Coradia Meridian",
        n_casse=5,
        pezzi_inventario=[
            "TN-Ale425-A41",
            "TN-Ale425-A46",
            "TN-Le425-A42-A45",
            "TN-Le425-A43",
        ],
    ),
    _MaterialeFamiglia(
        codice="ETR526",
        nome_commerciale="ETR526",
        famiglia="Coradia Meridian",
        n_casse=6,
        pezzi_inventario=[
            "TN-Ale526-A41",
            "TN-Ale526-A46",
            "TN-Le526-A43",
        ],
    ),
]


#: Whitelist stazioni-vicine-sede. Per ogni sede manutentiva, un elenco
#: di pattern di nome stazione (case-insensitive, % come wildcard SQL).
#: Lo script cerca con `ILIKE` e accetta esattamente 1 match per
#: pattern; 0 o N match → errore.
#:
#: TILO è omesso volutamente: pool esterno con vincolo unico "rientro
#: in CH ogni sera", niente whitelist Italia (vedi piano §3).
WHITELIST_TRENORD: dict[str, list[str]] = {
    "IMPMAN_MILANO_FIORENZA": [  # FIO
        "%MILANO%GARIBALDI%",
        "%MILANO%CENTRALE%",
        "%MILANO%LAMBRATE%",
        "%MILANO%ROGOREDO%",
        "%MILANO%GRECO%PIRELLI%",
    ],
    "IMPMAN_NOVATE": [  # NOV
        "%MILANO%CADORNA%",
        "%MILANO%BOVISA%",
        "SARONNO",  # condivisa con CAM
    ],
    "IMPMAN_CAMNAGO": [  # CAM
        "SEVESO",
        "SARONNO",  # condivisa con NOV
    ],
    "IMPMAN_LECCO": [  # LEC
        "LECCO",
    ],
    "IMPMAN_CREMONA": [  # CRE
        "CREMONA",
    ],
    "IMPMAN_ISEO": [  # ISE
        "ISEO",
    ],
}


#: Accoppiamenti ammessi (decisione utente 2026-04-27, plan §3).
#: Normalizzati lessicograficamente (a <= b) — la migration 0007 ha
#: un CHECK che lo enforza.
#:
#: I 3 confermati al 2026-04-27. ETR521 è esplicitamente NON
#: accoppiabile (solo singola, decisione utente). Plausibili (da
#: chiedere all'utente prima di aggiungere): ETR522+ETR522,
#: ETR421+ETR522 (stessa famiglia Caravaggio/Rock); ETR425+ETR425
#: (stessa famiglia Coradia Meridian).
ACCOPPIAMENTI_TRENORD: list[tuple[str, str]] = [
    ("ETR421", "ETR421"),
    ("ETR425", "ETR526"),  # 425 < 526 lex
    ("ETR526", "ETR526"),
]


# =====================================================================
# Risultato e errori
# =====================================================================


@dataclass
class SeedReport:
    """Counter dell'esecuzione, stampato a fine run."""

    materiali_inseriti: int = 0
    materiali_skippati: int = 0
    whitelist_inserite: int = 0
    whitelist_skippate: int = 0
    accoppiamenti_inseriti: int = 0
    accoppiamenti_skippati: int = 0


class SeedError(RuntimeError):
    """Errore di pre-condizione: stazione/materiale mancante o ambiguo."""


# =====================================================================
# Sezione 1 — Materiali famiglia ETR
# =====================================================================


async def _seed_materiali_famiglia(
    session: AsyncSession,
    azienda_id: int,
    report: SeedReport,
    materiali: list[_MaterialeFamiglia],
) -> None:
    """Upsert dei `materiale_tipo` famiglia.

    Idempotente: ON CONFLICT (codice) DO NOTHING. La PK è il `codice`,
    quindi un record già presente non viene toccato.
    """
    for fam in materiali:
        stmt = (
            pg_insert(MaterialeTipo)
            .values(
                codice=fam.codice,
                nome_commerciale=fam.nome_commerciale,
                famiglia=fam.famiglia,
                componenti_json={
                    "n_casse": fam.n_casse,
                    "pezzi_inventario": fam.pezzi_inventario,
                },
                azienda_id=azienda_id,
            )
            .on_conflict_do_nothing(index_elements=["codice"])
            .returning(MaterialeTipo.codice)
        )
        result = await session.execute(stmt)
        if result.scalar() is not None:
            report.materiali_inseriti += 1
            logger.info(
                "  + materiale famiglia %s (%d casse, famiglia %r)",
                fam.codice,
                fam.n_casse,
                fam.famiglia,
            )
        else:
            report.materiali_skippati += 1
            logger.debug("  · materiale famiglia %s già presente, skip", fam.codice)


# =====================================================================
# Sezione 2 — Whitelist stazioni-vicine-sede
# =====================================================================


async def _risolvi_pattern_stazione(session: AsyncSession, azienda_id: int, pattern: str) -> str:
    """Trova il codice stazione che matcha il pattern (ILIKE).

    Errore esplicito se 0 match (suggerisce di importare il PdE) o
    >1 match (lista i candidati per raffinare il pattern).
    """
    stmt = (
        select(Stazione.codice, Stazione.nome)
        .where(Stazione.azienda_id == azienda_id, Stazione.nome.ilike(pattern))
        .order_by(Stazione.nome)
    )
    rows = list((await session.execute(stmt)).all())
    if len(rows) == 0:
        raise SeedError(
            f"Pattern stazione {pattern!r} non matcha nessuna stazione per "
            f"azienda_id={azienda_id}. Hai importato il PdE? Comando:\n"
            f'  uv run python -m colazione.importers.pde_importer --file "..." --azienda <codice>'
        )
    if len(rows) > 1:
        candidati = "\n  - ".join(f"{r.codice} ({r.nome})" for r in rows)
        raise SeedError(
            f"Pattern stazione {pattern!r} matcha {len(rows)} stazioni "
            f"(atteso 1). Candidate:\n  - {candidati}\n"
            f"Raffina il pattern nella whitelist."
        )
    return str(rows[0].codice)


async def _carica_localita(
    session: AsyncSession, codice: str, azienda_id: int
) -> LocalitaManutenzione:
    stmt = select(LocalitaManutenzione).where(
        LocalitaManutenzione.codice == codice,
        LocalitaManutenzione.azienda_id == azienda_id,
    )
    loc = (await session.execute(stmt)).scalar_one_or_none()
    if loc is None:
        raise SeedError(
            f"Località {codice!r} non trovata per azienda_id={azienda_id}. Verifica seed 0002."
        )
    return loc


async def _seed_whitelist(
    session: AsyncSession,
    azienda_id: int,
    report: SeedReport,
    whitelist: dict[str, list[str]],
) -> None:
    """Per ogni sede in `whitelist`, risolve i pattern e fa INSERT
    idempotente su `localita_stazione_vicina`."""
    for localita_codice, patterns in whitelist.items():
        loc = await _carica_localita(session, localita_codice, azienda_id)
        logger.info("Sede %s (id=%d, breve=%s):", loc.codice, loc.id, loc.codice_breve)
        for pattern in patterns:
            stazione_codice = await _risolvi_pattern_stazione(session, azienda_id, pattern)
            stmt = (
                pg_insert(LocalitaStazioneVicina)
                .values(
                    localita_manutenzione_id=loc.id,
                    stazione_codice=stazione_codice,
                )
                .on_conflict_do_nothing(
                    index_elements=["localita_manutenzione_id", "stazione_codice"]
                )
                .returning(LocalitaStazioneVicina.id)
            )
            result = await session.execute(stmt)
            if result.scalar() is not None:
                report.whitelist_inserite += 1
                logger.info(
                    "  + whitelist %s ← %s (pattern %r)",
                    loc.codice_breve,
                    stazione_codice,
                    pattern,
                )
            else:
                report.whitelist_skippate += 1
                logger.debug(
                    "  · whitelist %s ← %s già presente (pattern %r), skip",
                    loc.codice_breve,
                    stazione_codice,
                    pattern,
                )


# =====================================================================
# Sezione 3 — Accoppiamenti materiali
# =====================================================================


async def _verifica_materiale_esiste(session: AsyncSession, codice: str, azienda_id: int) -> None:
    stmt = select(MaterialeTipo.codice).where(
        MaterialeTipo.codice == codice,
        MaterialeTipo.azienda_id == azienda_id,
    )
    found = (await session.execute(stmt)).scalar_one_or_none()
    if found is None:
        raise SeedError(
            f"Materiale {codice!r} non trovato per azienda_id={azienda_id}. "
            f"La sezione 1 dovrebbe averlo creato — verifica."
        )


async def _seed_accoppiamenti(
    session: AsyncSession,
    azienda_id: int,
    report: SeedReport,
    accoppiamenti: list[tuple[str, str]],
) -> None:
    """Verifica esistenza materiali + INSERT idempotente sugli accoppiamenti."""
    for a, b in accoppiamenti:
        if a > b:
            raise SeedError(
                f"Accoppiamento ({a!r}, {b!r}) non normalizzato: "
                f"deve valere a <= b lessicograficamente."
            )
        await _verifica_materiale_esiste(session, a, azienda_id)
        if a != b:
            await _verifica_materiale_esiste(session, b, azienda_id)
        stmt = (
            pg_insert(MaterialeAccoppiamentoAmmesso)
            .values(materiale_a_codice=a, materiale_b_codice=b)
            .on_conflict_do_nothing(index_elements=["materiale_a_codice", "materiale_b_codice"])
            .returning(MaterialeAccoppiamentoAmmesso.id)
        )
        result = await session.execute(stmt)
        if result.scalar() is not None:
            report.accoppiamenti_inseriti += 1
            logger.info("  + accoppiamento %s + %s", a, b)
        else:
            report.accoppiamenti_skippati += 1
            logger.debug("  · accoppiamento %s + %s già presente, skip", a, b)


# =====================================================================
# Orchestrator
# =====================================================================


async def seed_all(
    session: AsyncSession,
    azienda_codice: str,
    *,
    dry_run: bool = False,
    materiali: list[_MaterialeFamiglia] | None = None,
    whitelist: dict[str, list[str]] | None = None,
    accoppiamenti: list[tuple[str, str]] | None = None,
) -> SeedReport:
    """Esegue le 3 sezioni in transazione. Se ``dry_run``, ROLLBACK alla fine.

    I parametri ``materiali``, ``whitelist``, ``accoppiamenti`` sono
    opzionali: default ai const di modulo (`MATERIALI_FAMIGLIA_TRENORD`,
    `WHITELIST_TRENORD`, `ACCOPPIAMENTI_TRENORD`). Override permette di
    testare con dati mock isolati o di seedare aziende non-Trenord con
    config custom.
    """
    if materiali is None:
        materiali = MATERIALI_FAMIGLIA_TRENORD
    if whitelist is None:
        whitelist = WHITELIST_TRENORD
    if accoppiamenti is None:
        accoppiamenti = ACCOPPIAMENTI_TRENORD

    report = SeedReport()

    # Carica azienda
    stmt = select(Azienda).where(Azienda.codice == azienda_codice)
    azienda = (await session.execute(stmt)).scalar_one_or_none()
    if azienda is None:
        raise SeedError(f"Azienda {azienda_codice!r} non trovata.")
    azienda_id = azienda.id

    logger.info(
        "Seed whitelist + accoppiamenti per azienda %s (id=%d)%s",
        azienda_codice,
        azienda_id,
        " [DRY-RUN]" if dry_run else "",
    )

    logger.info("--- Sezione 1: materiali famiglia ETR ---")
    await _seed_materiali_famiglia(session, azienda_id, report, materiali)

    logger.info("--- Sezione 2: whitelist stazioni-vicine-sede ---")
    await _seed_whitelist(session, azienda_id, report, whitelist)

    logger.info("--- Sezione 3: accoppiamenti materiali ---")
    await _seed_accoppiamenti(session, azienda_id, report, accoppiamenti)

    if dry_run:
        logger.info("DRY-RUN: rollback transazione, nulla scritto.")
        await session.rollback()
    return report


# =====================================================================
# CLI
# =====================================================================


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/seed_whitelist_e_accoppiamenti.py",
        description=(
            "Popola whitelist stazioni-vicine-sede + accoppiamenti materiali "
            "per il builder giro (Sprint 5.2). Idempotente."
        ),
    )
    parser.add_argument(
        "--azienda",
        type=str,
        default="trenord",
        help="codice azienda (default: trenord)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="esegue tutto in transazione e fa rollback (no scritture)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="log DEBUG (mostra anche i record già presenti, skippati)",
    )
    return parser


async def _main_async(azienda: str, dry_run: bool) -> SeedReport:
    async with session_scope() as session:
        report = await seed_all(session, azienda, dry_run=dry_run)
    return report


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )
    try:
        report = asyncio.run(_main_async(args.azienda, args.dry_run))
    except SeedError as exc:
        print(f"\nERRORE: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        logger.exception("errore inatteso")
        print(f"\nERRORE INATTESO: {exc}", file=sys.stderr)
        return 1

    print(
        "\nReport:\n"
        f"  Materiali famiglia: {report.materiali_inseriti} inseriti, "
        f"{report.materiali_skippati} già presenti\n"
        f"  Whitelist stazioni: {report.whitelist_inserite} inserite, "
        f"{report.whitelist_skippate} già presenti\n"
        f"  Accoppiamenti:      {report.accoppiamenti_inseriti} inseriti, "
        f"{report.accoppiamenti_skippati} già presenti"
    )
    return 0


if __name__ == "__main__":
    # Sanity: richiama text() inutilizzato per evitare ruff F401 quando
    # l'import resta lì come comodità per future query manuali.
    _ = text
    sys.exit(main())
