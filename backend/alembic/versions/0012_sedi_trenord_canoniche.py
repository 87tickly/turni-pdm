"""0012 — Configurazione canonica sedi Trenord (Sprint 7.6 MR 2)

Smoke utente del Pianificatore Giro Materiale ha richiesto correzione
delle località manutenzione Trenord:

1. **FIO**: la stazione collegata corretta è **MILANO CERTOSA**
   (S01640), non MILANO CENTRALE (S01700). Certosa è il proxy
   commerciale fisicamente più vicino alla sede di Fiorenza, usato
   dal builder per generare il vuoto sede→origine prima corsa.

2. **Whitelist M:N stazioni-vicine-sede** (`localita_stazione_vicina`):
   popolazione canonica per le 6 sedi Trenord. La tabella esiste dal
   migration 0007 ma era stata lasciata vuota (lo script
   `scripts/seed_whitelist_e_accoppiamenti.py` non era mai stato
   applicato in DB).

   Pattern (case-insensitive, % wildcard):
   - **FIO**: GARIBALDI (no PASSANTE), CENTRALE, LAMBRATE, ROGOREDO,
     GRECO PIRELLI, CERTOSA (sede)
   - **NOV**: CADORNA, BOVISA POLITECNICO, SARONNO
     (NOVATE Milanese non presente come stazione PdE Trenord — vedi
     TN-UPDATE entry 70 per il dettaglio)
   - **CAM**: SEVESO, SARONNO
   - **LEC**: LECCO
   - **CRE**: CREMONA
   - **ISE**: ISEO

Migration **idempotente**: `INSERT ... ON CONFLICT DO NOTHING`. Già
in DB? Skip silenzioso.

Decisione utente 2026-05-02 — Sprint 7.6 MR 2.
"""

from __future__ import annotations

from alembic import op

revision: str = "b9e4c712a83f"
down_revision: str | None = "a8d3c5f97e21"  # 0011_drop_programma_stagione
branch_labels = None
depends_on = None


# (codice_breve_sede, lista pattern ILIKE per i nomi stazione)
WHITELIST_TRENORD: list[tuple[str, list[str]]] = [
    (
        "IMPMAN_MILANO_FIORENZA",
        [
            "%MILANO%GARIBALDI",  # esclude "...PASSANTE" (no % finale)
            "%MILANO%CENTRALE%",
            "%MILANO%LAMBRATE%",
            "%MILANO%ROGOREDO%",
            "%MILANO%GRECO%PIRELLI%",
            "MILANO CERTOSA",  # nuova in 0012: sede
        ],
    ),
    (
        "IMPMAN_NOVATE",
        [
            "%MILANO%CADORNA%",
            "%MILANO%BOVISA%",
            "SARONNO",  # condivisa con CAM
        ],
    ),
    (
        "IMPMAN_CAMNAGO",
        [
            "SEVESO",
            "SARONNO",  # condivisa con NOV
        ],
    ),
    ("IMPMAN_LECCO", ["LECCO"]),
    ("IMPMAN_CREMONA", ["CREMONA"]),
    ("IMPMAN_ISEO", ["ISEO"]),
]


def upgrade() -> None:
    # ----------------------------------------------------------------
    # 1) FIO.stazione_collegata = MILANO CERTOSA (S01640).
    #    Idempotente: WHERE codice = 'IMPMAN_MILANO_FIORENZA' AND
    #    stazione_collegata_codice IS DISTINCT FROM 'S01640'.
    # ----------------------------------------------------------------
    op.execute(
        """
        UPDATE localita_manutenzione
        SET stazione_collegata_codice = (
          SELECT codice FROM stazione WHERE nome = 'MILANO CERTOSA' LIMIT 1
        )
        WHERE codice = 'IMPMAN_MILANO_FIORENZA'
          AND (
            stazione_collegata_codice IS DISTINCT FROM (
              SELECT codice FROM stazione WHERE nome = 'MILANO CERTOSA' LIMIT 1
            )
          )
        """
    )

    # ----------------------------------------------------------------
    # 2) Whitelist M:N. Per ogni (sede, pattern) cerca la stazione
    #    via ILIKE; se UNICO match → INSERT ON CONFLICT DO NOTHING.
    #    Se 0 o N match: skip + RAISE NOTICE (visibile in alembic
    #    upgrade output, non blocca la migration: meglio whitelist
    #    incompleta ma migration green che migration broken in CI).
    # ----------------------------------------------------------------
    for loc_codice, patterns in WHITELIST_TRENORD:
        for pattern in patterns:
            op.execute(
                f"""
                DO $$
                DECLARE
                  v_loc_id BIGINT;
                  v_st_codice VARCHAR;
                  v_count INT;
                BEGIN
                  SELECT id INTO v_loc_id FROM localita_manutenzione
                  WHERE codice = '{loc_codice}';
                  IF v_loc_id IS NULL THEN
                    RAISE NOTICE 'Sede % non trovata, skip pattern %',
                      '{loc_codice}', '{pattern}';
                    RETURN;
                  END IF;

                  SELECT COUNT(*), MIN(codice) INTO v_count, v_st_codice
                  FROM stazione
                  WHERE nome ILIKE '{pattern}';

                  IF v_count = 0 THEN
                    RAISE NOTICE 'Pattern % non matcha alcuna stazione (sede %)',
                      '{pattern}', '{loc_codice}';
                  ELSIF v_count > 1 THEN
                    RAISE NOTICE 'Pattern % ambiguo (% match) per sede %',
                      '{pattern}', v_count, '{loc_codice}';
                  ELSE
                    INSERT INTO localita_stazione_vicina
                      (localita_manutenzione_id, stazione_codice)
                    VALUES (v_loc_id, v_st_codice)
                    ON CONFLICT DO NOTHING;
                  END IF;
                END $$;
                """  # noqa: S608 — pattern hardcoded, no user input
            )


def downgrade() -> None:
    # Inverso simmetrico:
    # 1) restore FIO.stazione_collegata = MILANO CENTRALE
    # 2) DELETE righe whitelist inserite da questa migration
    #    (cancelliamo TUTTA la whitelist delle 6 sedi Trenord — semplice
    #    e affidabile: chi vuole rieseguirla rilancia upgrade)
    op.execute(
        """
        UPDATE localita_manutenzione
        SET stazione_collegata_codice = (
          SELECT codice FROM stazione WHERE nome = 'MILANO CENTRALE' LIMIT 1
        )
        WHERE codice = 'IMPMAN_MILANO_FIORENZA'
        """
    )
    op.execute(
        """
        DELETE FROM localita_stazione_vicina
        WHERE localita_manutenzione_id IN (
          SELECT id FROM localita_manutenzione
          WHERE codice IN (
            'IMPMAN_MILANO_FIORENZA', 'IMPMAN_NOVATE', 'IMPMAN_CAMNAGO',
            'IMPMAN_LECCO', 'IMPMAN_CREMONA', 'IMPMAN_ISEO'
          )
        )
        """
    )
