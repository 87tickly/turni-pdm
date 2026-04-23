"""
Cycle Optimizer — rimuove cicli vettura-vettura inutili da una sequenza
di segmenti PdC.

Bug diagnosticato (23/04/2026, richiesta utente): il builder legacy puo'
produrre sequenze come:

    10062     ALE -> MI     (prod, 15:49-17:08)
    2375 (v)  MI -> ALE     (vettura, 17:25-18:44)     <-- inutile
    2381 (v)  ALE -> MI     (vettura, 19:16-20:35)     <-- inutile
    2383     MI -> ALE      (prod, 21:25-22:44)

Le due vetture formano un cerchio MI->ALE->MI: il PdC avrebbe potuto
semplicemente aspettare a Milano tra le 17:08 e le 21:25. Il builder
legacy concatena piu' "blocchi prod+rientro" senza accorgersi che il
rientro del blocco 1 e il posizionamento del blocco 2 si cancellano.

Questo modulo fa un pass post-build che rileva e rimuove i cicli:

  Regola:
    Dati segmenti consecutivi A, B entrambi is_deadhead=True (vettura):
    se A.from == B.to e A.to == B.from, i due formano un cerchio
    (A va X->Y e B torna Y->X). Li rimuovo entrambi: il PdC resta
    fermo alla stazione X dall'orario A.dep all'orario B.arr.

  Regola estesa (se serve): A e B non strettamente consecutivi ma
  separati solo da segmenti che non cambiano stazione (es. refez
  in mezzo). Per ora manteniamo la regola stretta (consecutivi) per
  evitare eliminazioni aggressive.

Il modulo non altera segmenti produttivi (condotta).
"""
from __future__ import annotations

from typing import Optional


def _is_deadhead(seg) -> bool:
    if isinstance(seg, dict):
        return bool(seg.get("is_deadhead", False))
    return bool(getattr(seg, "is_deadhead", False))


def _is_refezione(seg) -> bool:
    if isinstance(seg, dict):
        return bool(seg.get("is_refezione", False))
    return bool(getattr(seg, "is_refezione", False))


def _get(seg, key, default=""):
    if isinstance(seg, dict):
        return seg.get(key, default)
    return getattr(seg, key, default)


def _from(seg) -> str:
    return (_get(seg, "from_station", "") or "").upper().strip()


def _to(seg) -> str:
    return (_get(seg, "to_station", "") or "").upper().strip()


def find_redundant_cycles(segments: list) -> list[tuple[int, int]]:
    """
    Ritorna la lista di coppie (i, j) di indici in `segments` che formano
    un ciclo vettura-vettura inutile. Solo coppie i, i+1 (strettamente
    consecutive) per la regola stretta.

    Esempio:
        [prod1, vett(X->Y), vett(Y->X), prod2] -> [(1, 2)]
    """
    pairs = []
    n = len(segments)
    for i in range(n - 1):
        a, b = segments[i], segments[i + 1]
        if not _is_deadhead(a) or not _is_deadhead(b):
            continue
        if _is_refezione(a) or _is_refezione(b):
            continue
        if _from(a) == _to(b) and _to(a) == _from(b) and _from(a) != _to(a):
            pairs.append((i, i + 1))
    return pairs


def remove_redundant_cycles(segments: list) -> tuple[list, int]:
    """
    Rimuove le coppie vettura-vettura che formano cicli X->Y + Y->X.

    Ritorna (nuova_lista, n_coppie_rimosse). Applica in modo iterativo
    per gestire il caso in cui dopo la rimozione emergono nuovi cicli
    (raro ma possibile con catene lunghe).
    """
    current = list(segments)
    total_removed = 0
    while True:
        pairs = find_redundant_cycles(current)
        if not pairs:
            break
        # Raccogli tutti gli indici da rimuovere in un passaggio (sicuro
        # perche' le coppie sono consecutive e non sovrapposte: iteriamo
        # su i fissando j=i+1, quindi due coppie consecutive richiedono
        # 4 indici distinti).
        to_drop = set()
        last_used = -1
        for i, j in pairs:
            if i <= last_used:
                continue   # salta coppie sovrapposte
            to_drop.add(i)
            to_drop.add(j)
            last_used = j
        current = [s for k, s in enumerate(current) if k not in to_drop]
        total_removed += len(to_drop) // 2
        if not to_drop:
            break
    return current, total_removed
