"""0026 — repair seed depots + persona.sede_residenza_id (Sprint 7.9 MR ζ-fix).

In produzione la migration 0002_seed_trenord non aveva popolato i 25
depositi PdC nell'azienda 'trenord' (motivo non chiaro: forse il seed
era diverso al momento dell'apply iniziale, oppure i depositi erano
stati cancellati manualmente). Risultato: la 0025 ha inserito le 75
persone con `sede_residenza_id = NULL` (la subquery
`(SELECT id FROM depot WHERE codice = X)` tornava NULL).

Sintomi osservati in prod (entry 145 smoke):
- `/api/depots` → ``[]`` (nessun depot per l'azienda dell'admin)
- `/api/persone` → 75 elementi tutti con ``depot_codice: null``
- Calendario e Depositi sotto Gestione Personale risultano vuoti.

Questa migration è idempotente:
1. Insert 25 depots mancanti su azienda 'trenord' (`ON CONFLICT (codice)
   DO NOTHING` — non tocca depots già esistenti).
2. UPDATE delle 75 persone seed dove `sede_residenza_id IS NULL`,
   ricostruendo il mapping originale dai codici dipendente.

`downgrade()` è no-op (non vogliamo togliere depositi o spezzare
sede_residenza_id) — sicurezza.

Revision ID: a8b9c0d1e2f3
Revises: f1a2b3c4d5e6 (0025_seed_persone)
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8b9c0d1e2f3"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Stessa lista (codice, display_name) di 0002_seed_trenord §12.3.
DEPOT_TRENORD: list[tuple[str, str]] = [
    ("ALESSANDRIA", "Alessandria"),
    ("ARONA", "Arona"),
    ("BERGAMO", "Bergamo"),
    ("BRESCIA", "Brescia"),
    ("COLICO", "Colico"),
    ("COMO", "Como"),
    ("CREMONA", "Cremona"),
    ("DOMODOSSOLA", "Domodossola"),
    ("FIORENZA", "Fiorenza"),
    ("GALLARATE", "Gallarate"),
    ("GARIBALDI_ALE", "Milano P. Garibaldi (ALE)"),
    ("GARIBALDI_CADETTI", "Milano P. Garibaldi (Cadetti)"),
    ("GARIBALDI_TE", "Milano P. Garibaldi (TE)"),
    ("GRECO_TE", "Milano Greco Pirelli (TE)"),
    ("GRECO_S9", "Milano Greco Pirelli (S9)"),
    ("LECCO", "Lecco"),
    ("LUINO", "Luino"),
    ("MANTOVA", "Mantova"),
    ("MORTARA", "Mortara"),
    ("PAVIA", "Pavia"),
    ("PIACENZA", "Piacenza"),
    ("SONDRIO", "Sondrio"),
    ("TREVIGLIO", "Treviglio"),
    ("VERONA", "Verona"),
    ("VOGHERA", "Voghera"),
]

# Mapping `codice_dipendente → codice_depot` per ricostruire
# `sede_residenza_id` delle 75 persone seed.
PERSONA_DEPOT_MAP: list[tuple[str, str]] = [
    ("100101", "ALESSANDRIA"),
    ("100102", "ALESSANDRIA"),
    ("100103", "ALESSANDRIA"),
    ("100201", "ARONA"),
    ("100202", "ARONA"),
    ("100203", "ARONA"),
    ("100301", "BERGAMO"),
    ("100302", "BERGAMO"),
    ("100303", "BERGAMO"),
    ("100401", "BRESCIA"),
    ("100402", "BRESCIA"),
    ("100403", "BRESCIA"),
    ("100501", "COLICO"),
    ("100502", "COLICO"),
    ("100503", "COLICO"),
    ("100601", "COMO"),
    ("100602", "COMO"),
    ("100603", "COMO"),
    ("100701", "CREMONA"),
    ("100702", "CREMONA"),
    ("100703", "CREMONA"),
    ("100801", "DOMODOSSOLA"),
    ("100802", "DOMODOSSOLA"),
    ("100803", "DOMODOSSOLA"),
    ("100901", "FIORENZA"),
    ("100902", "FIORENZA"),
    ("100903", "FIORENZA"),
    ("101001", "GALLARATE"),
    ("101002", "GALLARATE"),
    ("101003", "GALLARATE"),
    ("101101", "GARIBALDI_ALE"),
    ("101102", "GARIBALDI_ALE"),
    ("101103", "GARIBALDI_ALE"),
    ("101201", "GARIBALDI_CADETTI"),
    ("101202", "GARIBALDI_CADETTI"),
    ("101203", "GARIBALDI_CADETTI"),
    ("101301", "GARIBALDI_TE"),
    ("101302", "GARIBALDI_TE"),
    ("101303", "GARIBALDI_TE"),
    ("101401", "GRECO_TE"),
    ("101402", "GRECO_TE"),
    ("101403", "GRECO_TE"),
    ("101501", "GRECO_S9"),
    ("101502", "GRECO_S9"),
    ("101503", "GRECO_S9"),
    ("101601", "LECCO"),
    ("101602", "LECCO"),
    ("101603", "LECCO"),
    ("101701", "LUINO"),
    ("101702", "LUINO"),
    ("101703", "LUINO"),
    ("101801", "MANTOVA"),
    ("101802", "MANTOVA"),
    ("101803", "MANTOVA"),
    ("101901", "MORTARA"),
    ("101902", "MORTARA"),
    ("101903", "MORTARA"),
    ("102001", "PAVIA"),
    ("102002", "PAVIA"),
    ("102003", "PAVIA"),
    ("102101", "PIACENZA"),
    ("102102", "PIACENZA"),
    ("102103", "PIACENZA"),
    ("102201", "SONDRIO"),
    ("102202", "SONDRIO"),
    ("102203", "SONDRIO"),
    ("102301", "TREVIGLIO"),
    ("102302", "TREVIGLIO"),
    ("102303", "TREVIGLIO"),
    ("102401", "VERONA"),
    ("102402", "VERONA"),
    ("102403", "VERONA"),
    ("102501", "VOGHERA"),
    ("102502", "VOGHERA"),
    ("102503", "VOGHERA"),
]


def _esc(s: str) -> str:
    return s.replace("'", "''")


def upgrade() -> None:
    azienda_subq = "(SELECT id FROM azienda WHERE codice = 'trenord')"

    # ── Step 1: re-INSERT 25 depots (idempotente) ──────────────────
    depot_values = ",\n          ".join(
        f"('{_esc(c)}', '{_esc(n)}')" for c, n in DEPOT_TRENORD
    )
    op.execute(f"""
        INSERT INTO depot (codice, display_name, azienda_id, tipi_personale_ammessi)
        SELECT v.codice, v.display_name, {azienda_subq}, 'PdC'
        FROM (VALUES
          {depot_values}
        ) AS v(codice, display_name)
        ON CONFLICT (codice) DO NOTHING
    """)

    # ── Step 2: UPDATE persona.sede_residenza_id dove NULL ─────────
    map_values = ",\n          ".join(
        f"('{_esc(cod)}', '{_esc(depot)}')" for cod, depot in PERSONA_DEPOT_MAP
    )
    op.execute(f"""
        UPDATE persona p
        SET sede_residenza_id = d.id
        FROM (VALUES
          {map_values}
        ) AS m(codice_dipendente, codice_depot)
        JOIN depot d ON d.codice = m.codice_depot
        WHERE p.codice_dipendente = m.codice_dipendente
          AND p.azienda_id = {azienda_subq}
          AND p.sede_residenza_id IS NULL
    """)


def downgrade() -> None:
    """No-op: questa è una migration di REPAIR. Non vogliamo cancellare
    depositi o spezzare i link persona→deposito."""
    pass
