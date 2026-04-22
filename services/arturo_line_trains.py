"""
ARTURO Line Trains — discovery di treni reali su una tratta abilitata.

Il builder non si limita piu' ai segmenti del DB material_turn (importati
da PDF): quando una linea e' abilitata nel deposito (STEP 0 abilitazioni),
chiama l'API live.arturo.travel cerca_tratta per scoprire TUTTI i treni
reali che circolano tra da/a. Questi treni vengono offerti al builder
come pool aggiuntivo, in particolare per:
- Seed produttivi su linee non-del-giro-principale (es. ASTI-MILANO da
  ALESSANDRIA dopo posizionamento)
- Rientri in vettura quando il DB material non ha un treno compatibile

Cache TTL 24h: la tabella arturo_line_cache tiene le risposte, re-fetchate
solo se piu' vecchie. Rate limit ARTURO 30/min gestito implicitamente.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional

from services import arturo_client
from src.database.db import Database


CACHE_TTL_HOURS = 24
TABLE_NAME = "arturo_line_cache"


def _ensure_table(db: Database) -> None:
    """Crea tabella cache idempotente."""
    cur = db._cursor()
    if db.is_pg:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id SERIAL PRIMARY KEY,
                from_station TEXT NOT NULL,
                to_station TEXT NOT NULL,
                quando TEXT NOT NULL DEFAULT 'oggi',
                treni_json TEXT NOT NULL,
                n_treni INTEGER NOT NULL DEFAULT 0,
                fetched_at TEXT NOT NULL,
                UNIQUE (from_station, to_station, quando)
            )
        """)
    else:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_station TEXT NOT NULL,
                to_station TEXT NOT NULL,
                quando TEXT NOT NULL DEFAULT 'oggi',
                treni_json TEXT NOT NULL,
                n_treni INTEGER NOT NULL DEFAULT 0,
                fetched_at TEXT NOT NULL,
                UNIQUE (from_station, to_station, quando)
            )
        """)
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_pair "
                f"ON {TABLE_NAME}(from_station, to_station)")
    db.conn.commit()


def get_or_fetch_line(db: Database, from_station: str, to_station: str,
                     quando: str = "oggi",
                     force_refresh: bool = False) -> list[dict]:
    """
    Ritorna lista treni normalizzati per la tratta (from -> to).
    Formato compatibile col pool builder:
      [{"train_id", "from_station", "to_station", "dep_time",
        "arr_time", "confidence", "source": "arturo"}]
    Cache TTL 24h. Se fetch fallisce, ritorna [] (non bloccante).
    """
    _ensure_table(db)
    fu = (from_station or "").upper().strip()
    tu = (to_station or "").upper().strip()
    if not fu or not tu or fu == tu:
        return []

    # 1) Cache
    cur = db._cursor()
    if not force_refresh:
        cur.execute(db._q(
            f"SELECT treni_json, fetched_at FROM {TABLE_NAME} "
            f"WHERE from_station = ? AND to_station = ? AND quando = ?"
        ), (fu, tu, quando))
        row = cur.fetchone()
        if row:
            d = db._dict(row)
            fetched_at = d.get("fetched_at", "")
            try:
                fetched_dt = datetime.fromisoformat(fetched_at)
                if datetime.now() - fetched_dt < timedelta(hours=CACHE_TTL_HOURS):
                    try:
                        return json.loads(d["treni_json"])
                    except Exception:
                        pass
            except Exception:
                pass

    # 2) API fetch
    try:
        res = arturo_client.cerca_tratta(fu, tu, quando)
    except Exception:
        return []
    if not isinstance(res, dict):
        return []
    treni_raw = res.get("risultati", []) or []
    treni_norm: list[dict] = []
    for t in treni_raw:
        if not isinstance(t, dict):
            continue
        numero = (t.get("numero") or "").strip()
        dep = (t.get("orario_programmato") or "").strip()
        if not numero or not dep:
            continue
        # Normalizza a HH:MM
        if len(dep) > 5:
            dep = dep[:5]
        # Per l'arrivo: cerca_tratta ritorna solo partenza; chiama treno()
        # per avere l'arrivo. MA chiamare 30+ volte e' costoso. Salta: il
        # builder puo' fare verify_turn_via_api per arricchire poi.
        # Arr stimato nullo -> il builder puo' chiamare treno(numero) in
        # seconda passata se sceglie questo seed.
        treni_norm.append({
            "train_id": numero,
            "from_station": fu,
            "to_station": tu,
            "dep_time": dep,
            "arr_time": "",  # da completare via treno(numero) se scelto
            "confidence": 0.9,
            "source": "arturo",
            "categoria": t.get("categoria", ""),
            "affidabilita_pct": (t.get("affidabilita") or {}).get("puntualita_pct", 0),
        })

    # 3) Save cache (anche se vuota, per evitare re-fetch a vuoto)
    now = datetime.now().isoformat()
    payload = json.dumps(treni_norm)
    try:
        if db.is_pg:
            cur.execute(db._q(
                f"INSERT INTO {TABLE_NAME} "
                f"(from_station, to_station, quando, treni_json, n_treni, fetched_at) "
                f"VALUES (?,?,?,?,?,?) "
                f"ON CONFLICT (from_station, to_station, quando) "
                f"DO UPDATE SET treni_json = EXCLUDED.treni_json, "
                f"              n_treni = EXCLUDED.n_treni, "
                f"              fetched_at = EXCLUDED.fetched_at"
            ), (fu, tu, quando, payload, len(treni_norm), now))
        else:
            cur.execute(
                f"INSERT OR REPLACE INTO {TABLE_NAME} "
                f"(from_station, to_station, quando, treni_json, n_treni, fetched_at) "
                f"VALUES (?,?,?,?,?,?)",
                (fu, tu, quando, payload, len(treni_norm), now))
        db.conn.commit()
    except Exception:
        pass
    return treni_norm


def _estimate_duration_from_db(db: Database, from_st: str, to_st: str) -> int:
    """
    Stima durata mediana (in minuti) di una tratta dal DB train_segment.
    Utile per completare arr_time dei treni ARTURO che hanno solo dep_time.
    Ritorna 0 se nessun dato.
    """
    cur = db._cursor()
    try:
        cur.execute(db._q(
            "SELECT dep_time, arr_time FROM train_segment "
            "WHERE UPPER(from_station) = ? AND UPPER(to_station) = ? "
            "AND confidence > 0.5 LIMIT 50"
        ), (from_st.upper().strip(), to_st.upper().strip()))
        rows = cur.fetchall()
    except Exception:
        return 0
    durs: list[int] = []
    for r in rows:
        d = db._dict(r)
        dep, arr = d.get("dep_time", ""), d.get("arr_time", "")
        if not dep or not arr or ":" not in dep or ":" not in arr:
            continue
        try:
            dh, dm = map(int, dep.split(":"))
            ah, am = map(int, arr.split(":"))
            d_min = dh * 60 + dm
            a_min = ah * 60 + am
            if a_min < d_min:
                a_min += 1440
            dur = a_min - d_min
            if 5 <= dur <= 300:
                durs.append(dur)
        except Exception:
            continue
    if not durs:
        return 0
    durs.sort()
    return durs[len(durs) // 2]  # mediana


def _load_material_train_ids(db: Database) -> set:
    """Carica il set di train_id presenti nel DB material (parser PDF
    Trenord). Usato per cross-check: ARTURO ritorna TUTTI i treni di una
    tratta (Trenord, Trenitalia, Frecce, IC); solo quelli presenti nel
    materiale Trenord sono validi per i turni PdC Trenord."""
    cur = db._cursor()
    try:
        cur.execute("SELECT DISTINCT train_id FROM train_segment "
                    "WHERE train_id IS NOT NULL AND train_id != ''")
        return {(r["train_id"] if isinstance(r, dict) else r[0] or "").strip()
                for r in cur.fetchall()}
    except Exception:
        return set()


def enrich_pool_with_arturo(db: Database, deposito: str,
                             enabled_lines: set,
                             complete_arr: bool = True,
                             restrict_to_trenord: bool = True) -> list[dict]:
    """
    Per ogni linea abilitata, chiama cerca_tratta in entrambe le direzioni e
    ritorna un pool flat di segmenti ARTURO pronti per essere mischiati ai
    segmenti DB.

    enabled_lines: set di tuple (A, B) normalizzate alfabeticamente come
    da db.get_enabled_lines(deposito).

    complete_arr: se True (default), stima arr_time via durata mediana della
    tratta dal DB. Il builder vedra' segmenti completi. Falsi positivi
    possibili sulle durate, ma _verify_turn_via_api dopo la generazione
    ricarica gli orari veri via treno(numero).

    restrict_to_trenord: se True (default), filtra i treni ARTURO
    mantenendo solo quelli con train_id presente nel DB material (parser
    PDF Trenord). Evita di assegnare al PdC Trenord treni di Trenitalia
    o altri operatori (es. Freccia 2303 Milano-Salerno che passa per
    Alessandria ma non e' Trenord).
    """
    out: list[dict] = []
    # Cache durate per evitare query ripetute
    dur_cache: dict = {}
    dep_upper = (deposito or "").upper().strip()
    # Set train_id Trenord per cross-check
    trenord_tids: set = _load_material_train_ids(db) if restrict_to_trenord else set()

    # ── 1) Linee abilitate: entrambe le direzioni ──
    tratte: set = set()
    for (a, b) in enabled_lines:
        au, bu = a.upper().strip(), b.upper().strip()
        if not au or not bu or au == bu:
            continue
        tratte.add((au, bu))
        tratte.add((bu, au))
        # ── 2) Bridge deposito -> endpoints per posizionamento in vettura ──
        # Se una linea abilitata tocca X ma non parte dal deposito (es.
        # ASTI-MILANO su deposito ALE), il PdC deve poter salire passivo
        # su un treno ALE->ASTI per posizionarsi. Aggiungo le tratte
        # deposito <-> endpoint anche se non abilitate.
        if dep_upper and dep_upper not in (au, bu):
            for endpoint in (au, bu):
                if endpoint and endpoint != dep_upper:
                    tratte.add((dep_upper, endpoint))
                    tratte.add((endpoint, dep_upper))

    for src, dst in tratte:
        treni = get_or_fetch_line(db, src, dst, "oggi")
        if not treni:
            continue
        # Cross-check Trenord: i treni il cui train_id NON e' nel DB
        # material (Trenitalia / Frecce / IC / regionali di altri operatori)
        # vengono marcati is_deadhead=True. Il PdC Trenord puo' salirvi
        # come passeggero (vettura passiva) per posizionamento o rientro,
        # ma NON puo' guidarli (condotta produttiva -> solo Trenord).
        if restrict_to_trenord and trenord_tids:
            for t in treni:
                tid = (t.get("train_id", "") or "").strip()
                if tid not in trenord_tids:
                    t["is_deadhead"] = True
                    t["not_trenord"] = True
                else:
                    t["is_deadhead"] = False
        if complete_arr:
            key = (src, dst)
            if key not in dur_cache:
                db_dur = _estimate_duration_from_db(db, src, dst)
                # Fallback: se DB non ha dati (linea non presente nel material),
                # stima via arturo_client.treno(primo_numero) per avere durata
                # reale. Cost: 1 chiamata API per tratta nuova (cached dopo).
                if db_dur == 0 and treni:
                    try:
                        from services.train_route_cache import get_or_fetch_train_route
                        sample = treni[0]
                        route = get_or_fetch_train_route(
                            db, sample["train_id"], origine_hint=src,
                        )
                        if route and route.get("api_status") == "ok":
                            ferm = route.get("fermate", []) or []
                            # Trova indici src e dst in fermate
                            def _norm(x): return (x or "").upper().strip()
                            src_idx = next((i for i, f in enumerate(ferm)
                                            if _norm(f.get("stazione_nome", "")) == src), -1)
                            dst_idx = next((i for i, f in enumerate(ferm)
                                            if _norm(f.get("stazione_nome", "")) == dst), -1)
                            if 0 <= src_idx < dst_idx:
                                f_src = ferm[src_idx]
                                f_dst = ferm[dst_idx]
                                dep_ts = f_src.get("programmato_partenza") or ""
                                arr_ts = f_dst.get("programmato_arrivo") or ""
                                if len(dep_ts) >= 16 and len(arr_ts) >= 16:
                                    dh, dm = int(dep_ts[11:13]), int(dep_ts[14:16])
                                    ah, am = int(arr_ts[11:13]), int(arr_ts[14:16])
                                    d = (ah * 60 + am) - (dh * 60 + dm)
                                    if d < 0:
                                        d += 1440
                                    if 5 <= d <= 300:
                                        db_dur = d
                    except Exception:
                        pass
                # Ultimo fallback: 60min default (meglio di scartare il treno)
                if db_dur == 0:
                    db_dur = 60
                dur_cache[key] = db_dur
            dur = dur_cache[key]
            if dur > 0:
                for t in treni:
                    if t.get("arr_time"):
                        continue
                    dep = t.get("dep_time", "")
                    if ":" not in dep:
                        continue
                    try:
                        dh, dm = map(int, dep.split(":"))
                        arr_m = dh * 60 + dm + dur
                        arr_m = arr_m % 1440
                        t["arr_time"] = f"{arr_m // 60:02d}:{arr_m % 60:02d}"
                        t["arr_estimated"] = True
                    except Exception:
                        continue
        out.extend(treni)
    # Solo treni con arr_time impostato (se la stima e' fallita vengono scartati)
    return [t for t in out if t.get("arr_time")]


def complete_arr_time(db: Database, train_id: str, from_station: str) -> str:
    """
    Dato un treno ARTURO (solo dep_time noto), chiama l'API treno() per
    ottenere l'arr_time alla stazione di arrivo. Ritorna HH:MM o ''.
    """
    from services.train_route_cache import get_or_fetch_train_route
    try:
        route = get_or_fetch_train_route(db, train_id, origine_hint=from_station)
        if not route or route.get("api_status") != "ok":
            return ""
        fermate = route.get("fermate", []) or []
        if not fermate:
            return ""
        # Ultimo fermata = destinazione
        last = fermate[-1]
        prog_arr = last.get("programmato_arrivo") or ""
        if prog_arr and len(prog_arr) >= 16:
            return prog_arr[11:16]
    except Exception:
        pass
    return ""
