"""Strato 0 — anagrafica.

Entità di base condivise da tutti gli strati: aziende, stazioni,
materiali, località manutenzione, depositi PdC, e tabelle associative.

Vedi `docs/SCHEMA-DATI-NATIVO.md` §3 e migrazione 0001 per i dettagli.
"""

from datetime import date, datetime, time
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric as sa_Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from colazione.db import Base


class Azienda(Base):
    __tablename__ = "azienda"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codice: Mapped[str] = mapped_column(String(50), unique=True)
    nome: Mapped[str] = mapped_column(Text)
    normativa_pdc_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_attiva: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Stazione(Base):
    __tablename__ = "stazione"

    codice: Mapped[str] = mapped_column(String(20), primary_key=True)
    nome: Mapped[str] = mapped_column(Text)
    nomi_alternativi_json: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    rete: Mapped[str | None] = mapped_column(String(10))
    is_sede_deposito: Mapped[bool] = mapped_column(Boolean, default=False)
    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MaterialeTipo(Base):
    __tablename__ = "materiale_tipo"

    codice: Mapped[str] = mapped_column(String(50), primary_key=True)
    nome_commerciale: Mapped[str | None] = mapped_column(Text)
    famiglia: Mapped[str | None] = mapped_column(Text)
    componenti_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    velocita_max_kmh: Mapped[int | None] = mapped_column(Integer)
    posti_per_pezzo: Mapped[int | None] = mapped_column(Integer)
    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="RESTRICT")
    )
    # Sede manutentiva di default per il rotabile (Sprint 5.1, migration 0007).
    # Nullable: configurato dal pianificatore via UI/seed. Usato come fallback
    # quando una regola non specifica la sede.
    localita_manutenzione_default_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("localita_manutenzione.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LocalitaManutenzione(Base):
    __tablename__ = "localita_manutenzione"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codice: Mapped[str] = mapped_column(String(80), unique=True)
    # Codice breve (max 8 char, ^[A-Z]{2,8}$) usato per generare il
    # `numero_turno` dei giri secondo convenzione `G-{LOC_BREVE}-{NNN}`.
    # Aggiunto in migration 0006 (Sprint 4.4.5b).
    codice_breve: Mapped[str] = mapped_column(String(8))
    nome_canonico: Mapped[str] = mapped_column(Text)
    nomi_alternativi_json: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    stazione_collegata_codice: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("stazione.codice", ondelete="SET NULL")
    )
    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="RESTRICT")
    )
    is_pool_esterno: Mapped[bool] = mapped_column(Boolean, default=False)
    azienda_proprietaria_esterna: Mapped[str | None] = mapped_column(String(100))
    is_attiva: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LocalitaManutenzioneDotazione(Base):
    __tablename__ = "localita_manutenzione_dotazione"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    localita_manutenzione_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("localita_manutenzione.id", ondelete="CASCADE")
    )
    materiale_tipo_codice: Mapped[str] = mapped_column(
        String(50), ForeignKey("materiale_tipo.codice", ondelete="RESTRICT")
    )
    quantita: Mapped[int] = mapped_column(Integer)
    famiglia_rotabile: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Depot(Base):
    __tablename__ = "depot"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codice: Mapped[str] = mapped_column(String(80), unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="RESTRICT")
    )
    stazione_principale_codice: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("stazione.codice", ondelete="SET NULL")
    )
    tipi_personale_ammessi: Mapped[str] = mapped_column(String(20), default="PdC")
    is_attivo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DepotLineaAbilitata(Base):
    __tablename__ = "depot_linea_abilitata"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    depot_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("depot.id", ondelete="CASCADE"))
    stazione_a_codice: Mapped[str] = mapped_column(String(20), ForeignKey("stazione.codice"))
    stazione_b_codice: Mapped[str] = mapped_column(String(20), ForeignKey("stazione.codice"))


