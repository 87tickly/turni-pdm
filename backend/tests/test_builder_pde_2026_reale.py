"""MR-1110 sotto-MR 8 (entry 208) — integration test PdE 2026 REALE.

Test "opzione B" gated da env var: gira solo quando il DB locale ha
il PdE Trenord 2026 importato e l'utente vuole esercitarlo. Usa
``data/turni_materiale_2026_dump.json`` (54 turni Trenord estratti
dal PDF deposito) come **oracolo di riferimento**: per ogni turno
nominato (es. 1110, 1104, 1125), il builder COLAZIONE deve produrre
un giro con caratteristiche compatibili (numero giornate, materiale
compatibile, sede compatibile).

**Gating**:

- ``RUN_REAL_PDE_TESTS=1`` → attiva i test.
- ``data/turni_materiale_2026_dump.json`` deve esistere (è gitignored
  fuori repo per i dati grezzi del PdE; il dump dei turni è invece
  committato come fixture pubblica — vedi memoria
  ``reference_pdf_turno_materiale_2026.md``).
- DB di test deve avere PdE 2026 importato (``CorsaCommerciale`` con
  ``valido_da`` ≤ 2026-12-31 e ``valido_a`` ≥ 2026-01-01).

**Skip ragionato**: senza una di queste condizioni, ``pytest.skip``
con messaggio esplicativo che spiega come abilitare. Niente magia.

**Acceptance "soft"**: il PDF Trenord NON è oracle bit-per-bit per
il nostro builder (è il loro algoritmo, noi facciamo il nostro). Il
test verifica solo:

1. Builder produce ≥ 1 giro per la sede del turno.
2. Il giro generato ha materiale compatibile (famiglia ETRxxx /
   ALe7xx / E464 / ATR coerente con il turno Trenord).
3. ``numero_giornate`` del giro è nell'ordine di grandezza atteso
   (entro ±50% del turno Trenord).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# Skip dell'intero modulo se l'env var non è impostata.
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_REAL_PDE_TESTS") != "1",
    reason=(
        "Test PdE 2026 reale disabilitato. "
        "Per abilitare: RUN_REAL_PDE_TESTS=1 + DB con PdE 2026 importato."
    ),
)


# Path del dump turni (committato in repo come fixture oracolo).
DUMP_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "turni_materiale_2026_dump.json"
)


def _carica_oracolo_turni() -> list[dict[str, object]]:
    """Carica il dump dei 54 turni Trenord 2026 come oracolo.

    Skip se il file non esiste (caso primo run su clone fresco senza
    estrazione PDF).
    """
    if not DUMP_PATH.is_file():
        pytest.skip(
            f"Oracolo turni non disponibile: {DUMP_PATH}. "
            "Genera con lo script di estrazione PDF Trenord (vedi memoria "
            "reference_pdf_turno_materiale_2026.md)."
        )
    with DUMP_PATH.open() as f:
        data = json.load(f)
    turni = data.get("turni", [])
    assert isinstance(turni, list) and len(turni) > 0, (
        f"Oracolo {DUMP_PATH} non contiene turni"
    )
    return turni


def test_oracolo_turni_caricabile() -> None:
    """Smoke: il dump è leggibile e contiene 54 turni con i campi
    attesi (``numero_turno``, ``famiglie_materiale``, ``sede_manutenzione``,
    ``numero_giornate``).
    """
    turni = _carica_oracolo_turni()
    assert len(turni) >= 50, f"Atteso ≥ 50 turni, trovati {len(turni)}"
    primo = turni[0]
    assert "numero_turno" in primo
    assert "famiglie_materiale" in primo
    assert "sede_manutenzione" in primo
    assert "numero_giornate" in primo


# NOTA: i test E2E "builder COLAZIONE vs oracolo Trenord" richiedono:
#
# 1. PdE 2026 caricato in DB di test (tabella ``corsa_commerciale``).
# 2. Anagrafica località manutenzione popolata (FIO/CRE/LEC/NOV/CAM/ISE).
# 3. Whitelist stazioni vicine (migration 0012 + seed produzione).
# 4. Programmi creati per ogni regola da testare.
#
# Lo scaffold qui è di proposito minimale: aggiungere test concreti
# quando l'utente ha un setup DB di staging stabile con i dati 2026
# importati. Il pattern d'uso:
#
# @pytest.mark.asyncio
# async def test_turno_1110_etr526_4_giornate(azienda_id: int) -> None:
#     turni = _carica_oracolo_turni()
#     turno_1110 = next(t for t in turni if t["numero_turno"] == "1110")
#     # ... setup programma + regola dal turno_1110 ...
#     # ... genera_giri ...
#     # ... assert n_giornate, materiale, sede compatibili ...
