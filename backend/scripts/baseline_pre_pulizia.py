"""MR 0 — baseline conta righe pre-pulizia dati di prova.

Lo eseguo via ``railway run --service backend -- uv run python
scripts/baseline_pre_pulizia.py`` PRIMA di applicare la pulizia, per
salvare il numero esatto di righe in ciascuna tabella che andremo a
svuotare. Il risultato finisce in TN-UPDATE come baseline storica.

Read-only: nessuna modifica al DB. Sicuro da rilanciare a piacere.
"""

from __future__ import annotations

import asyncio
import os

# Lo script viene eseguito da locale via ``railway run --service Postgres``,
# che inietta sia ``DATABASE_URL`` (interna, postgres.railway.internal,
# non risolvibile da fuori) sia ``DATABASE_PUBLIC_URL`` (proxy pubblico
# Railway). Preferisci la pubblica quando disponibile.
_url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL", "")

# Forza il driver psycopg3: gli URL Railway arrivano come ``postgresql://``,
# ma il default SQLAlchemy = psycopg2 (non installato).
if _url.startswith("postgresql://"):
    _url = _url.replace("postgresql://", "postgresql+psycopg://", 1)
elif _url.startswith("postgres://"):
    _url = _url.replace("postgres://", "postgresql+psycopg://", 1)

os.environ["DATABASE_URL"] = _url

from sqlalchemy import text  # noqa: E402

from colazione.db import session_scope  # noqa: E402

# Tabelle che il MR 0 svuoterà, in ordine FK-safe (stesse del DELETE).
# Se una tabella manca dal DB stampiamo "n/a" e proseguiamo.
#
# Decisione utente 2026-05-05: il blocco PdE (corsa_commerciale +
# composizione + materiale_vuoto + import_run) **non è di prova**, è la
# base operativa attuale per la generazione. Lo lasciamo intatto e
# resta nel gruppo [B] insieme all'anagrafica.
TABELLE_DA_SVUOTARE: list[str] = [
    # Revisioni
    "revisione_provvisoria_pdc",
    "revisione_provvisoria_blocco",
    "revisione_provvisoria",
    # Turni PdC
    "turno_pdc_blocco",
    "turno_pdc_giornata",
    "turno_pdc",
    # Assegnazioni personale
    "assegnazione_giornata",
    # Giri materiale
    "giro_blocco",
    "giro_variante",
    "giro_giornata",
    "giro_finestra_validita",
    "versione_base_giro",
    "giro_materiale",
    # Builder runs
    "builder_run",
    # Programmi e regole correlate
    "regola_invio_sosta",
    "localita_sosta",
    "programma_regola_assegnazione",
    "programma_materiale",
]

# Tabelle preservate (anagrafica + PdE base). NON svuotate dal MR 0, ma
# le contiamo per rassicurarci che non vengano toccate per errore.
TABELLE_ANAGRAFICA: list[str] = [
    # Anagrafica organizzazione/asset/persone
    "azienda",
    "stazione",
    "materiale_tipo",
    "materiale_dotazione_azienda",
    "materiale_istanza",
    "materiale_thread",
    "materiale_thread_evento",
    "materiale_accoppiamento_ammesso",
    "localita_manutenzione",
    "localita_manutenzione_dotazione",
    "depot",
    "depot_linea_abilitata",
    "depot_materiale_abilitato",
    "localita_stazione_vicina",
    "festivita_ufficiale",
    "persona",
    "indisponibilita_persona",
    # PdE importato (base operativa, da preservare)
    "corsa_import_run",
    "corsa_commerciale",
    "corsa_composizione",
    "corsa_materiale_vuoto",
]


async def conta_tabella(tabella: str) -> int | None:
    """Esegue ``SELECT COUNT(*) FROM <tabella>``. None se non esiste."""
    from sqlalchemy.exc import ProgrammingError

    async with session_scope() as session:
        try:
            result = await session.execute(text(f"SELECT COUNT(*) FROM {tabella}"))
            return int(result.scalar_one())
        except ProgrammingError as exc:
            # UndefinedTable → tabella non esiste; altri errori di parsing rilanciati
            if "UndefinedTable" in str(exc.orig.__class__.__name__):
                return None
            raise


async def main() -> None:
    print("=" * 70)
    print("BASELINE PRE-PULIZIA — MR 0")
    print("=" * 70)

    print("\n[A] Tabelle DA SVUOTARE (dati di prova):")
    print("-" * 70)
    totale_svuotare = 0
    for tabella in TABELLE_DA_SVUOTARE:
        n = await conta_tabella(tabella)
        if n is None:
            print(f"  {tabella:<40} n/a (tabella inesistente)")
        else:
            totale_svuotare += n
            print(f"  {tabella:<40} {n:>10}")

    print(f"\n  TOTALE righe da rimuovere: {totale_svuotare}")

    print("\n[B] Tabelle ANAGRAFICA/SEED (NON toccate):")
    print("-" * 70)
    totale_anagrafica = 0
    for tabella in TABELLE_ANAGRAFICA:
        n = await conta_tabella(tabella)
        if n is None:
            print(f"  {tabella:<40} n/a (tabella inesistente)")
        else:
            totale_anagrafica += n
            print(f"  {tabella:<40} {n:>10}")

    print(f"\n  TOTALE righe anagrafica (devono restare invariate): {totale_anagrafica}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
