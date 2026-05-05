"""0025 — seed 75 personaggi italiani famosi come PdC + indisponibilità.

Sprint 7.9 MR ζ (Gestione Personale dashboard).

Distribuisce 75 personaggi italiani famosi (poeti, scienziati, artisti,
musicisti, storici, esploratori) come PdC sui 25 depositi PdC Trenord,
3 per deposito. Quando possibile, l'assegnazione segue un'affinità
geografica/storica (Manzoni → LECCO, Stradivari → CREMONA, Donizetti
→ BERGAMO, Volta → COMO, Virgilio → MANTOVA, ecc.); altrove la
distribuzione è arbitraria.

Aggiunge inoltre una decina di indisponibilità (ferie, malattia, ROL,
formazione) attorno alla data di apply per popolare i KPI dashboard
con valori non zero.

⚠️ Seed di **dimostrazione/UX**, non dati reali Trenord. Visibile solo
in ambiente con azienda 'trenord'. Idempotente: la `downgrade()`
elimina solo le persone con i 75 codici dipendente noti.

Revision ID: f1a2b3c4d5e6
Revises: e9a3f2c81d4b (0024_materiale_thread)
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "e9a3f2c81d4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ──────────────────────────────────────────────────────────────────
# Anagrafica seed: 75 persone (3 per deposito × 25 depositi PdC).
# Tuple: (codice_dipendente, nome, cognome, depot_codice, anno_assunzione)
# ──────────────────────────────────────────────────────────────────
PERSONE_SEED: list[tuple[str, str, str, str, int]] = [
    # ALESSANDRIA (Piemonte) — Eco/Pavese (vicini)/Alfieri (Asti)
    ("100101", "Umberto", "Eco", "ALESSANDRIA", 1995),
    ("100102", "Cesare", "Pavese", "ALESSANDRIA", 2003),
    ("100103", "Vittorio", "Alfieri", "ALESSANDRIA", 2010),
    # ARONA (Lago Maggiore)
    ("100201", "Carlo", "Borromeo", "ARONA", 1998),
    ("100202", "Antonio", "Rosmini", "ARONA", 2005),
    ("100203", "Salvatore", "Quasimodo", "ARONA", 2014),
    # BERGAMO — Donizetti/Lotto/Caravaggio
    ("100301", "Gaetano", "Donizetti", "BERGAMO", 1992),
    ("100302", "Lorenzo", "Lotto", "BERGAMO", 2001),
    ("100303", "Michelangelo", "Caravaggio", "BERGAMO", 2018),
    # BRESCIA — Arnaldo/Gambara/Speri
    ("100401", "Arnaldo", "da Brescia", "BRESCIA", 1996),
    ("100402", "Veronica", "Gambara", "BRESCIA", 2008),
    ("100403", "Tito", "Speri", "BRESCIA", 2016),
    # COLICO (LC, Valtellina)
    ("100501", "Ada", "Negri", "COLICO", 2002),
    ("100502", "Mario", "Rigoni Stern", "COLICO", 2011),
    ("100503", "Beppe", "Fenoglio", "COLICO", 2019),
    # COMO — Volta/Plinio/Foscolo
    ("100601", "Alessandro", "Volta", "COMO", 1990),
    ("100602", "Plinio", "il Giovane", "COMO", 2004),
    ("100603", "Ugo", "Foscolo", "COMO", 2013),
    # CREMONA — Stradivari/Monteverdi/Anguissola
    ("100701", "Antonio", "Stradivari", "CREMONA", 1993),
    ("100702", "Claudio", "Monteverdi", "CREMONA", 2006),
    ("100703", "Sofonisba", "Anguissola", "CREMONA", 2017),
    # DOMODOSSOLA (VB)
    ("100801", "Giosuè", "Carducci", "DOMODOSSOLA", 1999),
    ("100802", "Luigi", "Pirandello", "DOMODOSSOLA", 2007),
    ("100803", "Ippolito", "Nievo", "DOMODOSSOLA", 2015),
    # FIORENZA (Milano)
    ("100901", "Alda", "Merini", "FIORENZA", 1991),
    ("100902", "Carlo", "Porta", "FIORENZA", 2000),
    ("100903", "Carlo Emilio", "Gadda", "FIORENZA", 2012),
    # GALLARATE (VA)
    ("101001", "Lucio", "Fontana", "GALLARATE", 1997),
    ("101002", "Edoardo", "Bianchi", "GALLARATE", 2009),
    ("101003", "Pietro", "Mascagni", "GALLARATE", 2020),
    # GARIBALDI_ALE (Mi)
    ("101101", "Eugenio", "Montale", "GARIBALDI_ALE", 1994),
    ("101102", "Camillo", "Cavour", "GARIBALDI_ALE", 2003),
    ("101103", "Giuseppe", "Garibaldi", "GARIBALDI_ALE", 2014),
    # GARIBALDI_CADETTI (Mi)
    ("101201", "Carlo", "Cattaneo", "GARIBALDI_CADETTI", 1996),
    ("101202", "Giuseppe", "Mazzini", "GARIBALDI_CADETTI", 2008),
    ("101203", "Anna", "Magnani", "GARIBALDI_CADETTI", 2017),
    # GARIBALDI_TE (Mi)
    ("101301", "Luchino", "Visconti", "GARIBALDI_TE", 2001),
    ("101302", "Dino", "Buzzati", "GARIBALDI_TE", 2010),
    ("101303", "Italo", "Calvino", "GARIBALDI_TE", 2018),
    # GRECO_TE (Mi)
    ("101401", "Maria", "Montessori", "GRECO_TE", 1995),
    ("101402", "Francesco", "Petrarca", "GRECO_TE", 2006),
    ("101403", "Margherita", "Hack", "GRECO_TE", 2015),
    # GRECO_S9 (Mi)
    ("101501", "Enrico", "Fermi", "GRECO_S9", 1992),
    ("101502", "Rita", "Levi-Montalcini", "GRECO_S9", 2005),
    ("101503", "Federico", "Faggin", "GRECO_S9", 2019),
    # LECCO — Manzoni/Stoppani/Grossi
    ("101601", "Alessandro", "Manzoni", "LECCO", 1990),
    ("101602", "Antonio", "Stoppani", "LECCO", 2002),
    ("101603", "Tommaso", "Grossi", "LECCO", 2013),
    # LUINO — Sereni/Chiara/Luini
    ("101701", "Vittorio", "Sereni", "LUINO", 1998),
    ("101702", "Piero", "Chiara", "LUINO", 2007),
    ("101703", "Bernardino", "Luini", "LUINO", 2016),
    # MANTOVA — Virgilio/Mantegna/Tasso
    ("101801", "Publio", "Virgilio Marone", "MANTOVA", 1989),
    ("101802", "Andrea", "Mantegna", "MANTOVA", 2004),
    ("101803", "Torquato", "Tasso", "MANTOVA", 2014),
    # MORTARA (PV)
    ("101901", "Cesare", "Beccaria", "MORTARA", 2000),
    ("101902", "Carlo", "Goldoni", "MORTARA", 2011),
    ("101903", "Giambattista", "Vico", "MORTARA", 2020),
    # PAVIA — Spallanzani/Golgi/Ferraris
    ("102001", "Lazzaro", "Spallanzani", "PAVIA", 1993),
    ("102002", "Camillo", "Golgi", "PAVIA", 2004),
    ("102003", "Galileo", "Ferraris", "PAVIA", 2017),
    # PIACENZA — Gioia/Tondelli/Armani
    ("102101", "Melchiorre", "Gioia", "PIACENZA", 1997),
    ("102102", "Pier Vittorio", "Tondelli", "PIACENZA", 2009),
    ("102103", "Giorgio", "Armani", "PIACENZA", 2018),
    # SONDRIO (Valtellina)
    ("102201", "Francesco Saverio", "Quadrio", "SONDRIO", 2003),
    ("102202", "Giuseppe", "Romegialli", "SONDRIO", 2012),
    ("102203", "Mario", "Soldati", "SONDRIO", 2021),
    # TREVIGLIO (BG)
    ("102301", "Bartolomeo", "Colleoni", "TREVIGLIO", 1998),
    ("102302", "Cesare", "Cantù", "TREVIGLIO", 2008),
    ("102303", "Giambattista", "Cavalleri", "TREVIGLIO", 2019),
    # VERONA — Catullo/Barbarani/della Scala
    ("102401", "Gaio Valerio", "Catullo", "VERONA", 1991),
    ("102402", "Berto", "Barbarani", "VERONA", 2005),
    ("102403", "Cangrande", "della Scala", "VERONA", 2016),
    # VOGHERA (PV)
    ("102501", "Giovanni", "Pascoli", "VOGHERA", 2002),
    ("102502", "Grazia", "Deledda", "VOGHERA", 2010),
    ("102503", "Giuseppe", "Ungaretti", "VOGHERA", 2020),
]

# ──────────────────────────────────────────────────────────────────
# Indisponibilità seed: 12 voci attorno a oggi (mix tipi).
# Tuple: (codice_dipendente, tipo, offset_inizio_giorni, durata_giorni)
# ──────────────────────────────────────────────────────────────────
INDISPONIBILITA_SEED: list[tuple[str, str, int, int]] = [
    ("100101", "ferie", -2, 14),       # Eco in ferie da 2 giorni fa per 14gg
    ("100302", "malattia", 0, 5),      # Lotto malato oggi per 5gg
    ("101101", "ferie", -1, 10),       # Montale in ferie
    ("101601", "ROL", 0, 1),           # Manzoni 1 giorno ROL oggi
    ("100702", "formazione", -3, 7),   # Monteverdi formazione
    ("102001", "ferie", 5, 14),        # Spallanzani ferie future (non oggi)
    ("101802", "malattia", -1, 4),     # Mantegna malato
    ("100601", "ROL", 0, 1),           # Volta ROL oggi
    ("101403", "ferie", -5, 21),       # Hack ferie lunghe
    ("101001", "sciopero", 0, 1),      # Fontana sciopero oggi
    ("102403", "congedo", -10, 30),    # della Scala congedo lungo
    ("100802", "ferie", 10, 7),        # Pirandello ferie future (non oggi)
]


def _esc(s: str) -> str:
    """Escape singolo apice per literal SQL."""
    return s.replace("'", "''")


def upgrade() -> None:
    azienda_subq = "(SELECT id FROM azienda WHERE codice = 'trenord')"

    # ── persone ────────────────────────────────────────────────────
    persone_values = ",\n          ".join(
        f"('{cod}', '{_esc(nome)}', '{_esc(cogn)}', "
        f"(SELECT id FROM depot WHERE codice = '{depot}'), "
        f"DATE '{anno}-06-15', TRUE, 'PdC')"
        for cod, nome, cogn, depot, anno in PERSONE_SEED
    )
    op.execute(f"""
        INSERT INTO persona
          (azienda_id, codice_dipendente, nome, cognome,
           sede_residenza_id, data_assunzione, is_matricola_attiva, profilo)
        SELECT {azienda_subq}, v.codice, v.nome, v.cognome,
               v.sede_id, v.data_ass, v.attiva, v.profilo
        FROM (VALUES
          {persone_values}
        ) AS v(codice, nome, cognome, sede_id, data_ass, attiva, profilo)
    """)

    # ── indisponibilità ─────────────────────────────────────────────
    today = date.today()
    indisp_values = []
    for cod, tipo, offset_inizio, durata in INDISPONIBILITA_SEED:
        data_inizio = today + timedelta(days=offset_inizio)
        data_fine = data_inizio + timedelta(days=max(0, durata - 1))
        indisp_values.append(
            f"('{cod}', '{tipo}', DATE '{data_inizio.isoformat()}', "
            f"DATE '{data_fine.isoformat()}', TRUE)"
        )
    indisp_sql = ",\n          ".join(indisp_values)
    op.execute(f"""
        INSERT INTO indisponibilita_persona
          (persona_id, tipo, data_inizio, data_fine, is_approvato)
        SELECT p.id, v.tipo, v.di, v.df, v.approv
        FROM (VALUES
          {indisp_sql}
        ) AS v(codice, tipo, di, df, approv)
        JOIN persona p ON p.codice_dipendente = v.codice
                       AND p.azienda_id = {azienda_subq}
    """)


def downgrade() -> None:
    azienda_subq = "(SELECT id FROM azienda WHERE codice = 'trenord')"
    codici = ", ".join(f"'{p[0]}'" for p in PERSONE_SEED)

    op.execute(f"""
        DELETE FROM indisponibilita_persona
        WHERE persona_id IN (
            SELECT id FROM persona
            WHERE codice_dipendente IN ({codici})
            AND azienda_id = {azienda_subq}
        )
    """)
    op.execute(f"""
        DELETE FROM persona
        WHERE codice_dipendente IN ({codici})
        AND azienda_id = {azienda_subq}
    """)
