"""HIGH-1 SEVERO MR-A7: misura composizione pool esplorativo prog 17.

Conta:
- corse_totali_periodo: tutte le corse del PdE valide nel periodo del programma
- corse_tier0: matchano almeno una regola sui filtri (Tier 0)
- corse_tier1_only: matchano solo Tier 1 (materiale, filtri ignorati)
- corse_fuori_pool: nessuna regola le prende neanche al Tier 1

Per prog 17 (1 regola: ETR522 FIO direttrici X/Y/Z), atteso:
- tier0 = corse delle 3 direttrici (= 765 dal run rigido)
- tier1_only = corse fuori 3 direttrici ma materiale ETR522 compatibile
- fuori_pool = corse non-ETR522

Uso: cd backend && PYTHONPATH=src uv run python scripts/diag_pool_esplorativo.py [pid=17]
"""

from __future__ import annotations

import asyncio
import sys
from collections import Counter

from sqlalchemy import select

from colazione.db import session_scope
from colazione.domain.builder_giro.builder import (
    _carica_accoppiamenti_ammessi,
    _carica_corse,
    _carica_localita,
    _carica_stazioni_lookup,
    _carica_whitelist_stazioni,
    _trova_regola_dominante_esplorativa,
)
from colazione.domain.builder_giro.risolvi_corsa import matches_all
from colazione.domain.vincoli import carica_vincoli
from colazione.models.programmi import ProgrammaMateriale, ProgrammaRegolaAssegnazione


async def main(programma_id: int = 17) -> None:
    async with session_scope() as session:
        prog = (
            await session.execute(
                select(ProgrammaMateriale).where(ProgrammaMateriale.id == programma_id)
            )
        ).scalar_one_or_none()
        if prog is None:
            print(f"prog {programma_id} non trovato")
            return

        # Regole della prima sede (tipicamente FIO per prog 17)
        regole = (
            await session.execute(
                select(ProgrammaRegolaAssegnazione).where(
                    ProgrammaRegolaAssegnazione.programma_id == programma_id
                )
            )
        ).scalars().all()
        sede_codice = regole[0].localita_codice if regole else None
        regole_sede = [r for r in regole if r.localita_codice == sede_codice]
        print(f"prog {programma_id} '{prog.nome}': {len(regole)} regole totali, "
              f"sede principale='{sede_codice}', regole sede={len(regole_sede)}")

        # Carica corse del periodo
        corse = await _carica_corse(
            session, prog.azienda_id, prog.valido_da, prog.valido_a
        )
        print(f"corse caricate (PdE periodo): {len(corse)}")

        # Carica vincoli + lookup
        localita = await _carica_localita(session, sede_codice, prog.azienda_id)
        whitelist = await _carica_whitelist_stazioni(session, localita.id)
        stazioni_lookup = await _carica_stazioni_lookup(session, prog.azienda_id)
        accoppiamenti = await _carica_accoppiamenti_ammessi(session)

        # Vincoli inviolabili: identico al builder (entry 96 + MR-A3-bis)
        vincoli_inviolabili = carica_vincoli()

        # Per ogni corsa: Tier 0 (matcha filtri) o Tier 1-only (solo materiale)?
        tier0 = []
        tier1_only = []
        fuori_pool = []
        for c in corse:
            # Tier 0: una regola matcha TUTTI i filtri
            t0 = any(matches_all(r.filtri_json, c, "feriale") for r in regole_sede)
            # Tier 0 OR Tier 1 (esplorativo)
            t01 = _trova_regola_dominante_esplorativa(
                c,
                regole_sede,
                vincoli_inviolabili=vincoli_inviolabili,
                stazioni_lookup=stazioni_lookup,
            ) is not None
            if t0:
                tier0.append(c)
            elif t01:
                tier1_only.append(c)
            else:
                fuori_pool.append(c)

        print(f"\n=== Composizione pool esplorativo (Tier-based) ===")
        print(f"  Tier 0 (matcha filtri):           {len(tier0):>5} corse")
        print(f"  Tier 1 only (solo materiale):    {len(tier1_only):>5} corse  ← rumore SEVERO HIGH-1")
        print(f"  Fuori pool (nessuna regola):     {len(fuori_pool):>5} corse")
        print(f"  Pool esplorativo totale:          {len(tier0) + len(tier1_only):>5} corse")
        print(f"  Pool rigido totale:               {len(tier0):>5} corse")
        print(f"  Inflazione esplorativo:           +{len(tier1_only):>4} ({len(tier1_only)/max(len(tier0),1)*100:.1f}%)")

        # Distribuzione tier1_only per direttrice/codice_linea (pattern reali)
        if tier1_only:
            print(f"\n=== Pattern del rumore Tier 1 (top 10 direttrici) ===")
            direttrici_t1 = Counter(c.direttrice or "(nullo)" for c in tier1_only)
            for d, n in direttrici_t1.most_common(10):
                print(f"  {n:>4} corse — direttrice={d!r}")

            print(f"\n=== Top 10 codici linea ===")
            linee_t1 = Counter(c.codice_linea or "(nullo)" for c in tier1_only)
            for l, n in linee_t1.most_common(10):
                print(f"  {n:>4} corse — codice_linea={l!r}")

            print(f"\n=== Top 10 categorie ===")
            cat_t1 = Counter(c.categoria or "(nullo)" for c in tier1_only)
            for cat, n in cat_t1.most_common(10):
                print(f"  {n:>4} corse — categoria={cat!r}")


if __name__ == "__main__":
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 17
    asyncio.run(main(pid))
