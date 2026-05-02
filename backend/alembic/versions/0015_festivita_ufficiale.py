"""0015 — Calendario ufficiale festività italiane (Sprint 7.7 MR 2)

Crea la tabella ``festivita_ufficiale`` + popola con:

- **10 festività nazionali fisse** italiane × **anni 2025-2030**
  (Capodanno, Epifania, Liberazione, Lavoro, Repubblica, Ferragosto,
  Ognissanti, Immacolata, Natale, Santo Stefano).
- **Pasqua + Pasquetta** calcolate via algoritmo gregoriano per
  ogni anno 2025-2030.
- **Sant'Ambrogio** (7/12) come festività locale per Trenord
  (azienda_id = trenord) — patrono di Milano.

Decisione utente 2026-05-02 (memoria
``project_refactor_varianti_giri_separati_TODO.md``): il calendario
è prerequisito per il refactor "varianti → giri separati con
etichette parlanti" (Sprint 7.7.3).

Idempotente: ``ON CONFLICT DO NOTHING`` su ``(azienda_id, data, nome)``
via index parziale UNIQUE.
"""

from __future__ import annotations

from datetime import date

import sqlalchemy as sa
from alembic import op

revision: str = "e3b9a046f218"
down_revision: str | None = "d2a8f17bc94e"  # 0014_km_max_ciclo_per_regola
branch_labels = None
depends_on = None


# Algoritmo Pasqua gregoriana (duplicato dall'helper domain perché le
# migration alembic non possono importare app code).
def _pasqua(anno: int) -> date:
    a = anno % 19
    b = anno // 100
    c = anno % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    L = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * L) // 451
    mese = (h + L - 7 * m + 114) // 31
    giorno = ((h + L - 7 * m + 114) % 31) + 1
    return date(anno, mese, giorno)


_FESTIVITA_FISSE = [
    (1, 1, "Capodanno"),
    (6, 1, "Epifania"),
    (25, 4, "Festa della Liberazione"),
    (1, 5, "Festa del Lavoro"),
    (2, 6, "Festa della Repubblica"),
    (15, 8, "Ferragosto"),
    (1, 11, "Ognissanti"),
    (8, 12, "Immacolata Concezione"),
    (25, 12, "Natale"),
    (26, 12, "Santo Stefano"),
]

_ANNI_SEED = range(2025, 2031)  # 2025 incl., 2031 excl.


def upgrade() -> None:
    # ----------------------------------------------------------------
    # Tabella
    # ----------------------------------------------------------------
    op.create_table(
        "festivita_ufficiale",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "azienda_id",
            sa.BigInteger,
            sa.ForeignKey("azienda.id", ondelete="CASCADE"),
            nullable=True,
            comment="NULL = festività nazionale universale",
        ),
        sa.Column("data", sa.Date, nullable=False),
        sa.Column("nome", sa.Text, nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False, server_default="nazionale"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_festivita_data",
        "festivita_ufficiale",
        ["data"],
    )
    # Index UNIQUE parziali per gestire NULL di azienda_id (Postgres):
    # 1 indice per festività nazionali (azienda_id IS NULL)
    # 1 indice per festività azienda-specifiche (azienda_id IS NOT NULL)
    op.create_index(
        "idx_festivita_nazionale_data_nome_uq",
        "festivita_ufficiale",
        ["data", "nome"],
        unique=True,
        postgresql_where=sa.text("azienda_id IS NULL"),
    )
    op.create_index(
        "idx_festivita_azienda_data_nome_uq",
        "festivita_ufficiale",
        ["azienda_id", "data", "nome"],
        unique=True,
        postgresql_where=sa.text("azienda_id IS NOT NULL"),
    )

    # ----------------------------------------------------------------
    # Seed festività nazionali (azienda_id NULL) per 6 anni
    # ----------------------------------------------------------------
    rows: list[tuple[date, str, str]] = []  # (data, nome, tipo)
    for anno in _ANNI_SEED:
        # Fisse
        for giorno, mese, nome in _FESTIVITA_FISSE:
            tipo = (
                "religiosa"
                if nome
                in ("Epifania", "Immacolata Concezione", "Natale", "Santo Stefano", "Ognissanti")
                else "nazionale"
            )
            rows.append((date(anno, mese, giorno), nome, tipo))
        # Mobili (Pasqua + Pasquetta)
        p = _pasqua(anno)
        rows.append((p, "Pasqua", "religiosa"))
        rows.append((date.fromordinal(p.toordinal() + 1), "Lunedì dell'Angelo", "religiosa"))

    values_sql = ",\n          ".join(
        f"('{d.isoformat()}', $tag${nome}$tag$, '{tipo}')" for d, nome, tipo in rows
    )
    op.execute(
        f"""
        INSERT INTO festivita_ufficiale (azienda_id, data, nome, tipo)
        SELECT NULL, v.data::date, v.nome, v.tipo
        FROM (VALUES
          {values_sql}
        ) AS v(data, nome, tipo)
        ON CONFLICT DO NOTHING
        """  # noqa: S608 — pattern hardcoded, no user input
    )

    # ----------------------------------------------------------------
    # Seed festività locale Trenord — Sant'Ambrogio (7/12)
    # ----------------------------------------------------------------
    sant_ambrogio_values = ",\n          ".join(
        f"('{date(anno, 12, 7).isoformat()}')" for anno in _ANNI_SEED
    )
    op.execute(
        f"""
        INSERT INTO festivita_ufficiale (azienda_id, data, nome, tipo)
        SELECT a.id, v.data::date, $tag$Sant'Ambrogio$tag$, 'patronale'
        FROM (VALUES
          {sant_ambrogio_values}
        ) AS v(data)
        CROSS JOIN azienda a WHERE a.codice = 'trenord'
        ON CONFLICT DO NOTHING
        """  # noqa: S608
    )


def downgrade() -> None:
    op.drop_index("idx_festivita_azienda_data_nome_uq", table_name="festivita_ufficiale")
    op.drop_index("idx_festivita_nazionale_data_nome_uq", table_name="festivita_ufficiale")
    op.drop_index("idx_festivita_data", table_name="festivita_ufficiale")
    op.drop_table("festivita_ufficiale")
