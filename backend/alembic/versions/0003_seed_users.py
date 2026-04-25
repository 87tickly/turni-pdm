"""0003 seed_users — utenti applicativi iniziali (Sprint 2.5).

Crea due utenti per il bootstrap dell'app:
- `admin` con flag `is_admin=TRUE` e ruolo ADMIN
- `pianificatore_giro_demo` con ruolo PIANIFICATORE_GIRO

Le password sono prese da:
- env `ADMIN_DEFAULT_PASSWORD` (oppure default `admin12345`)
- env `DEMO_PASSWORD` (oppure default `demo12345`)

Gli hash bcrypt sono calcolati a runtime (cost 12). Il fatto che il
salt sia random implica che ogni esecuzione produce hash diversi: una
sequenza `down + up` cambia l'hash ma non la password effettiva.

⚠️ I default `admin12345` / `demo12345` sono SOLO per dev locale.
Imposta `ADMIN_DEFAULT_PASSWORD` in env per ambienti condivisi.

Revision ID: eb558744cc79
Revises: 8cc5db6b9dcc
Create Date: 2026-04-25 20:08:32.817836+00:00

"""

import os
from collections.abc import Sequence

from alembic import op

from colazione.auth.password import hash_password

# revision identifiers, used by Alembic.
revision: str = "eb558744cc79"
down_revision: str | None = "8cc5db6b9dcc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ADMIN_USERNAME = "admin"
DEMO_USERNAME = "pianificatore_giro_demo"


def upgrade() -> None:
    admin_password = os.getenv("ADMIN_DEFAULT_PASSWORD") or "admin12345"
    demo_password = os.getenv("DEMO_PASSWORD") or "demo12345"

    admin_hash = hash_password(admin_password)
    demo_hash = hash_password(demo_password)

    azienda_subq = "(SELECT id FROM azienda WHERE codice = 'trenord')"

    op.execute(f"""
        INSERT INTO app_user (username, password_hash, is_admin, azienda_id) VALUES
          ('{ADMIN_USERNAME}', '{admin_hash}', TRUE,  {azienda_subq}),
          ('{DEMO_USERNAME}',  '{demo_hash}',  FALSE, {azienda_subq})
    """)

    op.execute(f"""
        INSERT INTO app_user_ruolo (app_user_id, ruolo)
        SELECT id, 'ADMIN' FROM app_user WHERE username = '{ADMIN_USERNAME}'
    """)
    op.execute(f"""
        INSERT INTO app_user_ruolo (app_user_id, ruolo)
        SELECT id, 'PIANIFICATORE_GIRO' FROM app_user WHERE username = '{DEMO_USERNAME}'
    """)


def downgrade() -> None:
    op.execute(f"""
        DELETE FROM app_user_ruolo
        WHERE app_user_id IN (
            SELECT id FROM app_user
            WHERE username IN ('{ADMIN_USERNAME}', '{DEMO_USERNAME}')
        )
    """)
    op.execute(f"""
        DELETE FROM app_user
        WHERE username IN ('{ADMIN_USERNAME}', '{DEMO_USERNAME}')
    """)
