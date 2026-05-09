"""Programma context per builder PdC — Sprint 8.2 MR-PD-FIX-SEVERO 3b A2.

Incapsula le 3 dipendenze condivise di un "run di costruzione PdC su un
programma": il client httpx, la cache partenze (``PartenzeCache`` ora
**obbligatoria**), il registro vetture cross-PdC. Iniettato
nell'endpoint MR-PD5 come dipendenza per request.

NB rinominato da ``builder_programma.py`` (originale piano) in
``programma_context.py`` per chiarezza naming (S6 SEVERO).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.domain.builder_pdc.registro_vetture import (
    RegistroVettureAssegnate,
)
from colazione.integrations.live_arturo import PartenzeCache

logger = logging.getLogger(__name__)


@dataclass
class BuilderProgrammaContext:
    """Context object per la generazione PdC sull'intero programma.

    A2: ``cache`` è **shared cross-build** all'interno della stessa
    request endpoint — una sola entry per stazione anche se il resolver
    è invocato per N giri/turni (riduce chiamate API live e garantisce
    idempotenza intra-request).

    A1: ``registro`` viene popolato da DB all'inizio del run con i
    turni PdC esistenti del programma (factory async) + aggiornato
    in-memory ad ogni nuovo turno persistito (POST-INSERT in
    ``giornata_base.persisti_un_turno_pdc``).

    Il context è **per request**: NON va salvato in stato globale
    (cache miss tra request è acceptable, sovra-fetch più che race).
    Per cache cross-request va MR-PD7+ con snapshot DB.
    """

    cache: PartenzeCache
    """Cache delle response /api/partenze/{stazione}. Obbligatoria nel
    resolver post-3b (signature change rispetto al MVP MR-PD3 che la
    aveva opt-in)."""

    registro: RegistroVettureAssegnate
    """Registro vetture cross-PdC. Inizializzato da DB + aggiornato
    POST-INSERT ad ogni nuovo turno persistito nello stesso run."""

    live_client: httpx.AsyncClient
    """Client httpx riusabile (TLS connection pool). Lifespan per
    request."""

    programma_id: int
    """ID del programma per cui questo context è stato creato. Usato
    per logging/diagnostica + per ri-popolare il registro se serve."""

    metadata: dict[str, int | str] = field(default_factory=dict)
    """Spazio metadata libero per il chiamante (es. contatori turni
    costruiti nel run, statistiche cache, ecc.)."""

    @classmethod
    async def crea_per_programma(
        cls,
        db: AsyncSession,
        *,
        programma_id: int,
        live_client: httpx.AsyncClient,
    ) -> BuilderProgrammaContext:
        """Factory che istanzia il context per un programma.

        Esegue 1 query DB per popolare il registro con i turni esistenti
        + crea cache vuota + lega al client httpx fornito.

        Args:
            db: Sessione AsyncSession per la query del registro.
            programma_id: ID del programma corrente.
            live_client: Client httpx già aperto (gestione lifespan a
                cura del chiamante).

        Returns:
            Context pronto da passare a
            ``costruisci_giornata_deposito_first``.
        """
        registro = await RegistroVettureAssegnate.from_db(
            db, programma_id=programma_id
        )
        cache = PartenzeCache()
        ctx = cls(
            cache=cache,
            registro=registro,
            live_client=live_client,
            programma_id=programma_id,
        )
        logger.info(
            "BuilderProgrammaContext: creato per programma_id=%d, "
            "registro pre-popolato con %d vetture",
            programma_id,
            registro.n_assegnate,
        )
        return ctx


__all__ = ["BuilderProgrammaContext"]
