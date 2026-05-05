"""Test integration API endpoint conferma pipeline — Sprint 8.0 MR 0
(entry 164).

Copre i 6 endpoint introdotti nello stesso MR + filtraggio list per
ruolo (vedi ``api/programmi.py`` e ``domain/pipeline.py``).

Setup: utenti di test creati on-the-fly per i 4 ruoli pipeline (oltre
ad ``admin`` + ``pianificatore_giro_demo`` già seedati). Vengono
ripuliti dal fixture ``cleanup_users``.
"""

from __future__ import annotations

import os
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from colazione.auth.password import hash_password
from colazione.db import dispose_engine, session_scope
from colazione.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_DB_TESTS") == "1",
    reason="DB not configured for tests",
)


# =====================================================================
# Fixture
# =====================================================================


_PROG_PREFIX = "TEST_PIPELINE_"
_USER_PREFIX = "_test_pipeline_"
_TEST_PASSWORD = "pwd_test_pipeline_8_0"

_TEST_ROLES: tuple[tuple[str, str], ...] = (
    ("pianificatore_pdc", "PIANIFICATORE_PDC"),
    ("gestione_personale", "GESTIONE_PERSONALE"),
    ("manutenzione", "MANUTENZIONE"),
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


async def _wipe_programmi() -> None:
    async with session_scope() as session:
        await session.execute(
            text(
                "DELETE FROM programma_regola_assegnazione WHERE programma_id IN ("
                "  SELECT id FROM programma_materiale WHERE nome LIKE :p"
                ")"
            ),
            {"p": f"{_PROG_PREFIX}%"},
        )
        await session.execute(
            text("DELETE FROM programma_materiale WHERE nome LIKE :p"),
            {"p": f"{_PROG_PREFIX}%"},
        )


async def _ensure_test_users() -> None:
    """Crea (idempotente) gli utenti di test per i 3 ruoli a valle.

    L'utente esiste solo se manca: la migration 0003 seed-a admin +
    pianificatore_giro_demo, qui aggiungiamo i 3 a valle. La password
    bcrypt è ricalcolata ad ogni run (cost 12) ma è stabile fra test
    grazie all'unicità su ``username``.
    """
    pwd_hash = hash_password(_TEST_PASSWORD)
    async with session_scope() as session:
        for suffix, ruolo in _TEST_ROLES:
            username = f"{_USER_PREFIX}{suffix}"
            # CAST esplicito per evitare l'errore psycopg3 "AmbiguousParameter"
            # (text vs varchar) quando lo stesso parametro è usato in 2 punti
            # con tipi inferiti differenti.
            await session.execute(
                text(
                    "INSERT INTO app_user (username, password_hash, is_admin, "
                    "azienda_id) "
                    "SELECT CAST(:u AS VARCHAR), :h, FALSE, "
                    "  (SELECT id FROM azienda WHERE codice = 'trenord') "
                    "WHERE NOT EXISTS ("
                    "  SELECT 1 FROM app_user WHERE username = CAST(:u AS VARCHAR))"
                ),
                {"u": username, "h": pwd_hash},
            )
            await session.execute(
                text(
                    "INSERT INTO app_user_ruolo (app_user_id, ruolo) "
                    "SELECT u.id, CAST(:r AS VARCHAR) FROM app_user u "
                    "WHERE u.username = CAST(:u AS VARCHAR) "
                    "  AND NOT EXISTS ("
                    "    SELECT 1 FROM app_user_ruolo r "
                    "    WHERE r.app_user_id = u.id "
                    "      AND r.ruolo = CAST(:r AS VARCHAR))"
                ),
                {"u": username, "r": ruolo},
            )


async def _wipe_test_users() -> None:
    async with session_scope() as session:
        await session.execute(
            text("DELETE FROM app_user WHERE username LIKE :p"),
            {"p": f"{_USER_PREFIX}%"},
        )


@pytest.fixture(scope="module", autouse=True)
async def _module_setup() -> None:
    """Crea utenti di test prima del modulo, li rimuove dopo."""
    await _ensure_test_users()
    yield
    await _wipe_test_users()
    await _wipe_programmi()
    await dispose_engine()


@pytest.fixture(autouse=True)
async def _clean_programmi() -> None:
    await _wipe_programmi()


# =====================================================================
# Helpers
# =====================================================================


def _login(client: TestClient, username: str, password: str) -> str:
    res = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert res.status_code == 200, res.text
    return str(res.json()["access_token"])


def _admin_token(client: TestClient) -> str:
    return _login(client, "admin", "admin12345")


def _ruolo_token(client: TestClient, suffix: str) -> str:
    return _login(client, f"{_USER_PREFIX}{suffix}", _TEST_PASSWORD)


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _crea_programma_in_stato(
    nome_suffix: str,
    stato_pipeline_pdc: str = "PDE_IN_LAVORAZIONE",
    stato_manutenzione: str = "IN_ATTESA",
) -> int:
    """INSERT diretto del programma con lo stato pipeline impostato.

    Bypass dell'API ``POST /programmi`` perché non c'è ancora un endpoint
    per impostare ``stato_pipeline_pdc`` (tutto MR successivi). Per i
    test ci serve seed in stati intermedi.
    """
    async with session_scope() as session:
        row = (
            await session.execute(
                text(
                    "INSERT INTO programma_materiale "
                    "(azienda_id, nome, valido_da, valido_a, stato, "
                    "stato_pipeline_pdc, stato_manutenzione, "
                    "n_giornate_default, n_giornate_min, n_giornate_max, "
                    "fascia_oraria_tolerance_min, strict_options_json, "
                    "stazioni_sosta_extra_json) "
                    "SELECT id, :nome, :da, :a, 'attivo', :sp, :sm, "
                    "1, 4, 12, 30, '{}'::jsonb, '[]'::jsonb "
                    "FROM azienda WHERE codice = 'trenord' "
                    "RETURNING id"
                ),
                {
                    "nome": f"{_PROG_PREFIX}{nome_suffix}",
                    "da": date(2026, 1, 1),
                    "a": date(2026, 12, 31),
                    "sp": stato_pipeline_pdc,
                    "sm": stato_manutenzione,
                },
            )
        ).first()
        assert row is not None
        return int(row[0])


# =====================================================================
# Conferma materiale (PIANIFICATORE_GIRO)
# =====================================================================


async def test_conferma_materiale_da_pde_consolidato_ok(client: TestClient) -> None:
    pid = await _crea_programma_in_stato("conf_mat_ok", "PDE_CONSOLIDATO")
    token = _admin_token(client)
    res = client.post(
        f"/api/programmi/{pid}/conferma-materiale", headers=_h(token)
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["stato_pipeline_pdc"] == "MATERIALE_CONFERMATO"
    # Side effect: ramo manutenzione viene attivato.
    assert body["stato_manutenzione"] == "IN_LAVORAZIONE"


async def test_conferma_materiale_da_materiale_generato_ok(
    client: TestClient,
) -> None:
    pid = await _crea_programma_in_stato("conf_mat_gen", "MATERIALE_GENERATO")
    res = client.post(
        f"/api/programmi/{pid}/conferma-materiale",
        headers=_h(_admin_token(client)),
    )
    assert res.status_code == 200
    assert res.json()["stato_pipeline_pdc"] == "MATERIALE_CONFERMATO"


async def test_conferma_materiale_da_in_lavorazione_400(
    client: TestClient,
) -> None:
    """``PDE_IN_LAVORAZIONE → MATERIALE_CONFERMATO`` non è ammesso."""
    pid = await _crea_programma_in_stato("conf_mat_400", "PDE_IN_LAVORAZIONE")
    res = client.post(
        f"/api/programmi/{pid}/conferma-materiale",
        headers=_h(_admin_token(client)),
    )
    assert res.status_code == 400
    assert "non ammessa" in res.json()["detail"]


async def test_conferma_materiale_non_riattiva_manutenzione_gia_avanzata(
    client: TestClient,
) -> None:
    """Se la manutenzione è già IN_LAVORAZIONE, la confema-materiale non
    la fa regredire."""
    pid = await _crea_programma_in_stato(
        "conf_mat_man",
        stato_pipeline_pdc="MATERIALE_GENERATO",
        stato_manutenzione="IN_LAVORAZIONE",
    )
    res = client.post(
        f"/api/programmi/{pid}/conferma-materiale",
        headers=_h(_admin_token(client)),
    )
    assert res.status_code == 200
    assert res.json()["stato_manutenzione"] == "IN_LAVORAZIONE"


# =====================================================================
# Conferma PdC
# =====================================================================


async def test_conferma_pdc_ok(client: TestClient) -> None:
    pid = await _crea_programma_in_stato("conf_pdc", "PDC_GENERATO")
    res = client.post(
        f"/api/programmi/{pid}/conferma-pdc",
        headers=_h(_admin_token(client)),
    )
    assert res.status_code == 200
    assert res.json()["stato_pipeline_pdc"] == "PDC_CONFERMATO"


async def test_conferma_pdc_403_se_solo_pianificatore_giro(
    client: TestClient,
) -> None:
    """``PIANIFICATORE_GIRO`` non può confermare il PdC: serve PDC."""
    pid = await _crea_programma_in_stato("conf_pdc_403", "PDC_GENERATO")
    token = _login(client, "pianificatore_giro_demo", "demo12345")
    res = client.post(f"/api/programmi/{pid}/conferma-pdc", headers=_h(token))
    assert res.status_code == 403


async def test_conferma_pdc_da_ruolo_dedicato_ok(client: TestClient) -> None:
    pid = await _crea_programma_in_stato(
        "conf_pdc_role", "PDC_GENERATO"
    )
    token = _ruolo_token(client, "pianificatore_pdc")
    res = client.post(f"/api/programmi/{pid}/conferma-pdc", headers=_h(token))
    assert res.status_code == 200


# =====================================================================
# Conferma manutenzione
# =====================================================================


async def test_conferma_manutenzione_ok(client: TestClient) -> None:
    pid = await _crea_programma_in_stato(
        "conf_man",
        stato_pipeline_pdc="MATERIALE_CONFERMATO",
        stato_manutenzione="IN_LAVORAZIONE",
    )
    token = _ruolo_token(client, "manutenzione")
    res = client.post(
        f"/api/programmi/{pid}/conferma-manutenzione", headers=_h(token)
    )
    assert res.status_code == 200
    body = res.json()
    assert body["stato_manutenzione"] == "MATRICOLE_ASSEGNATE"
    # Indipendenza: il ramo PdC non si tocca.
    assert body["stato_pipeline_pdc"] == "MATERIALE_CONFERMATO"


async def test_conferma_manutenzione_da_in_attesa_400(
    client: TestClient,
) -> None:
    pid = await _crea_programma_in_stato(
        "conf_man_400",
        stato_pipeline_pdc="PDE_IN_LAVORAZIONE",
        stato_manutenzione="IN_ATTESA",
    )
    res = client.post(
        f"/api/programmi/{pid}/conferma-manutenzione",
        headers=_h(_admin_token(client)),
    )
    assert res.status_code == 400


# =====================================================================
# Sblocca (admin only)
# =====================================================================


async def test_sblocca_admin_pdc_regredisce(client: TestClient) -> None:
    pid = await _crea_programma_in_stato("sb_pdc", "MATERIALE_CONFERMATO")
    res = client.post(
        f"/api/programmi/{pid}/sblocca",
        json={"ramo": "pdc", "motivo": "test regressione"},
        headers=_h(_admin_token(client)),
    )
    assert res.status_code == 200
    assert res.json()["stato_pipeline_pdc"] == "MATERIALE_GENERATO"


async def test_sblocca_pdc_iniziale_400(client: TestClient) -> None:
    pid = await _crea_programma_in_stato("sb_init", "PDE_IN_LAVORAZIONE")
    res = client.post(
        f"/api/programmi/{pid}/sblocca",
        json={"ramo": "pdc"},
        headers=_h(_admin_token(client)),
    )
    assert res.status_code == 400
    assert "primo stato" in res.json()["detail"]


async def test_sblocca_manutenzione(client: TestClient) -> None:
    pid = await _crea_programma_in_stato(
        "sb_man",
        stato_pipeline_pdc="MATERIALE_CONFERMATO",
        stato_manutenzione="MATRICOLE_ASSEGNATE",
    )
    res = client.post(
        f"/api/programmi/{pid}/sblocca",
        json={"ramo": "manutenzione"},
        headers=_h(_admin_token(client)),
    )
    assert res.status_code == 200
    assert res.json()["stato_manutenzione"] == "IN_LAVORAZIONE"


async def test_sblocca_403_se_non_admin(client: TestClient) -> None:
    pid = await _crea_programma_in_stato("sb_403", "MATERIALE_CONFERMATO")
    token = _login(client, "pianificatore_giro_demo", "demo12345")
    res = client.post(
        f"/api/programmi/{pid}/sblocca",
        json={"ramo": "pdc"},
        headers=_h(token),
    )
    assert res.status_code == 403


# =====================================================================
# Filtro list per ruolo
# =====================================================================


async def test_list_pianificatore_pdc_vede_solo_da_materiale_confermato(
    client: TestClient,
) -> None:
    """Crea 2 programmi (uno sopra, uno sotto soglia) e verifica che il
    PIANIFICATORE_PDC vede solo quello ``>= MATERIALE_CONFERMATO``."""
    pid_basso = await _crea_programma_in_stato(
        "list_pdc_low", "PDE_CONSOLIDATO"
    )
    pid_alto = await _crea_programma_in_stato(
        "list_pdc_high", "MATERIALE_CONFERMATO"
    )

    token = _ruolo_token(client, "pianificatore_pdc")
    res = client.get("/api/programmi", headers=_h(token))
    assert res.status_code == 200
    ids = {p["id"] for p in res.json()}
    assert pid_alto in ids
    assert pid_basso not in ids


async def test_list_admin_vede_tutto(client: TestClient) -> None:
    pid_basso = await _crea_programma_in_stato(
        "list_admin_low", "PDE_IN_LAVORAZIONE"
    )
    pid_alto = await _crea_programma_in_stato(
        "list_admin_high", "PDC_CONFERMATO"
    )
    res = client.get("/api/programmi", headers=_h(_admin_token(client)))
    assert res.status_code == 200
    ids = {p["id"] for p in res.json()}
    assert pid_basso in ids
    assert pid_alto in ids


async def test_get_programma_pdc_404_se_sotto_soglia(
    client: TestClient,
) -> None:
    pid = await _crea_programma_in_stato(
        "get_pdc_low", "PDE_CONSOLIDATO"
    )
    token = _ruolo_token(client, "pianificatore_pdc")
    res = client.get(f"/api/programmi/{pid}", headers=_h(token))
    assert res.status_code == 404


async def test_get_programma_pdc_200_se_alla_soglia(
    client: TestClient,
) -> None:
    pid = await _crea_programma_in_stato(
        "get_pdc_high", "MATERIALE_CONFERMATO"
    )
    token = _ruolo_token(client, "pianificatore_pdc")
    res = client.get(f"/api/programmi/{pid}", headers=_h(token))
    assert res.status_code == 200
    assert res.json()["id"] == pid


async def test_list_gestione_personale_filtra_a_pdc_confermato(
    client: TestClient,
) -> None:
    pid_basso = await _crea_programma_in_stato(
        "list_pers_low", "PDC_GENERATO"
    )
    pid_alto = await _crea_programma_in_stato(
        "list_pers_high", "PDC_CONFERMATO"
    )
    token = _ruolo_token(client, "gestione_personale")
    res = client.get("/api/programmi", headers=_h(token))
    assert res.status_code == 200
    ids = {p["id"] for p in res.json()}
    assert pid_alto in ids
    assert pid_basso not in ids


# =====================================================================
# Freeze read-only post MATERIALE_CONFERMATO (Sprint 8.0 MR 1, entry 165)
# =====================================================================


_PATCH_PAYLOAD = {"km_max_giornaliero": 999}
_REGOLA_PAYLOAD: dict[str, object] = {
    "filtri_json": [{"campo": "codice_linea", "op": "eq", "valore": "S5"}],
    "composizione": [{"materiale_tipo_codice": "ALe711", "n_pezzi": 1}],
    "priorita": 50,
}


async def test_patch_programma_pre_freeze_ok(client: TestClient) -> None:
    """PATCH ok in PDE_IN_LAVORAZIONE."""
    pid = await _crea_programma_in_stato("freeze_patch_pre", "PDE_IN_LAVORAZIONE")
    res = client.patch(
        f"/api/programmi/{pid}",
        json=_PATCH_PAYLOAD,
        headers=_h(_admin_token(client)),
    )
    assert res.status_code == 200, res.text
    assert res.json()["km_max_giornaliero"] == 999


async def test_patch_programma_post_freeze_409(client: TestClient) -> None:
    """PATCH 409 in MATERIALE_CONFERMATO."""
    pid = await _crea_programma_in_stato("freeze_patch_post", "MATERIALE_CONFERMATO")
    res = client.patch(
        f"/api/programmi/{pid}",
        json=_PATCH_PAYLOAD,
        headers=_h(_admin_token(client)),
    )
    assert res.status_code == 409, res.text
    assert "MATERIALE_CONFERMATO" in res.json()["detail"]


async def test_patch_programma_post_freeze_pdc_confermato_409(
    client: TestClient,
) -> None:
    """Freeze attivo anche in stati successivi (PDC_CONFERMATO)."""
    pid = await _crea_programma_in_stato("freeze_patch_pdcc", "PDC_CONFERMATO")
    res = client.patch(
        f"/api/programmi/{pid}",
        json=_PATCH_PAYLOAD,
        headers=_h(_admin_token(client)),
    )
    assert res.status_code == 409


async def test_post_regola_post_freeze_409(client: TestClient) -> None:
    pid = await _crea_programma_in_stato(
        "freeze_regola_post", "MATERIALE_CONFERMATO"
    )
    res = client.post(
        f"/api/programmi/{pid}/regole",
        json=_REGOLA_PAYLOAD,
        headers=_h(_admin_token(client)),
    )
    assert res.status_code == 409


async def test_post_regola_pre_freeze_ok(client: TestClient) -> None:
    pid = await _crea_programma_in_stato("freeze_regola_pre", "PDE_CONSOLIDATO")
    res = client.post(
        f"/api/programmi/{pid}/regole",
        json=_REGOLA_PAYLOAD,
        headers=_h(_admin_token(client)),
    )
    assert res.status_code == 201, res.text


async def test_delete_regola_post_freeze_409(client: TestClient) -> None:
    """Crea regola pre-freeze, confermala (transizione applicativa), poi
    tenta delete: 409."""
    pid = await _crea_programma_in_stato("freeze_del_pre", "PDE_CONSOLIDATO")
    res_create = client.post(
        f"/api/programmi/{pid}/regole",
        json=_REGOLA_PAYLOAD,
        headers=_h(_admin_token(client)),
    )
    assert res_create.status_code == 201
    regola_id = res_create.json()["id"]

    # Avanza il programma a MATERIALE_CONFERMATO via endpoint pipeline.
    res_conf = client.post(
        f"/api/programmi/{pid}/conferma-materiale",
        headers=_h(_admin_token(client)),
    )
    assert res_conf.status_code == 200

    res_del = client.delete(
        f"/api/programmi/{pid}/regole/{regola_id}",
        headers=_h(_admin_token(client)),
    )
    assert res_del.status_code == 409


async def test_genera_giri_post_freeze_409(client: TestClient) -> None:
    """``POST /programmi/{id}/genera-giri`` blocca con 409 dopo
    MATERIALE_CONFERMATO. Niente setup di località/regole: il check
    di freeze precede ``genera_giri()`` quindi il test è independent
    da quegli artefatti.
    """
    pid = await _crea_programma_in_stato(
        "freeze_giri_post", "MATERIALE_CONFERMATO"
    )
    res = client.post(
        f"/api/programmi/{pid}/genera-giri",
        params={"localita_codice": "DUMMY", "force": False},
        headers=_h(_admin_token(client)),
    )
    assert res.status_code == 409
    assert "MATERIALE_CONFERMATO" in res.json()["detail"]


async def _crea_giro_minimo(programma_id: int, codice: str) -> int:
    """INSERT diretto di un giro materiale skeleton, agganciato a
    ``programma_id``. Usato dai test freeze-PdC per avere un
    ``giro_id`` valido senza dover seed-are corse/giornate/blocchi
    (il pre-check di freeze non li tocca). ``localita_manutenzione_partenza_id``
    è obbligatorio: prendiamo la prima località dell'azienda.
    """
    async with session_scope() as session:
        row = (
            await session.execute(
                text(
                    "INSERT INTO giro_materiale "
                    "(azienda_id, programma_id, numero_turno, tipo_materiale, "
                    "materiale_tipo_codice, numero_giornate, stato, "
                    "localita_manutenzione_partenza_id, "
                    "localita_manutenzione_arrivo_id, generation_metadata_json) "
                    "SELECT pm.azienda_id, :pid, CAST(:codice AS VARCHAR), "
                    "  'TEST', NULL, 1, 'bozza', "
                    "  (SELECT id FROM localita_manutenzione "
                    "   WHERE azienda_id = pm.azienda_id LIMIT 1), "
                    "  (SELECT id FROM localita_manutenzione "
                    "   WHERE azienda_id = pm.azienda_id LIMIT 1), "
                    "  '{}'::jsonb "
                    "FROM programma_materiale pm WHERE pm.id = :pid "
                    "RETURNING id"
                ),
                {"pid": programma_id, "codice": codice},
            )
        ).first()
        assert row is not None
        return int(row[0])


async def test_genera_turno_pdc_pdc_confermato_409(client: TestClient) -> None:
    """Sprint 8.0 MR 2: freeze su POST /api/giri/{id}/genera-turno-pdc
    quando programma >= PDC_CONFERMATO."""
    pid = await _crea_programma_in_stato("freeze_pdc_post", "PDC_CONFERMATO")
    giro_id = await _crea_giro_minimo(pid, "G-FRZ-PDC-001")
    res = client.post(
        f"/api/giri/{giro_id}/genera-turno-pdc",
        headers=_h(_admin_token(client)),
    )
    assert res.status_code == 409, res.text
    assert "PDC_CONFERMATO" in res.json()["detail"]


async def test_genera_turno_pdc_giro_inesistente_404(client: TestClient) -> None:
    """Pre-check freeze ritorna 404 se ``giro_id`` non esiste."""
    res = client.post(
        "/api/giri/999999/genera-turno-pdc",
        headers=_h(_admin_token(client)),
    )
    assert res.status_code == 404


async def test_genera_turno_pdc_personale_assegnato_409(
    client: TestClient,
) -> None:
    """Freeze attivo anche oltre la soglia (PERSONALE_ASSEGNATO)."""
    pid = await _crea_programma_in_stato(
        "freeze_pdc_pers", "PERSONALE_ASSEGNATO"
    )
    giro_id = await _crea_giro_minimo(pid, "G-FRZ-PDC-002")
    res = client.post(
        f"/api/giri/{giro_id}/genera-turno-pdc",
        headers=_h(_admin_token(client)),
    )
    assert res.status_code == 409


# =====================================================================
# Variazioni PdE (Sprint 8.0 MR 5, entry 170)
# =====================================================================


async def test_registra_variazione_pde_ok(client: TestClient) -> None:
    pid = await _crea_programma_in_stato("var_ok", "MATERIALE_CONFERMATO")
    res = client.post(
        f"/api/programmi/{pid}/variazioni",
        json={
            "tipo": "VARIAZIONE_INTERRUZIONE",
            "source_file": "pde_var_int_2026_03.txt",
            "n_corse": 12,
            "note": "interruzione linea S5 da 03/2026",
        },
        headers=_h(_admin_token(client)),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["tipo"] == "VARIAZIONE_INTERRUZIONE"
    assert body["programma_materiale_id"] == pid
    assert body["source_file"] == "pde_var_int_2026_03.txt"
    assert body["n_corse"] == 12


async def test_registra_variazione_pde_tipo_base_400(client: TestClient) -> None:
    """``BASE`` non è ammesso come variazione (è il primo import)."""
    pid = await _crea_programma_in_stato("var_base", "MATERIALE_CONFERMATO")
    res = client.post(
        f"/api/programmi/{pid}/variazioni",
        json={"tipo": "BASE", "source_file": "x.txt"},
        headers=_h(_admin_token(client)),
    )
    assert res.status_code == 422


async def test_list_variazioni_pde(client: TestClient) -> None:
    pid = await _crea_programma_in_stato("var_list", "MATERIALE_CONFERMATO")
    # Crea 2 variazioni
    for tipo in ("INTEGRAZIONE", "VARIAZIONE_ORARIO"):
        client.post(
            f"/api/programmi/{pid}/variazioni",
            json={
                "tipo": tipo,
                "source_file": f"pde_{tipo.lower()}.txt",
                "n_corse": 5,
            },
            headers=_h(_admin_token(client)),
        )
    res = client.get(
        f"/api/programmi/{pid}/variazioni", headers=_h(_admin_token(client))
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    # Ordinato DESC per started_at: la più recente (VARIAZIONE_ORARIO) in cima.
    assert body[0]["tipo"] == "VARIAZIONE_ORARIO"
    assert body[1]["tipo"] == "INTEGRAZIONE"


async def test_registra_variazione_post_freeze_ok(client: TestClient) -> None:
    """Le variazioni sono ammesse anche dopo MATERIALE_CONFERMATO
    (decisione MR 5: il PdE cambia in corso d'anno, scollegato dal
    freeze regole/giri)."""
    pid = await _crea_programma_in_stato("var_freezato", "PDC_CONFERMATO")
    res = client.post(
        f"/api/programmi/{pid}/variazioni",
        json={
            "tipo": "VARIAZIONE_CANCELLAZIONE",
            "source_file": "pde_canc_2026_06.txt",
        },
        headers=_h(_admin_token(client)),
    )
    assert res.status_code == 201


async def test_sblocca_riapre_modifiche(client: TestClient) -> None:
    """Verifica end-to-end del workflow: conferma → freeze 409 → admin
    sblocca → modifica torna a 200."""
    pid = await _crea_programma_in_stato("freeze_unblock", "MATERIALE_GENERATO")
    # Conferma (freeze attivo)
    assert (
        client.post(
            f"/api/programmi/{pid}/conferma-materiale",
            headers=_h(_admin_token(client)),
        ).status_code
        == 200
    )
    # PATCH ora è 409
    assert (
        client.patch(
            f"/api/programmi/{pid}",
            json=_PATCH_PAYLOAD,
            headers=_h(_admin_token(client)),
        ).status_code
        == 409
    )
    # Admin sblocca → torna a MATERIALE_GENERATO
    assert (
        client.post(
            f"/api/programmi/{pid}/sblocca",
            json={"ramo": "pdc", "motivo": "test riapertura"},
            headers=_h(_admin_token(client)),
        ).status_code
        == 200
    )
    # PATCH ora ok
    res_patch = client.patch(
        f"/api/programmi/{pid}",
        json=_PATCH_PAYLOAD,
        headers=_h(_admin_token(client)),
    )
    assert res_patch.status_code == 200, res_patch.text


# =====================================================================
# Auto-assegna persone — Sub-MR 2.bis-a (Sprint 8.0)
# =====================================================================
#
# Pattern: per ogni test si crea un setup completo (programma in
# PDC_CONFERMATO + giro + turno_pdc con generation_metadata_json giro_id
# + giornate LMXGV + persone nel deposito test). La fixture
# ``_clean_aa_data`` autouse pulisce tutte le righe AA prima di ogni
# test (in ordine FK-safe).
#
# Prefissi (isolati dai test pipeline TEST_PIPELINE_):
# - programma.nome / turno.codice / giro.numero_turno: ``TEST_AA_``
# - persona.codice_dipendente: ``TEST_AAM``
# - depot.codice: ``TEST_AA_DEPOT``
# - stazione.codice: ``S99TESTAA``


_AA_PROG_PREFIX = "TEST_AA_"
_AA_PERSONA_PREFIX = "TEST_AAM"
_AA_DEPOT_CODICE = "TEST_AA_DEPOT"
_AA_STAZIONE_CODICE = "STESTAA"  # solo lettere uppercase per ~'^[A-Z]+$'


async def _wipe_aa_data() -> None:
    """Pulisce tutti i dati creati dai test AA, in ordine FK-safe."""
    async with session_scope() as session:
        # 1) Assegnazioni → persona/turno_pdc_giornata
        await session.execute(
            text(
                "DELETE FROM assegnazione_giornata WHERE persona_id IN ("
                "  SELECT id FROM persona WHERE codice_dipendente LIKE :p)"
            ),
            {"p": f"{_AA_PERSONA_PREFIX}%"},
        )
        # 2) Indisponibilità → persona
        await session.execute(
            text(
                "DELETE FROM indisponibilita_persona WHERE persona_id IN ("
                "  SELECT id FROM persona WHERE codice_dipendente LIKE :p)"
            ),
            {"p": f"{_AA_PERSONA_PREFIX}%"},
        )
        # 3) Persone (dopo aver tolto FK figlie)
        await session.execute(
            text("DELETE FROM persona WHERE codice_dipendente LIKE :p"),
            {"p": f"{_AA_PERSONA_PREFIX}%"},
        )
        # 4) turno_pdc_giornata + turno_pdc (CASCADE su giornata)
        await session.execute(
            text("DELETE FROM turno_pdc WHERE codice LIKE :p"),
            {"p": f"{_AA_PROG_PREFIX}%"},
        )
        # 5) giro_materiale
        await session.execute(
            text("DELETE FROM giro_materiale WHERE numero_turno LIKE :p"),
            {"p": f"{_AA_PROG_PREFIX}%"},
        )
        # 6) programma_materiale (regole + master)
        await session.execute(
            text(
                "DELETE FROM programma_regola_assegnazione WHERE programma_id IN ("
                "  SELECT id FROM programma_materiale WHERE nome LIKE :p)"
            ),
            {"p": f"{_AA_PROG_PREFIX}%"},
        )
        await session.execute(
            text("DELETE FROM programma_materiale WHERE nome LIKE :p"),
            {"p": f"{_AA_PROG_PREFIX}%"},
        )


@pytest.fixture(autouse=True)
async def _clean_aa() -> None:
    """Wipe AA data before each test (parallelo a _clean_programmi)."""
    await _wipe_aa_data()


async def _crea_setup_aa(
    programma_suffix: str,
    *,
    n_persone: int = 2,
    n_giornate: int = 1,
    valido_da: date = date(2026, 5, 4),  # lunedì
    valido_a: date = date(2026, 5, 8),   # venerdì
    inizio_giornata: str = "06:00:00",
    fine_giornata: str = "14:00:00",
    is_notturno: bool = False,
    stazione_fine_codice: str | None = None,
    variante: str = "LMXGV",
) -> dict[str, int | list[int]]:
    """Crea programma PDC_CONFERMATO + giro + turno + giornate + persone.

    Ritorna ids per asserzioni nei test. ``stazione_fine_codice=None``
    significa stazione_fine = stazione del depot test (= no FR).
    """
    pid = await _crea_programma_in_stato(
        f"{programma_suffix}_AA",  # nome che inizia con TEST_PIPELINE_<suffix>_AA
        "PDC_CONFERMATO",
    )
    # Cambia il nome del programma al prefisso AA per cleanup isolato
    async with session_scope() as session:
        await session.execute(
            text(
                "UPDATE programma_materiale SET nome = :n, valido_da = :da, "
                "valido_a = :a WHERE id = :pid"
            ),
            {
                "n": f"{_AA_PROG_PREFIX}{programma_suffix}",
                "da": valido_da,
                "a": valido_a,
                "pid": pid,
            },
        )

        # 1) Stazione test (idempotente)
        await session.execute(
            text(
                "INSERT INTO stazione (codice, nome, azienda_id) "
                "SELECT :c, 'TEST AA STAZIONE', a.id "
                "FROM azienda a WHERE a.codice = 'trenord' "
                "ON CONFLICT (codice) DO NOTHING"
            ),
            {"c": _AA_STAZIONE_CODICE},
        )
        # 2) Depot test
        depot_row = (
            await session.execute(
                text(
                    "INSERT INTO depot "
                    "(codice, display_name, azienda_id, "
                    " stazione_principale_codice, tipi_personale_ammessi) "
                    "SELECT :c, 'TEST AA DEPOT', a.id, :s, 'PdC' "
                    "FROM azienda a WHERE a.codice = 'trenord' "
                    "ON CONFLICT (codice) DO UPDATE "
                    "SET display_name = EXCLUDED.display_name "
                    "RETURNING id"
                ),
                {"c": _AA_DEPOT_CODICE, "s": _AA_STAZIONE_CODICE},
            )
        ).first()
        assert depot_row is not None
        depot_id = int(depot_row[0])

        # 3) Giro materiale (FK programma)
        giro_row = (
            await session.execute(
                text(
                    "INSERT INTO giro_materiale "
                    "(azienda_id, programma_id, numero_turno, tipo_materiale, "
                    " materiale_tipo_codice, numero_giornate, stato, "
                    " localita_manutenzione_partenza_id, "
                    " localita_manutenzione_arrivo_id, "
                    " generation_metadata_json) "
                    "SELECT pm.azienda_id, :pid, :nt, 'TEST_AA', NULL, :ng, 'bozza', "
                    " (SELECT id FROM localita_manutenzione "
                    "  WHERE azienda_id = pm.azienda_id LIMIT 1), "
                    " (SELECT id FROM localita_manutenzione "
                    "  WHERE azienda_id = pm.azienda_id LIMIT 1), "
                    " '{}'::jsonb "
                    "FROM programma_materiale pm WHERE pm.id = :pid "
                    "RETURNING id"
                ),
                {
                    "pid": pid,
                    "nt": f"{_AA_PROG_PREFIX}{programma_suffix}_GIRO",
                    "ng": n_giornate,
                },
            )
        ).first()
        assert giro_row is not None
        giro_id = int(giro_row[0])

        # 4) Turno PdC (FK depot + generation_metadata_json giro_id)
        turno_row = (
            await session.execute(
                text(
                    "INSERT INTO turno_pdc "
                    "(azienda_id, codice, impianto, profilo, ciclo_giorni, "
                    " valido_da, valido_a, deposito_pdc_id, "
                    " generation_metadata_json, stato) "
                    "SELECT a.id, :c, 'TEST_AA', 'Condotta', 7, "
                    " :da, :a, :did, "
                    " jsonb_build_object('giro_materiale_id', CAST(:gid AS BIGINT)), "
                    " 'bozza' "
                    "FROM azienda a WHERE a.codice = 'trenord' "
                    "RETURNING id"
                ),
                {
                    "c": f"{_AA_PROG_PREFIX}{programma_suffix}_T",
                    "da": valido_da,
                    "a": valido_a,
                    "did": depot_id,
                    "gid": giro_id,
                },
            )
        ).first()
        assert turno_row is not None
        turno_id = int(turno_row[0])

        # 5) N giornate
        giornate_ids: list[int] = []
        sf_codice = stazione_fine_codice or _AA_STAZIONE_CODICE
        for n in range(1, n_giornate + 1):
            g_row = (
                await session.execute(
                    text(
                        "INSERT INTO turno_pdc_giornata "
                        "(turno_pdc_id, numero_giornata, variante_calendario, "
                        " stazione_inizio, stazione_fine, "
                        " inizio_prestazione, fine_prestazione, "
                        " prestazione_min, condotta_min, refezione_min, km, "
                        " is_notturno, is_riposo, is_disponibile, riposo_min) "
                        "VALUES (:tid, :n, :v, :si, :sf, "
                        " CAST(:ip AS TIME), CAST(:fp AS TIME), "
                        " 480, 240, 30, 0, :nt, FALSE, FALSE, 0) "
                        "RETURNING id"
                    ),
                    {
                        "tid": turno_id,
                        "n": n,
                        "v": variante,
                        "si": _AA_STAZIONE_CODICE,
                        "sf": sf_codice,
                        "ip": inizio_giornata,
                        "fp": fine_giornata,
                        "nt": is_notturno,
                    },
                )
            ).first()
            assert g_row is not None
            giornate_ids.append(int(g_row[0]))

        # 6) N persone nel depot. Codice unico per suffix per
        # supportare 2+ setup nello stesso test (es. test giornata
        # di altro programma).
        persone_ids: list[int] = []
        # Compatto (max 40 char):  TEST_AAM<suffix>_<idx>. ``codice_dipendente``
        # ha unique (azienda_id, codice_dipendente).
        suffix_safe = programma_suffix[:20].replace(" ", "_")
        for i in range(n_persone):
            p_row = (
                await session.execute(
                    text(
                        "INSERT INTO persona "
                        "(azienda_id, codice_dipendente, nome, cognome, profilo, "
                        " sede_residenza_id, qualifiche_json, is_matricola_attiva) "
                        "SELECT a.id, :c, :nome, 'TEST', 'PdC', :did, "
                        " '[]'::jsonb, TRUE "
                        "FROM azienda a WHERE a.codice = 'trenord' "
                        "RETURNING id"
                    ),
                    {
                        "c": f"{_AA_PERSONA_PREFIX}{suffix_safe}_{i:03d}",
                        "nome": f"PdC{i}",
                        "did": depot_id,
                    },
                )
            ).first()
            assert p_row is not None
            persone_ids.append(int(p_row[0]))

    return {
        "programma_id": pid,
        "depot_id": depot_id,
        "giro_id": giro_id,
        "turno_id": turno_id,
        "giornate_ids": giornate_ids,
        "persone_ids": persone_ids,
    }


async def test_auto_assegna_pre_pdc_confermato_409(
    client: TestClient,
) -> None:
    """Programma in MATERIALE_CONFERMATO → 409 (richiede PDC_CONFERMATO)."""
    pid = await _crea_programma_in_stato("aa_pre_409", "MATERIALE_CONFERMATO")
    res = client.post(
        f"/api/programmi/{pid}/auto-assegna-persone",
        json={},
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert res.status_code == 409, res.text
    assert "PDC_CONFERMATO" in res.json()["detail"]


async def test_auto_assegna_403_se_ruolo_diverso_da_gestione_personale(
    client: TestClient,
) -> None:
    """Auth: PIANIFICATORE_PDC non può auto-assegnare (è ruolo dedicato a Personale)."""
    pid = await _crea_programma_in_stato("aa_403", "PDC_CONFERMATO")
    # pianificatore_pdc è in _TEST_ROLES (creato dal _module_setup)
    res = client.post(
        f"/api/programmi/{pid}/auto-assegna-persone",
        json={},
        headers=_h(_ruolo_token(client, "pianificatore_pdc")),
    )
    assert res.status_code == 403


def test_auto_assegna_401_senza_token(client: TestClient) -> None:
    res = client.post("/api/programmi/9999/auto-assegna-persone", json={})
    assert res.status_code == 401


async def test_auto_assegna_caso_base_assegnazione_creata(
    client: TestClient,
) -> None:
    """1 turno + 1 giornata LMXGV + 1 persona + 1 lunedì → 1 assegnazione."""
    setup = await _crea_setup_aa(
        "case_base",
        n_persone=1,
        n_giornate=1,
        valido_da=date(2026, 5, 4),
        valido_a=date(2026, 5, 4),
    )
    res = client.post(
        f"/api/programmi/{setup['programma_id']}/auto-assegna-persone",
        json={
            "data_da": "2026-05-04",
            "data_a": "2026-05-04",
        },
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["n_giornate_totali"] == 1
    assert body["n_giornate_coperte"] == 1
    assert body["n_assegnazioni_create"] == 1
    assert body["delta_copertura_pct"] == 100.0
    assert body["mancanze"] == []
    assert len(body["assegnazioni"]) == 1
    persone_ids = setup["persone_ids"]
    assert isinstance(persone_ids, list)
    assert body["assegnazioni"][0]["persona_id"] == persone_ids[0]


async def test_auto_assegna_indisponibilita_genera_mancanza(
    client: TestClient,
) -> None:
    """Unica persona indisponibile → mancanza con motivo TUTTI_INDISPONIBILI."""
    setup = await _crea_setup_aa(
        "case_indisp",
        n_persone=1,
        valido_da=date(2026, 5, 4),
        valido_a=date(2026, 5, 4),
    )
    persone_ids = setup["persone_ids"]
    assert isinstance(persone_ids, list)
    persona_id = persone_ids[0]
    # Inserisco indisponibilità approvata che copre la data
    async with session_scope() as session:
        await session.execute(
            text(
                "INSERT INTO indisponibilita_persona "
                "(persona_id, tipo, data_inizio, data_fine, is_approvato) "
                "VALUES (:pid, 'ferie', :da, :a, TRUE)"
            ),
            {
                "pid": persona_id,
                "da": date(2026, 5, 4),
                "a": date(2026, 5, 4),
            },
        )

    res = client.post(
        f"/api/programmi/{setup['programma_id']}/auto-assegna-persone",
        json={"data_da": "2026-05-04", "data_a": "2026-05-04"},
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["n_giornate_coperte"] == 0
    assert body["n_assegnazioni_create"] == 0
    assert body["delta_copertura_pct"] == 0.0
    assert len(body["mancanze"]) == 1
    assert body["mancanze"][0]["motivo"] == "tutti_indisponibili"


async def test_auto_assegna_idempotente(client: TestClient) -> None:
    """2° call con stessa finestra → 0 nuove (esistenti già coprono)."""
    setup = await _crea_setup_aa(
        "case_idempotent",
        n_persone=1,
        valido_da=date(2026, 5, 4),
        valido_a=date(2026, 5, 4),
    )
    body = {"data_da": "2026-05-04", "data_a": "2026-05-04"}
    # 1° run: crea 1 assegnazione
    res1 = client.post(
        f"/api/programmi/{setup['programma_id']}/auto-assegna-persone",
        json=body,
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert res1.status_code == 200
    assert res1.json()["n_assegnazioni_create"] == 1
    # 2° run: 0 nuove (la giornata è già coperta)
    res2 = client.post(
        f"/api/programmi/{setup['programma_id']}/auto-assegna-persone",
        json=body,
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert res2.status_code == 200
    body2 = res2.json()
    assert body2["n_assegnazioni_create"] == 0
    assert body2["n_giornate_coperte"] == 1
    assert body2["delta_copertura_pct"] == 100.0


async def test_auto_assegna_finestra_default_da_programma(
    client: TestClient,
) -> None:
    """Senza payload, usa programma.valido_da..valido_a."""
    setup = await _crea_setup_aa(
        "case_default_window",
        n_persone=5,  # abbastanza per coprire 5 giorni
        n_giornate=1,
        valido_da=date(2026, 5, 4),
        valido_a=date(2026, 5, 8),  # 5 lun-ven feriali
    )
    res = client.post(
        f"/api/programmi/{setup['programma_id']}/auto-assegna-persone",
        json={},  # no data_da/data_a → default
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["finestra_data_da"] == "2026-05-04"
    assert body["finestra_data_a"] == "2026-05-08"
    assert body["n_giornate_totali"] == 5  # 5 lun-ven match LMXGV
    assert body["n_assegnazioni_create"] == 5
    assert body["delta_copertura_pct"] == 100.0


async def test_auto_assegna_finestra_data_da_dopo_a_400(
    client: TestClient,
) -> None:
    """data_da > data_a esplicito → 400 dal validator Pydantic."""
    setup = await _crea_setup_aa("case_400", valido_da=date(2026, 5, 4))
    res = client.post(
        f"/api/programmi/{setup['programma_id']}/auto-assegna-persone",
        json={"data_da": "2026-05-10", "data_a": "2026-05-04"},
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    # Pydantic validator raises ValueError → 422
    assert res.status_code == 422, res.text


async def test_auto_assegna_persisted_su_db(client: TestClient) -> None:
    """Verifica che le assegnazioni sono persistite su ``assegnazione_giornata``."""
    setup = await _crea_setup_aa(
        "case_persist",
        n_persone=1,
        valido_da=date(2026, 5, 4),
        valido_a=date(2026, 5, 4),
    )
    res = client.post(
        f"/api/programmi/{setup['programma_id']}/auto-assegna-persone",
        json={"data_da": "2026-05-04", "data_a": "2026-05-04"},
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert res.status_code == 200
    # Verifica DB
    async with session_scope() as session:
        giornate_ids = setup["giornate_ids"]
        assert isinstance(giornate_ids, list)
        rows = (
            await session.execute(
                text(
                    "SELECT persona_id, data, turno_pdc_giornata_id, stato "
                    "FROM assegnazione_giornata "
                    "WHERE turno_pdc_giornata_id = :gid"
                ),
                {"gid": giornate_ids[0]},
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].stato == "pianificato"
        assert rows[0].data == date(2026, 5, 4)


# =====================================================================
# Assegna manuale (override) — Sub-MR 2.bis-b (Sprint 8.0)
# =====================================================================


async def test_assegna_manuale_ok(client: TestClient) -> None:
    """Override manuale: persona compatibile, giornata vuota → 201."""
    setup = await _crea_setup_aa(
        "manuale_ok",
        n_persone=1,
        n_giornate=1,
        valido_da=date(2026, 5, 4),
        valido_a=date(2026, 5, 4),
    )
    persone_ids = setup["persone_ids"]
    giornate_ids = setup["giornate_ids"]
    assert isinstance(persone_ids, list)
    assert isinstance(giornate_ids, list)

    res = client.post(
        f"/api/programmi/{setup['programma_id']}/assegna-manuale",
        json={
            "persona_id": persone_ids[0],
            "turno_pdc_giornata_id": giornate_ids[0],
            "data": "2026-05-04",
        },
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["persona_id"] == persone_ids[0]
    assert body["turno_pdc_giornata_id"] == giornate_ids[0]
    assert body["data"] == "2026-05-04"
    # Verifica nota="override_manuale" persistita per audit
    async with session_scope() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT note FROM assegnazione_giornata "
                    "WHERE persona_id = :pid AND data = :d"
                ),
                {"pid": persone_ids[0], "d": date(2026, 5, 4)},
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].note == "override_manuale"


async def test_assegna_manuale_pre_pdc_confermato_409(
    client: TestClient,
) -> None:
    """Programma in MATERIALE_CONFERMATO → 409."""
    pid = await _crea_programma_in_stato(
        "manuale_pre_409", "MATERIALE_CONFERMATO"
    )
    res = client.post(
        f"/api/programmi/{pid}/assegna-manuale",
        json={
            "persona_id": 1,
            "turno_pdc_giornata_id": 1,
            "data": "2026-05-04",
        },
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert res.status_code == 409
    assert "PDC_CONFERMATO" in res.json()["detail"]


async def test_assegna_manuale_persona_inesistente_404(
    client: TestClient,
) -> None:
    """persona_id non esiste → 404."""
    setup = await _crea_setup_aa("manuale_pers_404", n_persone=1, n_giornate=1)
    giornate_ids = setup["giornate_ids"]
    assert isinstance(giornate_ids, list)
    res = client.post(
        f"/api/programmi/{setup['programma_id']}/assegna-manuale",
        json={
            "persona_id": 999999,
            "turno_pdc_giornata_id": giornate_ids[0],
            "data": "2026-05-04",
        },
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert res.status_code == 404
    assert "persona" in res.json()["detail"].lower()


async def test_assegna_manuale_giornata_di_altro_programma_404(
    client: TestClient,
) -> None:
    """Giornata che NON appartiene al programma target → 404."""
    setup_a = await _crea_setup_aa(
        "manuale_a", n_persone=1, n_giornate=1
    )
    setup_b = await _crea_setup_aa(
        "manuale_b", n_persone=1, n_giornate=1
    )
    persone_a_ids = setup_a["persone_ids"]
    giornate_b_ids = setup_b["giornate_ids"]
    assert isinstance(persone_a_ids, list)
    assert isinstance(giornate_b_ids, list)
    res = client.post(
        f"/api/programmi/{setup_a['programma_id']}/assegna-manuale",
        json={
            "persona_id": persone_a_ids[0],
            "turno_pdc_giornata_id": giornate_b_ids[0],  # giornata di B
            "data": "2026-05-04",
        },
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert res.status_code == 404
    assert "non appartiene" in res.json()["detail"]


async def test_assegna_manuale_persona_gia_assegnata_409(
    client: TestClient,
) -> None:
    """Persona ha già un'assegnazione sulla stessa data → 409."""
    setup = await _crea_setup_aa(
        "manuale_doppia_pers",
        n_persone=1,
        n_giornate=2,
        valido_da=date(2026, 5, 4),
        valido_a=date(2026, 5, 4),
    )
    persone_ids = setup["persone_ids"]
    giornate_ids = setup["giornate_ids"]
    assert isinstance(persone_ids, list)
    assert isinstance(giornate_ids, list)
    # 1° assegnazione manuale
    r1 = client.post(
        f"/api/programmi/{setup['programma_id']}/assegna-manuale",
        json={
            "persona_id": persone_ids[0],
            "turno_pdc_giornata_id": giornate_ids[0],
            "data": "2026-05-04",
        },
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert r1.status_code == 201
    # 2° tentativo stesso (persona, data) ma giornata diversa → 409
    r2 = client.post(
        f"/api/programmi/{setup['programma_id']}/assegna-manuale",
        json={
            "persona_id": persone_ids[0],
            "turno_pdc_giornata_id": giornate_ids[1],
            "data": "2026-05-04",
        },
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert r2.status_code == 409
    assert "ha già" in r2.json()["detail"]


async def test_assegna_manuale_giornata_gia_coperta_409(
    client: TestClient,
) -> None:
    """(turno_pdc_giornata, data) già coperto → 409."""
    setup = await _crea_setup_aa(
        "manuale_doppia_giorn",
        n_persone=2,
        n_giornate=1,
        valido_da=date(2026, 5, 4),
        valido_a=date(2026, 5, 4),
    )
    persone_ids = setup["persone_ids"]
    giornate_ids = setup["giornate_ids"]
    assert isinstance(persone_ids, list)
    assert isinstance(giornate_ids, list)
    r1 = client.post(
        f"/api/programmi/{setup['programma_id']}/assegna-manuale",
        json={
            "persona_id": persone_ids[0],
            "turno_pdc_giornata_id": giornate_ids[0],
            "data": "2026-05-04",
        },
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert r1.status_code == 201
    # 2° tentativo stessa giornata stessa data ma persona diversa → 409
    r2 = client.post(
        f"/api/programmi/{setup['programma_id']}/assegna-manuale",
        json={
            "persona_id": persone_ids[1],
            "turno_pdc_giornata_id": giornate_ids[0],
            "data": "2026-05-04",
        },
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert r2.status_code == 409
    assert "già coperta" in r2.json()["detail"]


async def test_assegna_manuale_403_pianificatore_pdc(
    client: TestClient,
) -> None:
    """PIANIFICATORE_PDC non può fare override (è ruolo Personale)."""
    setup = await _crea_setup_aa("manuale_403", n_persone=1, n_giornate=1)
    persone_ids = setup["persone_ids"]
    giornate_ids = setup["giornate_ids"]
    assert isinstance(persone_ids, list)
    assert isinstance(giornate_ids, list)
    res = client.post(
        f"/api/programmi/{setup['programma_id']}/assegna-manuale",
        json={
            "persona_id": persone_ids[0],
            "turno_pdc_giornata_id": giornate_ids[0],
            "data": "2026-05-04",
        },
        headers=_h(_ruolo_token(client, "pianificatore_pdc")),
    )
    assert res.status_code == 403


async def test_assegna_manuale_chiude_mancanza_da_auto_assegna(
    client: TestClient,
) -> None:
    """Workflow completo: auto-assegna lascia mancanza (persona indisp),
    override la chiude."""
    setup = await _crea_setup_aa(
        "manuale_chiude_mancanza",
        n_persone=1,
        n_giornate=1,
        valido_da=date(2026, 5, 4),
        valido_a=date(2026, 5, 4),
    )
    persone_ids = setup["persone_ids"]
    giornate_ids = setup["giornate_ids"]
    assert isinstance(persone_ids, list)
    assert isinstance(giornate_ids, list)

    # Indisponibilità che blocca l'auto-assegna
    async with session_scope() as session:
        await session.execute(
            text(
                "INSERT INTO indisponibilita_persona "
                "(persona_id, tipo, data_inizio, data_fine, is_approvato) "
                "VALUES (:pid, 'ferie', :da, :a, TRUE)"
            ),
            {
                "pid": persone_ids[0],
                "da": date(2026, 5, 4),
                "a": date(2026, 5, 4),
            },
        )

    # Auto-assegna → mancanza
    r_auto = client.post(
        f"/api/programmi/{setup['programma_id']}/auto-assegna-persone",
        json={"data_da": "2026-05-04", "data_a": "2026-05-04"},
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert r_auto.status_code == 200
    assert r_auto.json()["n_assegnazioni_create"] == 0
    assert len(r_auto.json()["mancanze"]) == 1

    # Override manuale: forza la persona indisponibile
    r_man = client.post(
        f"/api/programmi/{setup['programma_id']}/assegna-manuale",
        json={
            "persona_id": persone_ids[0],
            "turno_pdc_giornata_id": giornate_ids[0],
            "data": "2026-05-04",
        },
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert r_man.status_code == 201

    # Re-run auto-assegna: ora la giornata è coperta, n_assegnazioni_create=0
    r_auto2 = client.post(
        f"/api/programmi/{setup['programma_id']}/auto-assegna-persone",
        json={"data_da": "2026-05-04", "data_a": "2026-05-04"},
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert r_auto2.status_code == 200
    body2 = r_auto2.json()
    assert body2["n_assegnazioni_create"] == 0
    assert body2["n_giornate_coperte"] == 1
    assert body2["delta_copertura_pct"] == 100.0
    assert body2["mancanze"] == []


# =====================================================================
# Conferma personale gating su copertura_pct — Sub-MR 2.bis-c (entry 174)
# =====================================================================


async def test_conferma_personale_409_se_no_run_auto_assegna(
    client: TestClient,
) -> None:
    """``programma.copertura_pct IS NULL`` → 409 con messaggio "esegui prima auto-assegna"."""
    pid = await _crea_programma_in_stato("conf_pers_no_run", "PDC_CONFERMATO")
    res = client.post(
        f"/api/programmi/{pid}/conferma-personale",
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert res.status_code == 409, res.text
    assert "auto-assegna" in res.json()["detail"]


async def test_conferma_personale_409_se_copertura_sotto_soglia(
    client: TestClient,
) -> None:
    """``copertura_pct < 95.0`` → 409."""
    pid = await _crea_programma_in_stato(
        "conf_pers_sotto", "PDC_CONFERMATO"
    )
    # Forzo copertura_pct = 80.0 (sotto soglia 95.0)
    async with session_scope() as session:
        await session.execute(
            text("UPDATE programma_materiale SET copertura_pct = 80.0 WHERE id = :pid"),
            {"pid": pid},
        )
    res = client.post(
        f"/api/programmi/{pid}/conferma-personale",
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert "80" in detail
    assert "95" in detail


async def test_conferma_personale_ok_se_copertura_sopra_soglia(
    client: TestClient,
) -> None:
    """``copertura_pct >= 95.0`` → 200 (transizione PERSONALE_ASSEGNATO)."""
    pid = await _crea_programma_in_stato(
        "conf_pers_ok", "PDC_CONFERMATO"
    )
    async with session_scope() as session:
        await session.execute(
            text("UPDATE programma_materiale SET copertura_pct = 100.0 WHERE id = :pid"),
            {"pid": pid},
        )
    res = client.post(
        f"/api/programmi/{pid}/conferma-personale",
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["stato_pipeline_pdc"] == "PERSONALE_ASSEGNATO"
    assert body["copertura_pct"] == 100.0


async def test_conferma_personale_ok_a_soglia_esatta(
    client: TestClient,
) -> None:
    """``copertura_pct == 95.0`` (esattamente alla soglia) → 200."""
    pid = await _crea_programma_in_stato(
        "conf_pers_soglia", "PDC_CONFERMATO"
    )
    async with session_scope() as session:
        await session.execute(
            text("UPDATE programma_materiale SET copertura_pct = 95.0 WHERE id = :pid"),
            {"pid": pid},
        )
    res = client.post(
        f"/api/programmi/{pid}/conferma-personale",
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert res.status_code == 200, res.text


async def test_conferma_personale_workflow_end_to_end(
    client: TestClient,
) -> None:
    """End-to-end: auto-assegna popola copertura → conferma-personale 200."""
    setup = await _crea_setup_aa(
        "conf_pers_e2e",
        n_persone=1,
        n_giornate=1,
        valido_da=date(2026, 5, 4),
        valido_a=date(2026, 5, 4),
    )
    # Auto-assegna copre la giornata (1/1 = 100%)
    r_auto = client.post(
        f"/api/programmi/{setup['programma_id']}/auto-assegna-persone",
        json={"data_da": "2026-05-04", "data_a": "2026-05-04"},
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert r_auto.status_code == 200
    assert r_auto.json()["delta_copertura_pct"] == 100.0
    # Conferma OK
    r_conf = client.post(
        f"/api/programmi/{setup['programma_id']}/conferma-personale",
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert r_conf.status_code == 200
    assert r_conf.json()["stato_pipeline_pdc"] == "PERSONALE_ASSEGNATO"


async def test_auto_assegna_persiste_copertura_pct_su_programma(
    client: TestClient,
) -> None:
    """Verifica che la copertura calcolata dall'algoritmo sia
    persistita su ``programma_materiale.copertura_pct``."""
    setup = await _crea_setup_aa(
        "auto_persiste_pct",
        n_persone=1,
        n_giornate=1,
        valido_da=date(2026, 5, 4),
        valido_a=date(2026, 5, 4),
    )
    res = client.post(
        f"/api/programmi/{setup['programma_id']}/auto-assegna-persone",
        json={"data_da": "2026-05-04", "data_a": "2026-05-04"},
        headers=_h(_ruolo_token(client, "gestione_personale")),
    )
    assert res.status_code == 200
    # Verifica DB
    async with session_scope() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT copertura_pct FROM programma_materiale "
                    "WHERE id = :pid"
                ),
                {"pid": setup["programma_id"]},
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].copertura_pct == 100.0
