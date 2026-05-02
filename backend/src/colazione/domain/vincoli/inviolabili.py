"""Validator dei vincoli inviolabili a livello tipo materiale.

Single Source of Truth: ``data/vincoli_materiale_inviolabili.json``
(repo root). Il file è caricato all'import del modulo.

Il validator espone una funzione **pura** ``valida_regola()`` che riceve:
- la lista di corse del programma (già caricate dal chiamante),
- un lookup ``codice_stazione → nome``,
- il payload della regola in creazione (filtri + composizione),
- la lista di vincoli (caricati dal JSON).

E ritorna una lista di ``Violazione``. Lista vuota = regola valida.

Il caricamento DB è responsabilità del chiamante (l'API endpoint),
così questo modulo resta DB-agnostic e facilmente testabile.

Spec: ``data/vincoli_materiale_inviolabili.json`` ``_metadata``.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from colazione.domain.builder_giro.risolvi_corsa import matches_all

# =====================================================================
# Path di default — Single Source of Truth
# =====================================================================

# Il file canonico vive nel repo root in `data/`. Cerco risalendo i parent
# del modulo finché trovo la cartella `data/` con il file:
# - dev locale: backend/src/colazione/domain/vincoli/inviolabili.py → repo_root/data/...
# - Docker:    /app/src/colazione/domain/vincoli/inviolabili.py → /app/data/...
_VINCOLI_FILENAME = "vincoli_materiale_inviolabili.json"

# Override via env var (utile per test e setup custom).
_ENV_VAR = "COLAZIONE_VINCOLI_INVIOLABILI_PATH"


def _resolve_vincoli_path() -> Path:
    """Risolve il path al file vincoli (env var override, poi search ascendente)."""
    env_path = os.environ.get(_ENV_VAR)
    if env_path:
        return Path(env_path)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "data" / _VINCOLI_FILENAME
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"File {_VINCOLI_FILENAME!r} non trovato risalendo da {here}. "
        f"Setta {_ENV_VAR} per override, oppure verifica la cartella data/."
    )


# =====================================================================
# Modello
# =====================================================================


@dataclass(frozen=True)
class Vincolo:
    """Un vincolo inviolabile dichiarato nel JSON.

    Match logic per modalità whitelist:
    - Se ``stazioni_ammesse_lista`` non vuota: ENTRAMBE origine e
      destinazione della corsa devono essere nella lista (AND match).
      Più preciso, evita falsi positivi su stazioni ambigue.
    - Altrimenti, ``stazioni_ammesse_pattern`` matcha l'haystack
      "origine | destinazione" con OR semantics.

    Per modalità blacklist usa solo ``stazioni_vietate_pattern`` (OR
    su singola stazione).
    """

    id: str
    nome: str
    tipo: str  # tecnico_alimentazione | contrattuale_omologazione | operativo_*
    modalita: str  # whitelist | blacklist
    descrizione: str
    materiale_tipo_codici_target: frozenset[str]
    materiale_tipo_codici_esenti: frozenset[str] = frozenset()
    stazioni_ammesse_pattern: tuple[re.Pattern[str], ...] = ()
    stazioni_ammesse_lista: frozenset[str] = frozenset()
    stazioni_vietate_pattern: tuple[re.Pattern[str], ...] = ()
    linee_descrizione: tuple[str, ...] = ()


@dataclass(frozen=True)
class Violazione:
    """Una violazione di un vincolo HARD su una regola."""

    vincolo_id: str
    vincolo_nome: str
    vincolo_tipo: str
    materiale_tipo_codice: str
    descrizione: str
    # corse problematiche (numero_treno + stazioni). Tagliate a max 5 per leggibilità.
    corse_problematiche: tuple[dict[str, str], ...] = field(default_factory=tuple)


# =====================================================================
# Loader
# =====================================================================


def carica_vincoli(path: Path | None = None) -> list[Vincolo]:
    """Carica i vincoli dal JSON. Path default = ``data/vincoli_materiale_inviolabili.json``.

    Compila i pattern regex una sola volta. Solleva ``FileNotFoundError``
    se il file non esiste; ``json.JSONDecodeError`` se malformato.
    """
    p = path or _resolve_vincoli_path()
    raw = json.loads(p.read_text())
    out: list[Vincolo] = []
    for v in raw["vincoli"]:
        ammesse = tuple(
            re.compile(p) for p in v.get("stazioni_ammesse_pattern_regex", [])
        )
        vietate = tuple(
            re.compile(p) for p in v.get("stazioni_vietate_pattern_regex", [])
        )
        linee = tuple(
            v.get("linee_descrizione_ammesse", [])
            + v.get("linee_descrizione_vietate", [])
        )
        out.append(
            Vincolo(
                id=v["id"],
                nome=v["nome"],
                tipo=v["tipo"],
                modalita=v["modalita"],
                descrizione=v["descrizione"],
                materiale_tipo_codici_target=frozenset(v["materiale_tipo_codici_target"]),
                materiale_tipo_codici_esenti=frozenset(
                    v.get("materiale_tipo_codici_esenti", [])
                ),
                stazioni_ammesse_pattern=ammesse,
                stazioni_ammesse_lista=frozenset(
                    v.get("stazioni_ammesse_lista", [])
                ),
                stazioni_vietate_pattern=vietate,
                linee_descrizione=linee,
            )
        )
    return out


# =====================================================================
# Protocol per duck-typing della corsa
# =====================================================================


class _CorsaLike(Protocol):
    """CorsaCommerciale o equivalente di test."""

    numero_treno: str
    codice_origine: str
    codice_destinazione: str
    codice_linea: str | None
    direttrice: str | None
    categoria: str | None
    rete: str | None
    is_treno_garantito_feriale: bool
    is_treno_garantito_festivo: bool
    fascia_oraria: str | None


# =====================================================================
# Validation logic
# =====================================================================


def _stazioni_della_corsa(
    corsa: _CorsaLike, stazioni_lookup: dict[str, str]
) -> list[str]:
    """Ritorna i nomi (e codici fallback) delle stazioni origine + destinazione.

    Il ``stazioni_lookup`` è ``{codice_stazione: nome}``. Se il codice
    non è nel lookup (incoerenza DB), si usa il codice grezzo come
    fallback per il match regex.
    """
    nomi = []
    for codice in (corsa.codice_origine, corsa.codice_destinazione):
        nomi.append(stazioni_lookup.get(codice, codice))
    return nomi


def _corsa_matcha_stazioni_ammesse(
    corsa: _CorsaLike,
    stazioni_lookup: dict[str, str],
    pattern_ammesse: Sequence[re.Pattern[str]],
    lista_ammesse: frozenset[str] = frozenset(),
) -> bool:
    """True se la corsa è ammessa dalla whitelist.

    Se ``lista_ammesse`` non è vuota: AND match — ENTRAMBE origine e
    destinazione devono essere nella lista. Pattern_regex ignorati.

    Altrimenti: OR su pattern_regex contro haystack "origine | destinazione".
    """
    nomi = _stazioni_della_corsa(corsa, stazioni_lookup)
    if lista_ammesse:
        # AND match: tutte le stazioni della corsa devono essere nella lista
        return all(nome in lista_ammesse for nome in nomi)
    haystack = " | ".join(nomi)
    return any(p.search(haystack) for p in pattern_ammesse)


def _corsa_matcha_stazioni_vietate(
    corsa: _CorsaLike,
    stazioni_lookup: dict[str, str],
    pattern_vietate: Sequence[re.Pattern[str]],
) -> bool:
    """True se almeno una stazione (origine O destinazione) matcha un pattern vietato."""
    nomi = _stazioni_della_corsa(corsa, stazioni_lookup)
    haystack = " | ".join(nomi)
    return any(p.search(haystack) for p in pattern_vietate)


def _filtri_senza_giorno_tipo(filtri: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rimuove eventuali filtri ``giorno_tipo``: il vincolo geografico
    non dipende dal giorno (la linea è la stessa lun-dom)."""
    return [f for f in filtri if f.get("campo") != "giorno_tipo"]


