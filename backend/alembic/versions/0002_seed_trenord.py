"""0002 seed_trenord — popolamento iniziale dati Trenord

Riferimento: docs/SCHEMA-DATI-NATIVO.md §12.

Carica:
- §12.1 azienda Trenord (1 riga, con normativa_pdc_json)
- §12.2 7 località manutenzione (6 IMPMAN reali + 1 POOL_TILO esterno)
- §12.3 25 depot PdC (NORMATIVA-PDC §2.1)
- materiale_tipo: 69 codici unici da data/depositi_manutenzione_trenord_seed.json
- localita_manutenzione_dotazione: 84 righe (6 IMPMAN × N codici)

Note:
- POOL_TILO_SVIZZERA è creato senza dotazione (è un pool esterno TILO).
- NON_ASSEGNATO del seed JSON è escluso (placeholder applicativo, non
  una località reale).
- L'utente admin e gli altri ruoli sono rinviati a 0003_seed_users.py
  (Sprint 2, vedi PIANO-MVP.md).

Revision ID: 8cc5db6b9dcc
Revises: fea31638ebad
Create Date: 2026-04-25 19:32:37.114010+00:00

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8cc5db6b9dcc"
down_revision: str | None = "fea31638ebad"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# =====================================================================
# Dati statici (estratti da docs/SCHEMA-DATI-NATIVO.md §12 + seed JSON)
# =====================================================================

# §12.2 — 7 località manutenzione
# (codice, nome_canonico, is_pool_esterno, azienda_proprietaria_esterna)
LOCALITA_MANUTENZIONE: list[tuple[str, str, bool, str | None]] = [
    ("IMPMAN_MILANO_FIORENZA", "TRENORD IMPMAN MILANO FIORENZA", False, None),
    ("IMPMAN_NOVATE", "TRENORD IMPMAN NOVATE", False, None),
    ("IMPMAN_CAMNAGO", "TRENORD IMPMAN CAMNAGO", False, None),
    ("IMPMAN_LECCO", "TRENORD IMPMAN LECCO", False, None),
    ("IMPMAN_CREMONA", "TRENORD IMPMAN CREMONA", False, None),
    ("IMPMAN_ISEO", "TRENORD IMPMAN ISEO", False, None),
    ("POOL_TILO_SVIZZERA", "(Pool TILO - servizi Svizzera-Italia)", True, "TILO"),
]

# §12.3 — 25 depot PdC Trenord (NORMATIVA-PDC §2.1)
# (codice, display_name)
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

# 69 codici materiale_tipo unici, estratti da seed JSON (campo pezzi_totali
# di tutte le località eccetto NON_ASSEGNATO)
MATERIALE_CODES: list[str] = [
    "ALe245",
    "ALe426",
    "ALe506",
    "ALe710",
    "ALe711",
    "ALn668(1000)",
    "ATR115",
    "ATR125",
    "Ale760",
    "Ale761",
    "D520",
    "E464N",
    "Le245",
    "Le736",
    "Le990",
    "TN-A421-DM1",
    "TN-A421-DM2",
    "TN-A421-TA",
    "TN-A421-TB",
    "TN-A522-DM1",
    "TN-A522-DM2",
    "TN-A522-TA",
    "TN-A522-TB1",
    "TN-A522-TX",
    "TN-Ale103-A1",
    "TN-Ale103-A4",
    "TN-Ale104-A1",
    "TN-Ale104-A4",
    "TN-Ale204-A1",
    "TN-Ale204-A4",
    "TN-Ale421-DM1",
    "TN-Ale421-DM2",
    "TN-Ale425-A41",
    "TN-Ale425-A46",
    "TN-Ale521-DM1",
    "TN-Ale521-DM2",
    "TN-Ale522-DM1",
    "TN-Ale522-DM2",
    "TN-Ale526-A41",
    "TN-Ale526-A46",
    "TN-Aln803-A",
    "TN-Aln803-B",
    "TN-Le103-A2",
    "TN-Le104-A2",
    "TN-Le104-A3",
    "TN-Le204-A2",
    "TN-Le204-A3",
    "TN-Le421-TA",
    "TN-Le421-TB",
    "TN-Le421-TB1",
    "TN-Le425-A42-A45",
    "TN-Le425-A43",
    "TN-Le521-TA",
    "TN-Le521-TB",
    "TN-Le521-TX",
    "TN-Le522-TA",
    "TN-Le522-TB",
    "TN-Le522-TB1",
    "TN-Le522-TX",
    "TN-Le526-A43",
    "TN-Ln803-C",
    "TN-Ln803-PP",
    "nAAW",
    "nBBW",
    "nBC-clim",
    "npBBHW",
    "npBDCTE-clim",
    "npBDL",
    "npBDL-clim",
]

# 84 righe dotazione (località_codice, materiale_codice, quantità)
# Estratte da data/depositi_manutenzione_trenord_seed.json. POOL_TILO non
# ha dotazione (pool esterno).
DOTAZIONE: list[tuple[str, str, int]] = [
    ("IMPMAN_CAMNAGO", "ALe710", 56),
    ("IMPMAN_CAMNAGO", "ALe711", 28),
    ("IMPMAN_CAMNAGO", "TN-Ale522-DM1", 17),
    ("IMPMAN_CAMNAGO", "TN-Ale522-DM2", 17),
    ("IMPMAN_CAMNAGO", "TN-Le522-TA", 17),
    ("IMPMAN_CAMNAGO", "TN-Le522-TB", 17),
    ("IMPMAN_CAMNAGO", "TN-Le522-TX", 17),
    ("IMPMAN_CREMONA", "TN-Aln803-A", 23),
    ("IMPMAN_CREMONA", "TN-Aln803-B", 23),
    ("IMPMAN_CREMONA", "TN-Ln803-C", 23),
    ("IMPMAN_CREMONA", "TN-Ln803-PP", 23),
    ("IMPMAN_ISEO", "ALn668(1000)", 8),
    ("IMPMAN_ISEO", "ATR115", 4),
    ("IMPMAN_ISEO", "ATR125", 8),
    ("IMPMAN_ISEO", "D520", 1),
    ("IMPMAN_LECCO", "ATR115", 4),
    ("IMPMAN_LECCO", "ATR125", 9),
    ("IMPMAN_LECCO", "TN-Ale204-A1", 11),
    ("IMPMAN_LECCO", "TN-Ale204-A4", 11),
    ("IMPMAN_LECCO", "TN-Le204-A2", 11),
    ("IMPMAN_LECCO", "TN-Le204-A3", 11),
    ("IMPMAN_MILANO_FIORENZA", "ALe710", 74),
    ("IMPMAN_MILANO_FIORENZA", "ALe711", 64),
    ("IMPMAN_MILANO_FIORENZA", "E464N", 22),
    ("IMPMAN_MILANO_FIORENZA", "TN-A421-DM1", 15),
    ("IMPMAN_MILANO_FIORENZA", "TN-A421-DM2", 15),
    ("IMPMAN_MILANO_FIORENZA", "TN-A421-TA", 15),
    ("IMPMAN_MILANO_FIORENZA", "TN-A421-TB", 15),
    ("IMPMAN_MILANO_FIORENZA", "TN-A522-DM1", 7),
    ("IMPMAN_MILANO_FIORENZA", "TN-A522-DM2", 7),
    ("IMPMAN_MILANO_FIORENZA", "TN-A522-TA", 7),
    ("IMPMAN_MILANO_FIORENZA", "TN-A522-TB1", 7),
    ("IMPMAN_MILANO_FIORENZA", "TN-A522-TX", 7),
    ("IMPMAN_MILANO_FIORENZA", "TN-Ale103-A1", 2),
    ("IMPMAN_MILANO_FIORENZA", "TN-Ale103-A4", 2),
    ("IMPMAN_MILANO_FIORENZA", "TN-Ale104-A1", 5),
    ("IMPMAN_MILANO_FIORENZA", "TN-Ale104-A4", 5),
    ("IMPMAN_MILANO_FIORENZA", "TN-Ale204-A1", 48),
    ("IMPMAN_MILANO_FIORENZA", "TN-Ale204-A4", 48),
    ("IMPMAN_MILANO_FIORENZA", "TN-Ale421-DM1", 34),
    ("IMPMAN_MILANO_FIORENZA", "TN-Ale421-DM2", 34),
    ("IMPMAN_MILANO_FIORENZA", "TN-Ale521-DM1", 4),
    ("IMPMAN_MILANO_FIORENZA", "TN-Ale521-DM2", 4),
    ("IMPMAN_MILANO_FIORENZA", "TN-Ale522-DM1", 36),
    ("IMPMAN_MILANO_FIORENZA", "TN-Ale522-DM2", 36),
    ("IMPMAN_MILANO_FIORENZA", "TN-Ale526-A41", 9),
    ("IMPMAN_MILANO_FIORENZA", "TN-Ale526-A46", 9),
    ("IMPMAN_MILANO_FIORENZA", "TN-Le103-A2", 2),
    ("IMPMAN_MILANO_FIORENZA", "TN-Le104-A2", 5),
    ("IMPMAN_MILANO_FIORENZA", "TN-Le104-A3", 5),
    ("IMPMAN_MILANO_FIORENZA", "TN-Le204-A2", 48),
    ("IMPMAN_MILANO_FIORENZA", "TN-Le204-A3", 48),
    ("IMPMAN_MILANO_FIORENZA", "TN-Le421-TA", 34),
    ("IMPMAN_MILANO_FIORENZA", "TN-Le421-TB", 18),
    ("IMPMAN_MILANO_FIORENZA", "TN-Le421-TB1", 16),
    ("IMPMAN_MILANO_FIORENZA", "TN-Le521-TA", 4),
    ("IMPMAN_MILANO_FIORENZA", "TN-Le521-TB", 4),
    ("IMPMAN_MILANO_FIORENZA", "TN-Le521-TX", 4),
    ("IMPMAN_MILANO_FIORENZA", "TN-Le522-TA", 36),
    ("IMPMAN_MILANO_FIORENZA", "TN-Le522-TB", 24),
    ("IMPMAN_MILANO_FIORENZA", "TN-Le522-TB1", 12),
    ("IMPMAN_MILANO_FIORENZA", "TN-Le522-TX", 36),
    ("IMPMAN_MILANO_FIORENZA", "TN-Le526-A43", 9),
    ("IMPMAN_MILANO_FIORENZA", "nAAW", 13),
    ("IMPMAN_MILANO_FIORENZA", "nBBW", 52),
    ("IMPMAN_MILANO_FIORENZA", "nBC-clim", 51),
    ("IMPMAN_MILANO_FIORENZA", "npBBHW", 13),
    ("IMPMAN_MILANO_FIORENZA", "npBDCTE-clim", 3),
    ("IMPMAN_MILANO_FIORENZA", "npBDL", 2),
    ("IMPMAN_MILANO_FIORENZA", "npBDL-clim", 4),
    ("IMPMAN_NOVATE", "ALe245", 20),
    ("IMPMAN_NOVATE", "ALe426", 7),
    ("IMPMAN_NOVATE", "ALe506", 7),
    ("IMPMAN_NOVATE", "ALe710", 53),
    ("IMPMAN_NOVATE", "ALe711", 58),
    ("IMPMAN_NOVATE", "Ale760", 10),
    ("IMPMAN_NOVATE", "Ale761", 10),
    ("IMPMAN_NOVATE", "Le245", 30),
    ("IMPMAN_NOVATE", "Le736", 14),
    ("IMPMAN_NOVATE", "Le990", 20),
    ("IMPMAN_NOVATE", "TN-Ale425-A41", 14),
    ("IMPMAN_NOVATE", "TN-Ale425-A46", 14),
    ("IMPMAN_NOVATE", "TN-Le425-A42-A45", 28),
    ("IMPMAN_NOVATE", "TN-Le425-A43", 14),
]


# =====================================================================
# Helper SQL — costruzione VALUES list da liste Python
# =====================================================================


def _sql_str(s: str | None) -> str:
    if s is None:
        return "NULL"
    return "'" + s.replace("'", "''") + "'"


def _sql_bool(b: bool) -> str:
    return "TRUE" if b else "FALSE"


# =====================================================================
# upgrade / downgrade
# =====================================================================


def upgrade() -> None:
    # -----------------------------------------------------------------
    # §12.1 — azienda Trenord (con normativa_pdc_json)
    # -----------------------------------------------------------------
    op.execute("""
        INSERT INTO azienda (codice, nome, normativa_pdc_json) VALUES (
          'trenord',
          'Trenord SRL',
          '{
            "max_prestazione_min_standard": 510,
            "max_prestazione_min_notte": 420,
            "cap_7h_window_start_min": 60,
            "cap_7h_window_end_min": 299,
            "max_condotta_min": 330,
            "refez_required_above_min": 360,
            "refez_min_duration": 30,
            "meal_window_1": [690, 930],
            "meal_window_2": [1110, 1350],
            "accp_standard_min": 40,
            "acca_standard_min": 40,
            "accp_preriscaldo_min": 80,
            "fr_max_per_settimana": 1,
            "fr_max_per_28_giorni": 3,
            "riposo_settimanale_min_h": 62
          }'::jsonb
        )
    """)

    # -----------------------------------------------------------------
    # §12.2 — 7 località manutenzione
    # -----------------------------------------------------------------
    loc_values = ",\n          ".join(
        f"({_sql_str(c)}, {_sql_str(n)}, {_sql_bool(p)}, {_sql_str(a)})"
        for c, n, p, a in LOCALITA_MANUTENZIONE
    )
    op.execute(f"""
        INSERT INTO localita_manutenzione
          (codice, nome_canonico, azienda_id, is_pool_esterno, azienda_proprietaria_esterna)
        SELECT v.codice, v.nome_canonico, a.id, v.is_pool_esterno, v.azienda_proprietaria_esterna
        FROM (VALUES
          {loc_values}
        ) AS v(codice, nome_canonico, is_pool_esterno, azienda_proprietaria_esterna)
        CROSS JOIN azienda a WHERE a.codice = 'trenord'
    """)

    # -----------------------------------------------------------------
    # §12.3 — 25 depot PdC
    # -----------------------------------------------------------------
    depot_values = ",\n          ".join(
        f"({_sql_str(c)}, {_sql_str(n)})" for c, n in DEPOT_TRENORD
    )
    op.execute(f"""
        INSERT INTO depot (codice, display_name, azienda_id, tipi_personale_ammessi)
        SELECT v.codice, v.display_name, a.id, 'PdC'
        FROM (VALUES
          {depot_values}
        ) AS v(codice, display_name)
        CROSS JOIN azienda a WHERE a.codice = 'trenord'
    """)

    # -----------------------------------------------------------------
    # materiale_tipo — 69 codici unici dal seed JSON
    # -----------------------------------------------------------------
    mat_values = ",\n          ".join(f"({_sql_str(c)})" for c in MATERIALE_CODES)
    op.execute(f"""
        INSERT INTO materiale_tipo (codice, azienda_id)
        SELECT v.codice, a.id
        FROM (VALUES
          {mat_values}
        ) AS v(codice)
        CROSS JOIN azienda a WHERE a.codice = 'trenord'
    """)

    # -----------------------------------------------------------------
    # localita_manutenzione_dotazione — 84 righe dal seed JSON
    # -----------------------------------------------------------------
    dot_values = ",\n          ".join(
        f"({_sql_str(loc)}, {_sql_str(mat)}, {qty})" for loc, mat, qty in DOTAZIONE
    )
    op.execute(f"""
        INSERT INTO localita_manutenzione_dotazione
          (localita_manutenzione_id, materiale_tipo_codice, quantita)
        SELECT lm.id, v.materiale_codice, v.quantita
        FROM (VALUES
          {dot_values}
        ) AS v(loc_codice, materiale_codice, quantita)
        JOIN localita_manutenzione lm ON lm.codice = v.loc_codice
    """)


def downgrade() -> None:
    # Inverso: prima i FK-figli, poi i padri. Tutto filtrato per
    # azienda_id Trenord per non toccare seed di altre aziende future.
    azienda_subquery = "(SELECT id FROM azienda WHERE codice = 'trenord')"

    op.execute(f"""
        DELETE FROM localita_manutenzione_dotazione
        WHERE localita_manutenzione_id IN (
            SELECT id FROM localita_manutenzione
            WHERE azienda_id = {azienda_subquery}
        )
    """)
    op.execute(f"""
        DELETE FROM materiale_tipo
        WHERE azienda_id = {azienda_subquery}
    """)
    op.execute(f"""
        DELETE FROM depot
        WHERE azienda_id = {azienda_subquery}
    """)
    op.execute(f"""
        DELETE FROM localita_manutenzione
        WHERE azienda_id = {azienda_subquery}
    """)
    op.execute("DELETE FROM azienda WHERE codice = 'trenord'")
