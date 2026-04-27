"""Smoke test schemas Pydantic (Sprint 1.8, aggiornato Sprint 5.1).

Verifica:
- Gli schemi si importano da `colazione.schemas`
- Parsing da dict fixture (input tipico API request/response body)
- Parsing da modello ORM in memoria (path FastAPI route → response)

Conteggio: 31 (Read base v0.5) + 7 (Sprint 4.1: FiltroRegola,
StrictOptions, 2 Read + 2 Create + 1 Update per programma) + 1
(Sprint 5.1: ComposizioneItem) = 39.
"""

from datetime import UTC, date, datetime, time
from decimal import Decimal

from colazione import schemas
from colazione.models.anagrafica import Azienda, LocalitaManutenzione
from colazione.models.corse import CorsaCommerciale
from colazione.schemas.anagrafica import AziendaRead, LocalitaManutenzioneRead
from colazione.schemas.corse import CorsaCommercialeRead

EXPECTED_SCHEMA_COUNT = 39


def test_schemas_all_exported() -> None:
    """`__all__` contiene 31 schemi e tutti importabili dal package."""
    assert len(schemas.__all__) == EXPECTED_SCHEMA_COUNT
    for name in schemas.__all__:
        assert hasattr(schemas, name), f"{name} listato ma non importabile"


def test_azienda_read_from_dict_fixture() -> None:
    """Parsing da dict (es. body JSON ricevuto da client)."""
    fixture = {
        "id": 1,
        "codice": "trenord",
        "nome": "Trenord SRL",
        "normativa_pdc_json": {
            "max_prestazione_min_standard": 510,
            "meal_window_1": [690, 930],
        },
        "is_attiva": True,
        "created_at": datetime(2026, 4, 25, 12, 0, tzinfo=UTC),
    }
    out = AziendaRead.model_validate(fixture)
    assert out.id == 1
    assert out.codice == "trenord"
    assert out.normativa_pdc_json["max_prestazione_min_standard"] == 510
    assert out.is_attiva is True


def test_azienda_read_from_orm_instance() -> None:
    """Parsing da modello ORM in memoria (path FastAPI response_model)."""
    az = Azienda(
        id=42,
        codice="trenord",
        nome="Trenord SRL",
        normativa_pdc_json={"max_prestazione_min_standard": 510},
        is_attiva=True,
        created_at=datetime(2026, 4, 25, 12, 0, tzinfo=UTC),
    )
    out = AziendaRead.model_validate(az)
    assert out.id == 42
    assert out.codice == "trenord"


def test_localita_manutenzione_read_pool_esterno() -> None:
    """Parsing località con flag pool esterno (POOL_TILO_SVIZZERA)."""
    lm = LocalitaManutenzione(
        id=7,
        codice="POOL_TILO_SVIZZERA",
        codice_breve="TILO",
        nome_canonico="(Pool TILO - servizi Svizzera-Italia)",
        nomi_alternativi_json=[],
        stazione_collegata_codice=None,
        azienda_id=1,
        is_pool_esterno=True,
        azienda_proprietaria_esterna="TILO",
        is_attiva=True,
        created_at=datetime(2026, 4, 25, 12, 0, tzinfo=UTC),
    )
    out = LocalitaManutenzioneRead.model_validate(lm)
    assert out.is_pool_esterno is True
    assert out.azienda_proprietaria_esterna == "TILO"
    assert out.stazione_collegata_codice is None


def test_corsa_commerciale_read_with_decimal_and_time() -> None:
    """CorsaCommerciale ha tipi vari: time, date, Decimal, JSONB."""
    corsa = CorsaCommerciale(
        id=100,
        azienda_id=1,
        numero_treno="28335",
        rete=None,
        numero_treno_rfi=None,
        numero_treno_fn=None,
        categoria="REG",
        codice_linea="S5",
        direttrice="Milano-Treviglio",
        codice_origine="MIPG",
        codice_destinazione="TRV",
        codice_inizio_cds=None,
        codice_fine_cds=None,
        ora_partenza=time(7, 15),
        ora_arrivo=time(8, 5),
        ora_inizio_cds=None,
        ora_fine_cds=None,
        min_tratta=50,
        min_cds=None,
        km_tratta=Decimal("32.450"),
        km_cds=None,
        valido_da=date(2025, 12, 14),
        valido_a=date(2026, 12, 12),
        codice_periodicita="GG",
        periodicita_breve="GG",
        is_treno_garantito_feriale=True,
        is_treno_garantito_festivo=False,
        fascia_oraria="MATTINA",
        giorni_per_mese_json={"gen": 31},
        valido_in_date_json=["2025-12-15", "2025-12-16"],
        totale_km=Decimal("32.450"),
        totale_minuti=50,
        posti_km=None,
        velocita_commerciale=None,
        import_source="pde",
        import_run_id=None,
        imported_at=datetime(2026, 4, 25, 12, 0, tzinfo=UTC),
    )
    out = CorsaCommercialeRead.model_validate(corsa)
    assert out.numero_treno == "28335"
    assert out.ora_partenza == time(7, 15)
    assert out.km_tratta == Decimal("32.450")
    assert out.valido_da == date(2025, 12, 14)
    assert out.valido_in_date_json == ["2025-12-15", "2025-12-16"]


def test_schemas_serialize_to_json() -> None:
    """Output JSON serializzabile (per FastAPI response)."""
    az = Azienda(
        id=1,
        codice="trenord",
        nome="Trenord SRL",
        normativa_pdc_json={"x": 1},
        is_attiva=True,
        created_at=datetime(2026, 4, 25, 12, 0, tzinfo=UTC),
    )
    out = AziendaRead.model_validate(az)
    payload = out.model_dump_json()
    assert '"codice":"trenord"' in payload
    assert '"is_attiva":true' in payload
