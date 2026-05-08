"""Vincoli soft pesati per il builder esplorativo (Sprint 8.1 MR-A1).

Foundation del refactor "filtra-e-scarta" → "esplora-e-rilassa". Definisce
le strutture dati che il builder esplorativo userà a partire da MR-A3
per modellare i vincoli del programma materiale come **vincoli soft
pesati con fallback gerarchico**, invece che come **filtri AND-rigidi**.

**Decisione utente 2026-05-08 Q1=b**: regole del programma = vincolo
SOFT con fallback governato. Il builder prova prima il vincolo
configurato (es. ``linea=R11``); se non basta a coprire/chiudere il
giro, allarga con criterio (materiali compatibili, linee adiacenti,
vuoti di rientro/posizionamento). NON ignora la regola — la **degrada
in modo controllato** scendendo lungo i tier.

In MR-A1 questo modulo contiene SOLO strutture dati e factory dei tier
di default. Nessuna logica di applicazione/scoring: arriva in MR-A3
(``risolvi_corsa_esplorativo``) e MR-A4 (backtracking esplorativo nel
``catena.py`` / ``multi_giornata.py``).

**Coesistenza con `programma_regola_assegnazione.filtri_json`**: il
modulo non SOSTITUISCE i filtri delle regole, ma li **incapsula**
all'interno di un tier 0 (vincolo esatto). I tier successivi sono
generati dal motore esplorativo a partire dal contesto (composizione
ammessa, dotazione, area metropolitana, whitelist sede).

**Naming**: italiano per dominio, coerente con
``schemas/vincoli.py`` (vincoli soste) e
``programma_vincoli_soste`` migration 0039. Modulo separato perché
``schemas/vincoli.py`` è validazione Pydantic, mentre questo è
modello di dominio puro (dataclass + enum, niente serialization).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# =====================================================================
# Enum
# =====================================================================


class TipoVincoloSoft(StrEnum):
    """Tipo di vincolo del programma materiale che può essere rilassato.

    Ogni tipo descrive **cosa** viene vincolato e **come** può essere
    degradato lungo i tier di fallback (vedi ``tier_vincoli_default``).
    """

    #: La corsa deve appartenere alla linea X. Tier 0 (esatto) → tier
    #: 1 (linea adiacente, ovvero linea che condivide almeno 1 stazione
    #: con la regola) → tier 2 (qualsiasi linea con materiale
    #: compatibile, accettando un vuoto di rientro).
    LINEA = "linea"

    #: La corsa deve essere coperta dal materiale tipo X. Tier 0
    #: (esatto) → tier 1 (materiale dello stesso "famiglia accoppiabile"
    #: configurata in ``materiale_accoppiamento_ammesso``). Vincolo
    #: forte di norma (la linea ha materiale dichiarato dal pianificatore),
    #: rilassabile solo via override esplicito.
    MATERIALE = "materiale"

    #: Il giro chiude geograficamente nella whitelist della sede. Tier 0
    #: (chiusura naturale: ultima corsa termina in stazione whitelist) →
    #: tier 1 (chiusura con vuoto di rientro a sede) → tier 2 (ciclo
    #: aperto marcato per intervento manuale, decisione utente Q2=b).
    SEDE_CHIUSURA = "sede_chiusura"

    #: Il giro ha lunghezza ``>= n_giornate_min`` (soft, già implementato
    #: in legacy). Tier 0 (≥min) → tier 1 (<min ma chiude in sede e
    #: copre N corse residue, "giro di chiusura").
    DURATA_GIORNATE = "durata_giornate"

    #: Sosta intergiornata diurna ``<= max_sosta_diurna_min``
    #: (vincolo MR-4 entry 224). Hard di default; rilassabile solo se
    #: il programma ha ``max_sosta_diurna_min IS NULL`` (vincolo
    #: disattivato).
    SOSTA_DIURNA = "sosta_diurna"

    #: Servizio per giornata ``>= min_servizio_giornata_pct``
    #: (vincolo MR-4 entry 224). Stesso pattern di SOSTA_DIURNA.
    SERVIZIO_GIORNATA = "servizio_giornata"


class TipoRilassamento(StrEnum):
    """Strategia di rilassamento applicata a un singolo tier.

    Determina come il motore esplorativo decide se accettare il
    rilassamento al passaggio dal tier N al tier N+1.
    """

    #: Preferenza: il rilassamento applica una penalità al punteggio
    #: del giro candidato, ma è sempre accettabile. Usato per vincoli
    #: di ottimalità (es. minimizzare vuoti).
    PREFERENZA = "preferenza"

    #: Fallback governato: il rilassamento è ammesso solo se il tier
    #: precedente ha fallito (nessuna soluzione viable trovata).
    #: Default per vincoli del programma (linea, materiale).
    FALLBACK_GOVERNATO = "fallback_governato"

    #: Hard block: il vincolo è inviolabile in questo tier. Usato per
    #: vincoli forti (capacity dotazione, normativa PdC). Saltare il
    #: tier richiede override esplicito utente.
    HARD_BLOCK = "hard_block"


# =====================================================================
# Dataclass
# =====================================================================


@dataclass(frozen=True)
class VincoloSoft:
    """Istanza concreta di un vincolo soft pesato.

    Attributi:
        tipo: il tipo di vincolo (vedi ``TipoVincoloSoft``).
        valore_target: il valore desiderato dal pianificatore. Tipo libero
            (str/int/list) interpretato dal motore in base a ``tipo``.
            Esempio: ``valore_target="R11"`` con ``tipo=LINEA``.
        peso: penalità applicata al punteggio del giro quando il vincolo
            è rilassato (range tipico 1-100, 0 = irrilevante). Più alto
            = vincolo più importante = builder rilassa più tardi.
        rilassamento: strategia di rilassamento di questo vincolo
            (vedi ``TipoRilassamento``).
        metadata: contesto extra opzionale (es. priorità della regola
            che ha generato il vincolo, id della regola sorgente).
    """

    tipo: TipoVincoloSoft
    valore_target: Any
    peso: int = 50
    rilassamento: TipoRilassamento = TipoRilassamento.FALLBACK_GOVERNATO
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.peso < 0 or self.peso > 100:
            raise ValueError(
                f"VincoloSoft.peso deve essere in [0, 100], ricevuto {self.peso}"
            )


@dataclass(frozen=True)
class Tier:
    """Livello di rilassamento. Lista di vincoli con stessa strategia.

    I tier sono ordinati: il motore esplorativo li applica nell'ordine
    crescente di ``livello`` (0 = vincolo esatto, N = rilassamento
    massimo / marker).

    Attributi:
        livello: ordine del tier (0-based). Più basso = più stringente.
        nome: identificatore human-readable per UI/log (es. "esatto",
            "linea_adiacente", "qualsiasi_linea_con_vuoto").
        vincoli: lista di vincoli soft applicati a questo tier.
        descrizione: spiegazione sintetica per il pianificatore.
    """

    livello: int
    nome: str
    vincoli: tuple[VincoloSoft, ...] = ()
    descrizione: str = ""

    def __post_init__(self) -> None:
        if self.livello < 0:
            raise ValueError(
                f"Tier.livello deve essere >= 0, ricevuto {self.livello}"
            )


# =====================================================================
# Factory tier di default
# =====================================================================


def tier_vincoli_default() -> tuple[Tier, ...]:
    """Ritorna la sequenza di tier di default usata dal motore esplorativo.

    Sequenza ordinata di rilassamento gerarchico (decisione utente
    Q1=b, 2026-05-08):

    - **Tier 0** ``esatto``: la corsa rispetta TUTTI i filtri AND della
      regola del programma (comportamento legacy "rigido"). Nessun
      rilassamento applicato. Default per il primo tentativo del
      builder esplorativo.
    - **Tier 1** ``materiale_compatibile``: la corsa NON matcha la
      regola sulla linea, ma il materiale è compatibile (composizione
      coerente con ``materiale_accoppiamento_ammesso``). Penalty media.
      Usato per allacciare corse di linee diverse della stessa famiglia
      di materiale (es. ETR522 di S5 e S11 nello stesso giro).
    - **Tier 2** ``linea_adiacente``: la corsa è di una linea che
      condivide almeno 1 stazione con la regola del programma (calcolato
      dal motore a partire dal grafo PdE). Penalty più alta del tier 1.
    - **Tier 3** ``qualsiasi_con_vuoto``: il builder accetta corse di
      linee non in regola ma raggiungibili con un vuoto di posizionamento
      (es. da Mi.Centrale a Brescia per allacciare un giro che chiude
      a Cremona). Penalty massima.
    - **Tier 4** ``marker``: nessun rilassamento ulteriore. Se nessun
      tier ha trovato soluzione viable, il giro viene marcato come
      ``ciclo_aperto_irrisolto`` o la corsa resta residua (decisione
      utente Q2=b: tollerati ma marcati per intervento manuale).

    I pesi dei vincoli associati ad ogni tier crescono con il livello
    (penalty cumulativa al punteggio del giro candidato), così che il
    motore preferisca soluzioni a tier basso. I tier sono ``frozen``:
    chi vuole personalizzazione per programma deve ritornare una
    sequenza diversa, non mutare quella di default.

    **Foundation in MR-A1**: questa funzione restituisce solo strutture
    dati. L'integrazione con ``risolvi_corsa.py`` arriva in MR-A3,
    quando ``risolvi_corsa_esplorativo`` consumerà i tier per il
    fallback gerarchico.
    """
    return (
        Tier(
            livello=0,
            nome="esatto",
            vincoli=(),
            descrizione=(
                "Corsa rispetta tutti i filtri AND della regola del "
                "programma (comportamento legacy 'rigido')."
            ),
        ),
        Tier(
            livello=1,
            nome="materiale_compatibile",
            vincoli=(
                VincoloSoft(
                    tipo=TipoVincoloSoft.LINEA,
                    valore_target=None,
                    peso=20,
                    rilassamento=TipoRilassamento.FALLBACK_GOVERNATO,
                ),
            ),
            descrizione=(
                "Linea non in regola, ma materiale compatibile via "
                "materiale_accoppiamento_ammesso."
            ),
        ),
        Tier(
            livello=2,
            nome="linea_adiacente",
            vincoli=(
                VincoloSoft(
                    tipo=TipoVincoloSoft.LINEA,
                    valore_target=None,
                    peso=40,
                    rilassamento=TipoRilassamento.FALLBACK_GOVERNATO,
                ),
            ),
            descrizione=(
                "Linea con almeno 1 stazione in comune con la regola "
                "del programma (grafo PdE)."
            ),
        ),
        Tier(
            livello=3,
            nome="qualsiasi_con_vuoto",
            vincoli=(
                VincoloSoft(
                    tipo=TipoVincoloSoft.LINEA,
                    valore_target=None,
                    peso=70,
                    rilassamento=TipoRilassamento.FALLBACK_GOVERNATO,
                ),
                VincoloSoft(
                    tipo=TipoVincoloSoft.SEDE_CHIUSURA,
                    valore_target="con_vuoto",
                    peso=60,
                    rilassamento=TipoRilassamento.PREFERENZA,
                ),
            ),
            descrizione=(
                "Linea fuori regola raggiungibile con vuoto di "
                "posizionamento. Penalty massima sulla linea + costo vuoto."
            ),
        ),
        Tier(
            livello=4,
            nome="marker",
            vincoli=(
                VincoloSoft(
                    tipo=TipoVincoloSoft.SEDE_CHIUSURA,
                    valore_target="ciclo_aperto_irrisolto",
                    peso=100,
                    rilassamento=TipoRilassamento.HARD_BLOCK,
                ),
            ),
            descrizione=(
                "Nessuna soluzione trovata. Giro marcato per intervento "
                "manuale (decisione utente Q2=b)."
            ),
        ),
    )


__all__ = [
    "Tier",
    "TipoRilassamento",
    "TipoVincoloSoft",
    "VincoloSoft",
    "tier_vincoli_default",
]
