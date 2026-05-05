"""Sprint 7.10 MR α.1 — popola stazione_principale_codice sui depositi PdC.

Senza una stazione di residenza per ogni deposito, l'algoritmo CV
(``lista_stazioni_cv_ammesse`` in ``builder_pdc/split_cv.py``) non sa
dove ammettere uno scambio PdC, e il builder MVP non può segmentare
correttamente i giri lunghi: vedi screenshot smoke 2026-05-05 dove il
turno PdC per ETR421-6g ha 124h53 di prestazione totale e 6/6
giornate fuori cap, perché lo split CV non trova alcun punto valido.

Mapping pattern-based via ILIKE: per ogni deposito noto cerco la
stazione con nome più simile (preferendo i match più corti). Se la
stazione non esiste nel DB il deposito resta con NULL e la migration
non fallisce — idempotente, safe da rieseguire.

Riferimenti:
- ``NORMATIVA-PDC.md §2.1`` per la lista 25 depositi standard.
- ``alembic/0028_seed_depots_per_azienda.DEPOT_TRENORD`` per i codici.
- Memoria utente: FIORENZA → MILANO CERTOSA (vecchia decisione MR2
  per stazione_collegata_codice di ``IMPMAN_MILANO_FIORENZA``).
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8e9f0a1b2c3"
down_revision: str | None = "b7c8d9e0f1a2"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


# Mapping deposito_codice → pattern ILIKE per il nome stazione.
# Formato: (codice_depot, pattern_ilike). Pattern PostgreSQL: ILIKE
# è case-insensitive e i `%` sono wildcard. Quando ci sono più match
# preferiamo il NOME PIÙ CORTO (così "MILANO P. GARIBALDI" vince su
# "MILANO PORTA GARIBALDI SOTTERRANEA").
DEPOT_TO_STAZIONE_PATTERN: list[tuple[str, str]] = [
    ("ALESSANDRIA", "%ALESSANDRIA%"),
    ("ARONA", "%ARONA%"),
    ("BERGAMO", "%BERGAMO%"),
    ("BRESCIA", "%BRESCIA%"),
    ("COLICO", "%COLICO%"),
    # COMO: preferiamo "Como S. Giovanni" su "Como Lago" via ORDER BY
    # length asc (sono entrambe corte, ma S.G. è la principale RFI).
    ("COMO", "%COMO%"),
    ("CREMONA", "%CREMONA%"),
    ("DOMODOSSOLA", "%DOMODOSSOLA%"),
    # FIORENZA è un deposito MATERIALE, non commerciale: la sua
    # stazione di superficie è MILANO CERTOSA (vecchia decisione MR2,
    # vedi memoria utente). Quando la stazione non esiste nel DB il
    # deposito resta NULL → fallback al non-CV per quella sede.
    ("FIORENZA", "%CERTOSA%"),
    ("GALLARATE", "%GALLARATE%"),
    # I tre depositi GARIBALDI puntano tutti alla stessa stazione
    # commerciale (le sigle ALE/Cadetti/TE sono sub-aree fisiche).
    ("GARIBALDI_ALE", "%GARIBALDI%"),
    ("GARIBALDI_CADETTI", "%GARIBALDI%"),
    ("GARIBALDI_TE", "%GARIBALDI%"),
    # GRECO PIRELLI: stessa logica per le due sub-aree TE/S9.
    ("GRECO_TE", "%GRECO%PIRELLI%"),
    ("GRECO_S9", "%GRECO%PIRELLI%"),
    ("LECCO", "%LECCO%"),
    ("LUINO", "%LUINO%"),
    ("MANTOVA", "%MANTOVA%"),
    # MORTARA è anche deroga CV hardcoded — popolarla qui rinforza
    # la cosa: diventa CV via depot OR deroga (entrambe le strade).
    ("MORTARA", "%MORTARA%"),
    ("PAVIA", "%PAVIA%"),
    ("PIACENZA", "%PIACENZA%"),
    ("SONDRIO", "%SONDRIO%"),
    ("TREVIGLIO", "%TREVIGLIO%"),
    # VERONA P.N. è il nome canonico (Porta Nuova). Match permissivo.
    ("VERONA", "%VERONA%"),
    ("VOGHERA", "%VOGHERA%"),
]


def _sql_str(s: str) -> str:
    """Escape singoli apici per inserimento literal in SQL."""
    return "'" + s.replace("'", "''") + "'"


def upgrade() -> None:
    """Per ogni deposito noto, prova a popolare stazione_principale_codice
    cercando la stazione con nome che matcha il pattern.

    Multi-azienda safe: aggiorna TUTTI i depositi con quel codice in
    QUALSIASI azienda, ma solo se ``stazione_principale_codice`` è
    attualmente NULL. Idempotente.

    Se una stazione non esiste nel DB di quell'azienda, l'UPDATE non
    cambia nulla per quel depot — resta NULL, comportamento safe.
    """
    for codice, pattern in DEPOT_TO_STAZIONE_PATTERN:
        op.execute(f"""
            UPDATE depot
            SET stazione_principale_codice = (
                SELECT s.codice FROM stazione s
                WHERE s.nome ILIKE {_sql_str(pattern)}
                ORDER BY LENGTH(s.nome) ASC
                LIMIT 1
            )
            WHERE codice = {_sql_str(codice)}
              AND stazione_principale_codice IS NULL
              AND EXISTS (
                  SELECT 1 FROM stazione s
                  WHERE s.nome ILIKE {_sql_str(pattern)}
              )
        """)


def downgrade() -> None:
    """Reset a NULL i campi popolati da questa migration.

    NB: rimuove anche eventuali popolazioni manuali avvenute dopo —
    ma per i depositi MR α.1 lo scope era proprio la popolazione
    bulk, quindi è coerente.
    """
    codici = ", ".join(_sql_str(c) for c, _ in DEPOT_TO_STAZIONE_PATTERN)
    op.execute(f"""
        UPDATE depot
        SET stazione_principale_codice = NULL
        WHERE codice IN ({codici})
    """)
