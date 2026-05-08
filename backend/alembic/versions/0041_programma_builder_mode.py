"""0041 — programma_materiale.builder_mode (Sprint 8.1 MR-A1).

MR-A1 della revisione builder turno materiale (Sprint 8.1, entry 242).
Aggiunge ``programma_materiale.builder_mode`` (String(20), NOT NULL,
server_default ``'rigido'``).

**Semantica**:

- ``'rigido'`` (default, retrocompat) = builder filtra-e-scarta.
  Logica attuale: regola del programma = filtro hard, corse che non
  matchano AND di tutti i filtri restano residue, cicli aperti
  persistiti senza tentativo di chiusura.
- ``'esplorativo'`` = builder esplora-e-rilassa. Regole = vincoli
  soft pesati con fallback governato (decisione utente 2026-05-08
  Q1=b): prova prima il vincolo (es. linea=R11), se non basta a
  coprire/chiudere allarga con criterio (materiali compatibili,
  vuoti di rientro, linee adiacenti). Cicli aperti tollerati ma
  marcati (Q2=b): builder tenta chiusura attiva con vuoti di
  posizionamento; se fallisce, marker esplicito per intervento manuale.

**Sintomi che motivano questo refactor** (programma 17 reale):
150 corse non coperte (22 sosta condivisa, 128 linea disgiunta), ~50%
giri da 1 sola giornata, cicli aperti persistiti (es. G-FIO-026 parte
Alessandria, termina Milano Certosa), regola unica "linea=R11" → 0
giri generati.

**CHECK constraint**: il campo accetta solo ``'rigido'`` o ``'esplorativo'``.
Tentativi di set ad altri valori falliscono al COMMIT.

**Backward compat**: programmi esistenti ricevono ``'rigido'`` via
``server_default``, nessuna logica esistente si rompe. Il flag è
**foundation pura** in MR-A1: nessun consumatore lo legge ancora.
MR-A3 introdurrà il branching in ``risolvi_corsa``, MR-A4 il
backtracking esplorativo, MR-A8 lo switch del default a ``'esplorativo'``
con cleanup del branch ``'rigido'``.

**Ortogonale a `builder_version`** (migration 0038): quel campo sceglie
la pipeline architetturale (v1 multi_giornata legacy / v2 turni con
catene-istanza). ``builder_mode`` sceglie la logica di assegnazione
corsa→regola (filtro rigido / esplorazione con fallback). Le 4
combinazioni sono possibili in DB, ma in pratica la matrice utile è
v1+rigido (legacy puro, default) e v1+esplorativo (durante validazione
del refactor); v2 segue percorso suo.

Revision ID: b1c2d3e4f5a6
Revises: aa01b2c3d4e5 (0040)
Create Date: 2026-05-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "aa01b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "programma_materiale",
        sa.Column(
            "builder_mode",
            sa.String(20),
            nullable=False,
            server_default="rigido",
            comment=(
                "Sprint 8.1 MR-A1: logica di assegnazione corsa→regola. "
                "'rigido' (default, retrocompat) = filtra-e-scarta legacy. "
                "'esplorativo' = esplora-e-rilassa con vincoli soft pesati "
                "e fallback governato. Foundation flag: i consumatori che "
                "lo leggono arrivano in MR-A3+. Ortogonale a builder_version."
            ),
        ),
    )
    op.create_check_constraint(
        "programma_materiale_builder_mode_check",
        "programma_materiale",
        "builder_mode IN ('rigido', 'esplorativo')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "programma_materiale_builder_mode_check",
        "programma_materiale",
        type_="check",
    )
    op.drop_column("programma_materiale", "builder_mode")