class DepotMaterialeAbilitato(Base):
    __tablename__ = "depot_materiale_abilitato"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    depot_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("depot.id", ondelete="CASCADE"))
    materiale_tipo_codice: Mapped[str] = mapped_column(
        String(50), ForeignKey("materiale_tipo.codice", ondelete="RESTRICT")
    )


class LocalitaStazioneVicina(Base):
    """Whitelist M:N stazioni-vicine-sede (Sprint 5.1, migration 0007).

    Per ogni sede manutentiva, l'insieme di stazioni in cui sono ammessi
    i vuoti tecnici di posizionamento. Vedi
    `docs/SPRINT-5-RIPENSAMENTO.md` §3 e §5.3 per la motivazione e la
    logica di consumo nel builder.

    Una stazione può appartenere a più sedi (es. Saronno per NOV+CAM).
    """

    __tablename__ = "localita_stazione_vicina"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    localita_manutenzione_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("localita_manutenzione.id", ondelete="CASCADE")
    )
    stazione_codice: Mapped[str] = mapped_column(
        String(20), ForeignKey("stazione.codice", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FestivitaUfficiale(Base):
    """Calendario ufficiale festività (Sprint 7.7 MR 2, migration 0015).

    Una riga per ogni giorno NON-feriale che NON è pura conseguenza
    del weekday (sabato/domenica si calcolano dal `data.weekday()`).
    Riguarda quindi solo:

    - Festività nazionali italiane (10 fisse + Pasqua + Pasquetta)
    - Festività locali per azienda/regione (Sant'Ambrogio per Trenord)
    - Eventuali ricorrenze speciali per programma (oggi non usate)

    `azienda_id` NULL = festività universale (nazionale).
    `azienda_id` valorizzato = festività specifica per quell'azienda
    (es. patrono locale).

    Il builder usa questa tabella + `domain/calendario.tipo_giorno()`
    per classificare ogni data come feriale/sabato/domenica/festivo,
    propedeutico al refactor "varianti → giri separati" (Sprint 7.7.3).
    """

    __tablename__ = "festivita_ufficiale"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    azienda_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="CASCADE")
    )
    data: Mapped[date] = mapped_column(Date, index=True)
    nome: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(String(20), default="nazionale")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MaterialeAccoppiamentoAmmesso(Base):
    """Coppie ammesse di rotabili in doppia composizione
    (Sprint 5.1, migration 0007).

    Normalizzata lessicograficamente (`materiale_a_codice <=
    materiale_b_codice`) per garantire unicità simmetrica: una sola
    riga per coppia, indipendentemente dall'ordine di inserimento.

    Esempi: ETR421+ETR421, ETR526+ETR526, ETR526+ETR425. La lista cresce
    nel tempo; per ora questi 3 sono il seed Sprint 5.2.

    Override manuale: la regola `programma_regola_assegnazione` può
    avere `is_composizione_manuale=True` per bypassare il check su
    questa tabella (override pianificatore per composizioni custom).
    """

    __tablename__ = "materiale_accoppiamento_ammesso"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    materiale_a_codice: Mapped[str] = mapped_column(
        String(50), ForeignKey("materiale_tipo.codice", ondelete="RESTRICT")
    )
    materiale_b_codice: Mapped[str] = mapped_column(
        String(50), ForeignKey("materiale_tipo.codice", ondelete="RESTRICT")
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LocalitaSosta(Base):
    """Sprint 7.9 MR β2-0: deposito di SOSTA INTERMEDIA, distinto dai
    depositi di manutenzione (``localita_manutenzione``).

    Esempio canonico: Milano San Rocco (codice ``MISR``), scalo
    dedicato per soste notturne/lunghe (>2h) come overflow di Milano
    Porta Garibaldi che non ha capacità di sosta lunga. I materiali
    ATR125/ATR115/ETR421 sganciati a Garibaldi vengono inviati qui.

    Distinzione semantica da ``LocalitaManutenzione``:
    - ``LocalitaSosta``: solo sosta tecnica, niente manutenzione, niente
      whitelist stazioni vicine, niente uscita/rientro deposito 9XXXX.
    - ``LocalitaManutenzione``: sede produttiva del materiale, fa
      manutenzione, ha whitelist stazioni vicine, è la "casa" del
      convoglio per il giro materiale.

    Decisione utente 2026-05-04: anagrafica globale per azienda (la
    sosta MISR esiste sempre per Trenord, configurabile in admin),
    poi le regole d'invio (``RegolaInvioSosta``) decidono per ogni
    programma quando inviare a quale sosta.
    """

    __tablename__ = "localita_sosta"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    codice: Mapped[str] = mapped_column(String(40))  # es. "MISR"
    nome: Mapped[str] = mapped_column(Text)
    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="RESTRICT")
    )
    # Stazione di proxy commerciale (es. MISR ↔ MILANO PORTA GARIBALDI)
    # — il convoglio "arriva" a questa stazione per essere considerato
    # in sosta presso la località.
    stazione_collegata_codice: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("stazione.codice", ondelete="SET NULL")
    )
    is_attiva: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("azienda_id", "codice", name="uq_localita_sosta_azienda_codice"),
    )


