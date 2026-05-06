"""Concatenazione ciclica delle giornate-tipo in turni materiali
(MR-1110 Step 4 — vedi ``docs/MR-1110-DESIGN.md`` §4.4).

Decisione utente 2026-05-06: dato l'output del sotto-MR 2
(``identifica_giornate_tipo``), costruisce i ``Turno`` ordinando le
giornate-tipo ciclicamente: ``G1 → G2 → … → GN → G1`` con vincolo di
concatenazione **rigido** (D6 chiusa entry 193):

    staz_fine(G_K) == staz_inizio(G_(K+1))   per ogni K
    staz_fine(GN)  == staz_inizio(G1)        chiusura del ciclo

**Niente vuoti notturni di posizionamento ad hoc** fra giornate-tipo:
se due giornate-tipo non si concatenano per nessuna permutazione,
finiscono in turni distinti (D2 chiusa entry 198: "ciclo rotto →
multi-turno").

**Caso degenere N=1**: una giornata-tipo che si auto-concatena
(``staz_fine == staz_inizio``) forma un turno di 1 giornata. Esempio
reale: turno 1104 stagionale MDVE/MDVC.

Algoritmo (alto livello):

1. Raggruppa le ``GiornataTipo`` per ``(materiale_tipo_codice,
   localita_codice)``. Ogni gruppo è candidato a formare 1+ turni.
2. Per ogni gruppo, costruisci un grafo orientato: nodi = giornate-tipo
   del gruppo, archi ``G_a → G_b`` se ``staz_fine_a == staz_inizio_b``.
3. Trova **cicli hamiltoniani** sul gruppo (= un ciclo che attraversa
   tutte le giornate-tipo esattamente una volta). Se il gruppo è
   piccolo (N ≤ ~20, vedi turno Caravaggio 1125 con N=17 come
   benchmark Trenord), una ricerca esaustiva con backtracking è
   trattabile.
4. **D2 — ciclo rotto**: se nessun ciclo hamiltoniano sul gruppo
   intero esiste, decomponi nei ``cicli connessi minimali``: per
   ogni componente fortemente connessa del grafo, ripeti la ricerca
   hamiltoniana SOLO su quella componente. Se ancora niente, fallback:
   ogni nodo isolato (= che si auto-concatena) diventa un turno N=1;
   nodi che NON si auto-concatenano vanno scartati come ``orfane``
   (impossibili da concatenare → corse residue del programma).

Output: lista di ``Turno`` ordinati per chiave + lista di
``GiornataTipo`` orfane (impossibili da inserire in alcun ciclo).

Il modulo è **DB-agnostic**: opera solo sulle dataclass di
``giornata_tipo.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

from colazione.domain.builder_giro.giornata_tipo import GiornataTipo

# =====================================================================
# Output dataclass
# =====================================================================


@dataclass(frozen=True)
class Turno:
    """Un turno materiale: ciclo ordinato di N giornate-tipo concatenate.

    Sprint MR-1110 sotto-MR 3: output finale dello Step 4. Sostituisce
    concettualmente il ``GiroAggregato`` del builder v1
    (``aggregazione_a2.py``), con la differenza che le giornate-tipo
    sono **fasi del ciclo** (D1 — chiave 5-uple) e non "K-esima
    posizione di calendario".

    Attributi:
        materiale_tipo_codice: tipo materiale del turno (parte 1 della
            chiave gruppo).
        localita_codice: sede manutenzione (parte 2 della chiave gruppo).
        giornate_tipo: tuple ordinata ciclicamente. ``giornate_tipo[K]``
            = giornata in posizione (K+1) del ciclo. La chiusura
            ciclica è implicita: ``staz_fine(giornate_tipo[-1]) ==
            staz_inizio(giornate_tipo[0])``.
        n_giornate: ``len(giornate_tipo)`` (≥ 1).

    Invarianti (verificate dal builder, non dal dataclass):

    - Per ogni K in [0, N-1]: ``giornate_tipo[K].staz_fine ==
      giornate_tipo[(K+1) % N].staz_inizio``.
    - Tutte le giornate-tipo condividono ``materiale_tipo_codice`` e
      ``localita_codice`` con il turno.
    """

    materiale_tipo_codice: str
    localita_codice: str
    giornate_tipo: tuple[GiornataTipo, ...]

    @property
    def n_giornate(self) -> int:
        return len(self.giornate_tipo)


# =====================================================================
# Helpers privati
# =====================================================================


def _raggruppa_per_chiave_gruppo(
    giornate: list[GiornataTipo],
) -> dict[tuple[str, str], list[GiornataTipo]]:
    """Raggruppa giornate-tipo per chiave ``(materiale, sede)``.

    Ogni gruppo è candidato a formare uno o più ``Turno``: tutte le
    giornate del gruppo condividono materiale e sede (invariante del
    ``Turno``).
    """
    per_chiave: dict[tuple[str, str], list[GiornataTipo]] = {}
    for gt in giornate:
        chiave = (gt.materiale_tipo_codice, gt.localita_codice)
        per_chiave.setdefault(chiave, []).append(gt)
    return per_chiave


def _cerca_ciclo_hamiltoniano(
    nodi: list[GiornataTipo],
) -> tuple[GiornataTipo, ...] | None:
    """Cerca un ciclo hamiltoniano sul grafo delle giornate-tipo.

    Grafo orientato: ``G_a → G_b`` se ``staz_fine_a == staz_inizio_b``.
    Cerca una permutazione ``(π[0], π[1], …, π[N-1])`` tale che:

    - ``staz_fine(π[K]) == staz_inizio(π[K+1])`` per ogni K in [0, N-2]
    - ``staz_fine(π[N-1]) == staz_inizio(π[0])`` (chiusura ciclica)

    Algoritmo: backtracking DFS sul nodo lessicograficamente minimo
    (per determinismo). Se più cicli esistono, ritorna il primo
    incontrato — la radice fissa garantisce stabilità.

    Complessità peggiore: O(N!), ma con pruning forte (matching su
    `staz_fine`/`staz_inizio` + verifica chiusura) il caso medio è
    molto inferiore. Per N ≤ ~20 (benchmark Caravaggio 1125 N=17) è
    trattabile.

    Args:
        nodi: lista di ``GiornataTipo`` di uno stesso gruppo
            ``(materiale, sede)``. Min 1.

    Returns:
        Tuple ordinata di N giornate-tipo che formano il ciclo, oppure
        ``None`` se nessun ciclo hamiltoniano esiste.

    Casi degeneri:
    - N=1: ritorna ``(nodi[0],)`` se la giornata si auto-concatena
      (``staz_fine == staz_inizio``), altrimenti ``None``.
    """
    n = len(nodi)
    if n == 0:
        return None

    # Caso degenere N=1: auto-concatenazione richiesta.
    if n == 1:
        gt = nodi[0]
        if gt.staz_fine == gt.staz_inizio:
            return (gt,)
        return None

    # Ordinamento deterministico: permutiamo dalla giornata
    # lessicograficamente minima.
    nodi_ordinati = sorted(
        nodi,
        key=lambda g: (
            g.staz_inizio,
            g.staz_fine,
            g.codice_servizio_dominante or "",
        ),
    )

    radice = nodi_ordinati[0]
    visitati: set[int] = {0}
    cammino: list[GiornataTipo] = [radice]

    def _dfs(corrente: GiornataTipo) -> bool:
        # Caso base: tutti i nodi visitati. Verifica chiusura ciclica.
        if len(cammino) == n:
            return corrente.staz_fine == radice.staz_inizio

        for idx, candidato in enumerate(nodi_ordinati):
            if idx in visitati:
                continue
            if candidato.staz_inizio != corrente.staz_fine:
                continue
            visitati.add(idx)
            cammino.append(candidato)
            if _dfs(candidato):
                return True
            cammino.pop()
            visitati.remove(idx)
        return False

    if _dfs(radice):
        return tuple(cammino)
    return None


def _componenti_fortemente_connesse(
    nodi: list[GiornataTipo],
) -> list[list[GiornataTipo]]:
    """Calcola le componenti fortemente connesse (SCC) del grafo
    orientato delle giornate-tipo.

    Algoritmo: Tarjan iterativo (versione stack-based per evitare
    ricorsione profonda). Output: lista di SCC, ognuna è una lista
    non-vuota di ``GiornataTipo`` mutualmente raggiungibili.

    Una SCC singleton ``[gt]`` con ``staz_fine == staz_inizio`` è un
    nodo "ciclico su se stesso" → forma un Turno N=1 valido.
    Una SCC singleton senza auto-loop NON forma alcun ciclo.

    Args:
        nodi: lista di ``GiornataTipo`` (gruppo (materiale, sede)).

    Returns:
        Lista di SCC. Ogni SCC è una lista non vuota di nodi.
    """
    n = len(nodi)
    # Indici per veloce lookup nella DFS.
    idx_per_nodo: dict[int, int] = {id(g): i for i, g in enumerate(nodi)}

    # Adiacenza: per ogni nodo, lista degli indici dei successori.
    adiacenza: list[list[int]] = [[] for _ in range(n)]
    for i, ga in enumerate(nodi):
        for j, gb in enumerate(nodi):
            if i == j:
                continue
            if ga.staz_fine == gb.staz_inizio:
                adiacenza[i].append(j)
    # Auto-loop esplicito (G se staz_fine == staz_inizio).
    for i, g in enumerate(nodi):
        if g.staz_fine == g.staz_inizio:
            adiacenza[i].append(i)

    # Tarjan SCC.
    indices: dict[int, int] = {}
    lowlink: dict[int, int] = {}
    on_stack: set[int] = set()
    stack: list[int] = []
    counter = [0]
    scc_list: list[list[int]] = []

    def _strongconnect(v: int) -> None:
        # Iterativo con stack di frame esplicito (evita ricorsione
        # profonda su grafi grandi).
        call_stack: list[tuple[int, int]] = [(v, 0)]
        while call_stack:
            node, child_idx = call_stack[-1]
            if child_idx == 0:
                indices[node] = counter[0]
                lowlink[node] = counter[0]
                counter[0] += 1
                stack.append(node)
                on_stack.add(node)
            children = adiacenza[node]
            if child_idx < len(children):
                w = children[child_idx]
                call_stack[-1] = (node, child_idx + 1)
                if w not in indices:
                    call_stack.append((w, 0))
                elif w in on_stack:
                    lowlink[node] = min(lowlink[node], indices[w])
            else:
                # Tutti i figli esplorati: pop frame + chiusura SCC se
                # lowlink == indices.
                if lowlink[node] == indices[node]:
                    scc: list[int] = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        scc.append(w)
                        if w == node:
                            break
                    scc_list.append(scc)
                call_stack.pop()
                if call_stack:
                    parent = call_stack[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[node])

    for i in range(n):
        if i not in indices:
            _strongconnect(i)

    # Converte indici → GiornataTipo, usando idx_per_nodo per
    # consistency anche se nodi[i] è già il riferimento.
    _ = idx_per_nodo  # tenuto per chiarezza; nodi[i] basta.
    return [[nodi[i] for i in scc] for scc in scc_list]


# =====================================================================
# API pubblica
# =====================================================================


def concatena_in_turni(
    giornate: list[GiornataTipo],
) -> tuple[list[Turno], list[GiornataTipo]]:
    """Costruisce i ``Turno`` concatenando ciclicamente le giornate-tipo.

    Implementa lo Step 4 del nuovo builder MR-1110 (vedi
    ``docs/MR-1110-DESIGN.md`` §4.4 + decisioni D2/D6).

    Pipeline:

    1. Raggruppa le ``GiornataTipo`` per ``(materiale, sede)``.
    2. Per ogni gruppo, tenta un **ciclo hamiltoniano sul gruppo
       intero**. Se trovato → 1 Turno con tutte le giornate del gruppo.
    3. **D2 — ciclo rotto**: se nessun ciclo intero esiste, calcola
       le componenti fortemente connesse (SCC) del grafo. Per ogni
       SCC, tenta un ciclo hamiltoniano DENTRO la SCC.
       - Se trovato → Turno con le giornate di quella SCC.
       - Se la SCC è un singleton con auto-loop (``staz_fine ==
         staz_inizio``) → Turno N=1 valido.
       - Altrimenti → giornate della SCC vanno in ``orfane``.
    4. Output ordinato per ``(materiale, sede, n_giornate desc, prima
       staz_inizio)``.

    Args:
        giornate: lista di ``GiornataTipo`` (output di
            ``identifica_giornate_tipo``).

    Returns:
        Tupla ``(turni, orfane)``:

        - ``turni``: lista di ``Turno`` costruiti, ordinata
          deterministicamente per chiave.
        - ``orfane``: lista di ``GiornataTipo`` impossibili da
          inserire in alcun ciclo (= SCC senza ciclo hamiltoniano).
          Restituite al caller per gestione "corse residue" del
          programma materiale.

    Esempi:
        Input vuoto → output vuoto:

        >>> concatena_in_turni([])
        ([], [])
    """
    if not giornate:
        return ([], [])

    turni: list[Turno] = []
    orfane: list[GiornataTipo] = []

    per_gruppo = _raggruppa_per_chiave_gruppo(giornate)

    for (materiale, sede), nodi_gruppo in per_gruppo.items():
        # Tentativo 1: ciclo hamiltoniano sul gruppo intero.
        ciclo = _cerca_ciclo_hamiltoniano(nodi_gruppo)
        if ciclo is not None:
            turni.append(
                Turno(
                    materiale_tipo_codice=materiale,
                    localita_codice=sede,
                    giornate_tipo=ciclo,
                )
            )
            continue

        # Tentativo 2 (D2): scomponi in SCC e cerca ciclo dentro
        # ogni componente.
        scc_list = _componenti_fortemente_connesse(nodi_gruppo)
        for scc in scc_list:
            ciclo_scc = _cerca_ciclo_hamiltoniano(scc)
            if ciclo_scc is not None:
                turni.append(
                    Turno(
                        materiale_tipo_codice=materiale,
                        localita_codice=sede,
                        giornate_tipo=ciclo_scc,
                    )
                )
            else:
                # SCC senza ciclo hamiltoniano (es. nodi isolati senza
                # auto-loop) → orfane.
                orfane.extend(scc)

    # Ordinamento deterministico:
    # (materiale, sede, n_giornate desc, prima staz_inizio).
    turni.sort(
        key=lambda t: (
            t.materiale_tipo_codice,
            t.localita_codice,
            -t.n_giornate,
            t.giornate_tipo[0].staz_inizio,
        )
    )
    orfane.sort(
        key=lambda g: (
            g.materiale_tipo_codice,
            g.localita_codice,
            g.staz_inizio,
            g.staz_fine,
        )
    )

    return (turni, orfane)
