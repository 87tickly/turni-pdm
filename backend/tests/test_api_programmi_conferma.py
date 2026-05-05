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