class RegolaInvioSosta(Base):
    """Sprint 7.9 MR β2-0: regola operativa che decide DOVE mandare un
    materiale sganciato a una stazione X durante una finestra oraria.

    Esempio: "ATR125 sganciato a Milano Porta Garibaldi tra 06:00 e
    19:00 → invia a Milano San Rocco". Oppure "ETR421 sganciato a
    Garibaldi dopo le 19:00 → invia a Misr (preferito) con fallback
    a Fiorenza per rientro manutenzione".

    Ambito: per programma (decisione utente 2026-05-04 confermata in
    domanda 3 design β2-7). Le regole "universali" che valgono per
    tutti i programmi Trenord vanno modellate separatamente come
    `RegolaInvioSostaAzienda` (scope futuro β2-7); per ora questa
    tabella copre il caso "regola di programma".

    Vincoli:
    - Finestra oraria può attraversare mezzanotte (es. 22:00→04:00).
      L'algoritmo di matching deve gestire il caso ``inizio > fine``
      come "fascia notturna che gira la mezzanotte".
    - ``fallback_sosta_id`` opzionale: se la sosta principale è satura
      (capacity check futuro), si invia al fallback.
    """

    __tablename__ = "regola_invio_sosta"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    programma_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("programma_materiale.id", ondelete="CASCADE"),
    )
    # Stazione dove avviene lo sgancio (es. S01645 = Milano Porta Garibaldi).
    stazione_sgancio_codice: Mapped[str] = mapped_column(
        String(20), ForeignKey("stazione.codice", ondelete="RESTRICT")
    )
    # Tipo materiale a cui la regola si applica (es. "ETR421", "ATR125").
    tipo_materiale_codice: Mapped[str] = mapped_column(
        String(50), ForeignKey("materiale_tipo.codice", ondelete="RESTRICT")
    )
    # Finestra oraria di applicazione (es. 06:00-19:00 = "diurna",
    # 19:00-23:59 = "serale"). Può attraversare la mezzanotte.
    finestra_oraria_inizio: Mapped[time] = mapped_column(Time)
    finestra_oraria_fine: Mapped[time] = mapped_column(Time)
    # Sosta principale di destinazione.
    localita_sosta_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("localita_sosta.id", ondelete="RESTRICT")
    )
    # Sosta di fallback se la principale è satura (capacity check futuro).
    fallback_sosta_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("localita_sosta.id", ondelete="RESTRICT")
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MaterialeThread(Base):
    """Sprint 7.9 MR β2-4: thread logico (L2) di un singolo "pezzo" di
    materiale dentro un giro materiale.

    Concetto: quando 2 ETR526 viaggiano accoppiati (composizione di
    2 pezzi sullo stesso treno commerciale), sono DUE thread logici
    distinti. Ogni thread ha la sua sequenza temporale di eventi
    (corsa singolo, corsa doppia, sosta in stazione, vuoto solo,
    aggancio, sgancio, rientro deposito).

    Decisione utente 2026-05-04:

    > "Quando 2 ETR526 viaggiano accoppiati nello stesso treno, sono
    > due materiali distinti che fanno cose anche diverse nel tempo
    > (uno può essere agganciato a metà giornata, l'altro sganciato
    > altrove). Vogliamo tracciare ogni singolo pezzo continuo nei km,
    > dalla nascita al rientro, anche quando si fonde/separa da
    > composizioni diverse."

    Relazioni:
    - ``giro_materiale_id_origine``: il giro che ha "creato" questo
      thread (= thread proiettato dall'algoritmo β2-4 a partire da
      una catena di quel giro). Un thread può attraversare più giri
      se viaggia tramite agganci/sganci, ma la sua origine è un giro
      specifico.
    - ``matricola_id``: opzionale. Quando il ruolo Manutenzione
      assegna il telaio fisico al thread, questa FK punta a una
      ``MaterialeIstanza``. Per il pianificatore Giro Materiale resta
      sempre NULL (è anonimo per lui).

    Stats:
    - ``km_totali``: somma km_tratta di tutte le corse commerciali
      che il pezzo ha eseguito nel thread (= km del singolo pezzo
      fisico nel ciclo, utile a Manutenzione per programmare revisioni).
    """

    __tablename__ = "materiale_thread"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="RESTRICT")
    )
    programma_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("programma_materiale.id", ondelete="CASCADE"),
    )
    giro_materiale_id_origine: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("giro_materiale.id", ondelete="CASCADE")
    )
    tipo_materiale_codice: Mapped[str] = mapped_column(
        String(50), ForeignKey("materiale_tipo.codice", ondelete="RESTRICT")
    )
    matricola_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("materiale_istanza.id", ondelete="SET NULL")
    )
    # Metriche aggregate calcolate dall'algoritmo proiezione.
    km_totali: Mapped[float] = mapped_column(
        sa_Numeric(10, 3), default=0, server_default="0"
    )
    minuti_servizio: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    n_corse_commerciali: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MaterialeThreadEvento(Base):
    """Sprint 7.9 MR β2-4: evento atomico nella timeline di un
    `MaterialeThread`.

    Tipi di evento:
    - ``"corsa_singolo"``: il pezzo da solo svolge una corsa commerciale.
    - ``"corsa_doppia_pos1"`` / ``"corsa_doppia_pos2"``: il pezzo è
      parte di una composizione doppia, posizione 1 (testa) o 2 (coda).
    - ``"corsa_tripla_pos1"`` / ``"_pos2"`` / ``"_pos3"``: tripla
      composizione (es. 3×ETR421).
    - ``"vuoto_solo"``: il pezzo si sposta vuoto da X a Y.
    - ``"sosta_in_stazione"``: il pezzo è parcheggiato in una
      stazione (es. tra sgancio e riaggancio).
    - ``"aggancio"``: marker dell'evento di unione a un'altra
      composizione (puntatore al `giro_blocco` aggancio).
    - ``"sgancio"``: marker di separazione.
    - ``"uscita_deposito"``: il pezzo esce per la prima volta.
    - ``"rientro_deposito"``: chiusura ciclo, rientra in officina.

    L'``ordine`` è progressivo dentro il thread (1-based). Per ogni
    thread è garantita continuità geografica:
    ``stazione_a[i] == stazione_da[i+1]`` (con possibile sosta o
    vuoto fra i due se la stazione cambia).
    """

    __tablename__ = "materiale_thread_evento"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    thread_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("materiale_thread.id", ondelete="CASCADE")
    )
    ordine: Mapped[int] = mapped_column(Integer)  # progressivo 1-based
    tipo: Mapped[str] = mapped_column(String(30))
    # Riferimento al blocco originale del giro (per back-link UI).
    giro_blocco_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("giro_blocco.id", ondelete="SET NULL")
    )
    stazione_da_codice: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("stazione.codice", ondelete="SET NULL")
    )
    stazione_a_codice: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("stazione.codice", ondelete="SET NULL")
    )
    ora_inizio: Mapped[time | None] = mapped_column(Time)
    ora_fine: Mapped[time | None] = mapped_column(Time)
    data_giorno: Mapped[date | None] = mapped_column(Date)
    # km tratta (per corse commerciali) o NULL (per sosta/vuoto/marker).
    km_tratta: Mapped[float | None] = mapped_column(sa_Numeric(10, 3))
    # Numero treno commerciale (corsa) o virtuale 9XXX (vuoto), opaco
    # per gli altri tipi.
    numero_treno: Mapped[str | None] = mapped_column(String(20))
    # Note libere (es. "Aggancio +1 ETR526 da treno 24812 a CENTRALE 09:55").
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("thread_id", "ordine", name="uq_thread_evento_ordine"),
    )


