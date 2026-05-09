"""0045 — turno_pdc_blocco.tipo_evento check constraint estesa con
MM e VOCTAXI (Sprint 8.2 MR-PD5 fix critico).

Bug rilevato dal test integration smoke MR-PD-FIX-SEVERO 2 (S5):
``builder_strategy=deposito_first`` invoca il vettura_resolver §7.2
che produce blocchi ``MM`` o ``VOCTAXI`` come fallback di rientro al
deposito. Il check constraint pre-esistente
``turno_pdc_blocco_tipo_check`` accettava solo i 12 tipi MVP
(CONDOTTA, VETTURA, REFEZ, ACCp, ACCa, CVp, CVa, PK, SCOMP, PRESA,
FINE, DORMITA) — l'INSERT con tipo MM o VOCTAXI sollevava
``IntegrityError(CheckViolation)`` IN PRODUZIONE.

Bug latente da MR-PD2 (entry 262) che ha aggiornato i tipi TS
frontend + costanti backend ma **dimenticato** di aggiornare il
check constraint DB. MR-PD3b builder + MR-PD5 endpoint funzionavano
in unit test (mock) ma falliscono al primo INSERT reale.

Operazioni:
1. DROP CONSTRAINT ``turno_pdc_blocco_tipo_check``
2. ADD CONSTRAINT estesa con 14 tipi: 12 originali + ``MM`` + ``VOCTAXI``

Rollback: ripristina la lista 12-tipi.

Revision ID: a6b7c8d9e0f1
Revises: f4a5b6c7d8e9
Create Date: 2026-05-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a6b7c8d9e0f1"
down_revision: str | None = "f4a5b6c7d8e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TIPI_ESTESI = (
    "'CONDOTTA', 'VETTURA', 'REFEZ', 'ACCp', 'ACCa', "
    "'CVp', 'CVa', 'PK', 'SCOMP', 'PRESA', 'FINE', "
    "'DORMITA', 'MM', 'VOCTAXI'"
)
_TIPI_ORIGINALI = (
    "'CONDOTTA', 'VETTURA', 'REFEZ', 'ACCp', 'ACCa', "
    "'CVp', 'CVa', 'PK', 'SCOMP', 'PRESA', 'FINE', 'DORMITA'"
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE turno_pdc_blocco DROP CONSTRAINT IF EXISTS "
        "turno_pdc_blocco_tipo_check"
    )
    op.execute(
        "ALTER TABLE turno_pdc_blocco ADD CONSTRAINT "
        "turno_pdc_blocco_tipo_check CHECK "
        f"(tipo_evento IN ({_TIPI_ESTESI}))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE turno_pdc_blocco DROP CONSTRAINT IF EXISTS "
        "turno_pdc_blocco_tipo_check"
    )
    op.execute(
        "ALTER TABLE turno_pdc_blocco ADD CONSTRAINT "
        "turno_pdc_blocco_tipo_check CHECK "
        f"(tipo_evento IN ({_TIPI_ORIGINALI}))"
    )