def _corsa_problematica_summary(
    corsa: _CorsaLike, stazioni_lookup: dict[str, str]
) -> dict[str, str]:
    nomi = _stazioni_della_corsa(corsa, stazioni_lookup)
    return {
        "numero_treno": corsa.numero_treno,
        "origine": nomi[0],
        "destinazione": nomi[1],
    }


def corsa_ammessa_per_materiale(
    *,
    corsa: _CorsaLike,
    materiale_tipo_codice: str,
    stazioni_lookup: dict[str, str],
    vincoli: Sequence[Vincolo],
) -> bool:
    """Verifica se UNA corsa può essere assegnata a UN materiale.

    Usata dal builder (``risolvi_corsa``) per filtrare le regole
    candidate: se il materiale di una regola NON può fare quella
    corsa (vincolo HARD violato), la regola viene scartata e si
    prova la successiva (o la corsa diventa residua).

    Args:
        corsa: una corsa (CorsaCommerciale o mock con codice_origine,
            codice_destinazione).
        materiale_tipo_codice: codice PK del materiale (es. "ETR522").
        stazioni_lookup: ``{codice: nome}`` per matchare le stazioni
            contro i pattern dei vincoli.
        vincoli: lista di ``Vincolo`` (caricata da ``carica_vincoli()``).

    Returns:
        ``True`` se il materiale può fare la corsa, ``False`` altrimenti.
        Se la lista vincoli è vuota, ritorna sempre ``True`` (no check).
    """
    for vincolo in vincoli:
        # Vincolo applicabile a questo materiale?
        if materiale_tipo_codice not in vincolo.materiale_tipo_codici_target:
            continue
        if materiale_tipo_codice in vincolo.materiale_tipo_codici_esenti:
            continue

        if vincolo.modalita == "whitelist":
            # La corsa deve matchare le stazioni ammesse
            if not _corsa_matcha_stazioni_ammesse(
                corsa,
                stazioni_lookup,
                vincolo.stazioni_ammesse_pattern,
                vincolo.stazioni_ammesse_lista,
            ):
                return False
        elif vincolo.modalita == "blacklist":
            # La corsa NON deve matchare le stazioni vietate
            if _corsa_matcha_stazioni_vietate(
                corsa, stazioni_lookup, vincolo.stazioni_vietate_pattern
            ):
                return False
        else:
            raise ValueError(
                f"vincolo {vincolo.id}: modalita={vincolo.modalita!r} non supportata"
            )
    return True


