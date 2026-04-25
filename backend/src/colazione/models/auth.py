"""Strato 5 — autenticazione e audit.

Utenti applicativi (separati da `persona`), ruoli (cardinality 1:N),
notifiche e audit log.

Vedi `docs/SCHEMA-DATI-NATIVO.md` §9.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from colazione.db import Base


class AppUser(Base):
    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    persona_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("persona.id", ondelete="SET NULL")
    )
    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="RESTRICT")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppUserRuolo(Base):
    __tablename__ = "app_user_ruolo"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    app_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="CASCADE")
    )
    ruolo: Mapped[str] = mapped_column(String(40))


class Notifica(Base):
    __tablename__ = "notifica"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    destinatario_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="CASCADE")
    )
    tipo: Mapped[str] = mapped_column(String(60))
    titolo: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_letta: Mapped[bool] = mapped_column(Boolean, default=False)
    letta_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="SET NULL")
    )
    azione: Mapped[str] = mapped_column(String(60))
    target_tipo: Mapped[str | None] = mapped_column(String(60))
    target_id: Mapped[int | None] = mapped_column(BigInteger)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