class MaterialeIstanza(Base):
    """Sprint 7.9 MR β2-1: istanza fisica (L3) di un materiale.

    Decisione utente 2026-05-04: introduciamo da subito il livello L3
    (istanza fisica) anche se il ruolo Manutenzione che lo userà
    davvero arriva in Sprint successivo. Schema semplifica i futuri
    `MaterialeThread` che potranno opzionalmente puntare a una
    matricola specifica.

    Convenzione matricola: ``{TIPO}-{NNN}`` zero-padded a 3 cifre.
    Esempi: ``ETR526-000``, ``ETR526-001``, ..., ``ETR526-010`` (per
    dotazione = 11). Univocità per ``(azienda_id, matricola)`` —
    diverse aziende possono avere matricole identiche, ma dentro
    un'azienda no.

    ``sede_codice`` è NULLABLE: al seed iniziale l'istanza è
    "non assegnata" (sarà la Manutenzione ad assegnare il telaio fisico
    alla sede produttiva quando attivata la feature). Nel `MaterialeThread`
    invece la sede è quella del giro che ha generato il thread.

    Stato:
    - ``"attivo"``: istanza disponibile per l'assegnazione (default).
    - ``"in_revisione"``: temporaneamente fuori servizio (revisione
      programmata).
    - ``"fuori_servizio"``: dismessa (mantenuta per storico thread).
    """

    __tablename__ = "materiale_istanza"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="RESTRICT")
    )
    tipo_materiale_codice: Mapped[str] = mapped_column(
        String(50), ForeignKey("materiale_tipo.codice", ondelete="RESTRICT")
    )
    matricola: Mapped[str] = mapped_column(String(40))
    sede_codice: Mapped[str | None] = mapped_column(
        String(80), ForeignKey("localita_manutenzione.codice", ondelete="SET NULL")
    )
    stato: Mapped[str] = mapped_column(String(20), default="attivo")
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "azienda_id", "matricola", name="uq_materiale_istanza_azienda_matricola"
        ),
    )


class MaterialeDotazioneAzienda(Base):
    """Sprint 7.9 MR 7D: dotazione fisica per (azienda, materiale).

    Rappresenta il numero di pezzi singoli che un'azienda possiede di
    un certo tipo di materiale. Usato dalla dashboard "Convogli
    necessari" per warning di capacity.

    ``pezzi_disponibili = NULL`` → capacity illimitata (es. ETR524
    FLIRT TILO copre tutti i turni TILO senza un numero specifico).

    PK composta `(azienda_id, materiale_codice)` — al massimo 1 riga
    per coppia.
    """

    __tablename__ = "materiale_dotazione_azienda"

    azienda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("azienda.id", ondelete="CASCADE"), primary_key=True
    )
    materiale_codice: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("materiale_tipo.codice", ondelete="RESTRICT"),
        primary_key=True,
    )
    pezzi_disponibili: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