def valida_regola(
    *,
    corse_programma: Iterable[_CorsaLike],
    stazioni_lookup: dict[str, str],
    composizione: Sequence[dict[str, Any]],
    filtri: list[dict[str, Any]],
    vincoli: Sequence[Vincolo],
) -> list[Violazione]:
    """Valida una regola contro i vincoli inviolabili. Funzione pura.

    Args:
        corse_programma: tutte le corse candidate del programma
            (già filtrate per azienda + finestra temporale).
        stazioni_lookup: ``{codice_stazione: nome}`` per convertire i codici
            in nomi leggibili e matchare i pattern regex.
        composizione: lista ``[{materiale_tipo_codice, n_pezzi}, ...]`` della
            regola.
        filtri: ``filtri_json`` della regola (lista di dict
            ``{campo, op, valore}``).
        vincoli: lista di ``Vincolo`` caricati da ``carica_vincoli()``.

    Returns:
        Lista di ``Violazione`` (vuota = regola valida).
    """
    corse_list = list(corse_programma)
    filtri_geografici = _filtri_senza_giorno_tipo(filtri)
    # La funzione matches_all richiede giorno_tipo: usiamo "feriale" come
    # dummy perché abbiamo già rimosso i filtri giorno_tipo. Il giorno è
    # ininfluente per il match dei filtri rimanenti.
    GIORNO_DUMMY = "feriale"
    corse_catturate = [
        c for c in corse_list if matches_all(filtri_geografici, c, GIORNO_DUMMY)
    ]

    violazioni: list[Violazione] = []

    codici_composizione = {item["materiale_tipo_codice"] for item in composizione}

    for vincolo in vincoli:
        # Quali codici della composizione sono soggetti al vincolo?
        codici_soggetti = (
            codici_composizione
            & vincolo.materiale_tipo_codici_target
        ) - vincolo.materiale_tipo_codici_esenti
        if not codici_soggetti:
            continue  # vincolo non applicabile

        for codice in sorted(codici_soggetti):
            corse_problematiche: list[_CorsaLike] = []

            if vincolo.modalita == "whitelist":
                # Tutte le corse devono matchare ammesse. Quelle che non
                # matchano sono problematiche.
                for corsa in corse_catturate:
                    if not _corsa_matcha_stazioni_ammesse(
                        corsa,
                        stazioni_lookup,
                        vincolo.stazioni_ammesse_pattern,
                        vincolo.stazioni_ammesse_lista,
                    ):
                        corse_problematiche.append(corsa)

            elif vincolo.modalita == "blacklist":
                # Nessuna corsa deve matchare vietate. Quelle che matchano
                # sono problematiche.
                for corsa in corse_catturate:
                    if _corsa_matcha_stazioni_vietate(
                        corsa, stazioni_lookup, vincolo.stazioni_vietate_pattern
                    ):
                        corse_problematiche.append(corsa)
            else:
                raise ValueError(
                    f"vincolo {vincolo.id}: modalita={vincolo.modalita!r} non supportata"
                )

            if corse_problematiche:
                violazioni.append(
                    Violazione(
                        vincolo_id=vincolo.id,
                        vincolo_nome=vincolo.nome,
                        vincolo_tipo=vincolo.tipo,
                        materiale_tipo_codice=codice,
                        descrizione=vincolo.descrizione,
                        corse_problematiche=tuple(
                            _corsa_problematica_summary(c, stazioni_lookup)
                            for c in corse_problematiche[:5]  # max 5 per leggibilità
                        ),
                    )
                )

    return violazioni
