"""0028 — popola i 25 depositi PdC Trenord anche per le aziende non-Trenord.

Sprint 7.9 MR ε (entry TN-UPDATE 147).

Il seed `0002_seed_trenord` (e il fix `0026_repair_depots_persone`)
popolano i 25 depositi PdC solo per `azienda.codice = 'trenord'`
(azienda_id=1). Le altre aziende (es. quelle create per testing
multi-tenant come "azienda #2") restano senza depositi → la pagina
`/gestione-personale/depositi` mostra "Nessun deposito PdC".

Decisione utente 2026-05-05 ("popoliamo i depositi nella sezione
PdC"): popolare i 25 depositi anche per le aziende non-Trenord che
ne sono prive.

Migration **idempotente**: per ogni azienda non-Trenord, inserisce
solo i depositi mancanti (NOT EXISTS). Sicuro da rieseguire e da
applicare in produzione senza dati persi.

⚠️ Sui depositi non viene popolata `stazione_principale_codice`
(richiede mappa `(deposito_codice, stazione_codice)` consensuale per
tutte le aziende e dipende dalla rete RFI/aziendale specifica). Resta
NULL: il frontend (`GestionePersonaleDepositiRoute`) gestisce già il
caso. La popolazione mirata della stazione_principale per azienda
specifica resta scope futuro.

Revision ID: c3d4e5f6a7b8
Revises: a8b9c0d1e2f3 (0026_repair_depots_persone)
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "a8b9c0d1e2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Lista depositi Trenord — duplicato dal seed `0002_seed_trenord.py`
# (NORMATIVA-PDC §2.1). Il duplicato è intenzionale: le migration
# Alembic devono essere immutabili nel tempo, quindi non si importa
# da costanti esterne che potrebbero cambiare.
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


def _sql_str(s: str) -> str:
    """Escape singoli apici per inserimento literal in SQL VALUES."""
    return "'" + s.replace("'", "''") + "'"


def upgrade() -> None:
    depot_values = ",\n          ".join(
        f"({_sql_str(c)}, {_sql_str(n)})" for c, n in DEPOT_TRENORD
    )
    # Per ogni azienda diversa da 'trenord', inserisci i depositi che
    # NON esistono già (NOT EXISTS sul codice). Idempotente.
    op.execute(f"""
        INSERT INTO depot (codice, display_name, azienda_id, tipi_personale_ammessi, is_attivo)
        SELECT v.codice, v.display_name, a.id, 'PdC', TRUE
        FROM (VALUES
          {depot_values}
        ) AS v(codice, display_name)
        CROSS JOIN azienda a
        WHERE a.codice <> 'trenord'
          AND NOT EXISTS (
            SELECT 1 FROM depot d
            WHERE d.azienda_id = a.id AND d.codice = v.codice
          )
    """)


def downgrade() -> None:
    # Rimuove i depositi inseriti da QUESTA migration: solo quelli
    # delle aziende non-Trenord che hanno esattamente i 25 codici Trenord.
    # Filtro per azienda_id <> azienda Trenord per non toccare il seed
    # originale.
    codici = ", ".join(_sql_str(c) for c, _ in DEPOT_TRENORD)
    op.execute(f"""
        DELETE FROM depot
        WHERE codice IN ({codici})
          AND azienda_id <> (SELECT id FROM azienda WHERE codice = 'trenord')
    """)
