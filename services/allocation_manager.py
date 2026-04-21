"""
Allocation Manager — coordinamento unicita' treni cross-deposito.

Richiesta utente (21/04/2026): quando un treno e' assegnato a un turno
di un deposito (es. ALESSANDRIA), gli altri depositi (PAVIA, BRESCIA ecc.)
non possono usarlo nello stesso giorno di circolazione.

API semplice:
  - lock_trains(db, deposito, train_ids, turno_name, day_index):
    registra i treni come "in uso" da quel deposito. Skippa quelli
    gia' registrati ad altri (gestito dal DB UNIQUE).
  - released_by_depot(db, deposito): sblocca tutti i treni di un
    deposito (per rigenerare turno).
  - excluded_for(db, deposito, day_index): ritorna set di train_id
    che NON puo' usare (perche' gia' allocati ad altri depositi).

Il day_index = 0 e' usato per "allocazione generica" (quando non si
discrimina per giorno-variante del materiale). Per allocazione fine
(es. lunedi vs sabato) passare il day_index specifico del material_turn.
"""
from __future__ import annotations

from src.database.db import Database


def lock_trains(db: Database, deposito: str, train_ids: list,
                turno_name: str = "", day_index: int = 0) -> int:
    """Blocca train_ids per deposito. Ritorna numero righe inserite
    (treni effettivamente bloccati; duplicati vengono skippati)."""
    return db.allocate_trains(
        train_ids=train_ids,
        deposito=deposito,
        turno_name=turno_name,
        day_index=day_index,
    )


def released_by_depot(db: Database, deposito: str = "") -> int:
    """Sblocca tutti i treni allocati al deposito (o tutti se vuoto).
    Usato quando si rigenera un turno."""
    return db.clear_train_allocation(deposito)


def excluded_for(db: Database, deposito: str, day_index: int = 0) -> set:
    """Ritorna l'insieme di train_id che il deposito NON puo' usare
    perche' allocati ad altri depositi nello stesso day_index."""
    return db.get_trains_allocated_to_others(deposito, day_index)


def allocation_count(db: Database, deposito: str = "") -> int:
    """Conta le allocazioni totali o per deposito specifico."""
    return db.count_allocations(deposito)
