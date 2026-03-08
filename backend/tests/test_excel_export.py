import os
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
import requests
from dotenv import dotenv_values

# Excel export module regression: endpoint status/content, workbook schema, and filter subset correctness.


def _load_base_url() -> str:
    base_url = os.environ.get("REACT_APP_BACKEND_URL")
    if not base_url:
        frontend_env = Path("/app/frontend/.env")
        if frontend_env.exists():
            base_url = dotenv_values(frontend_env).get("REACT_APP_BACKEND_URL")
    if not base_url:
        raise RuntimeError("REACT_APP_BACKEND_URL is not configured")
    return str(base_url).rstrip("/")


BASE_URL = _load_base_url()
API_BASE = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def api_client() -> requests.Session:
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


def _read_export_dataframe(binary_content: bytes) -> pd.DataFrame:
    bio = BytesIO(binary_content)
    return pd.read_excel(bio, sheet_name="Sinyaller")


def test_export_excel_endpoint_returns_real_xlsx(api_client: requests.Session):
    payload = {"markets": ["NASDAQ", "BIST"], "actions": ["GÜÇLÜ AL", "AL", "TUT", "SAT", "GÜÇLÜ SAT"]}
    response = api_client.post(f"{API_BASE}/signals/export/excel", json=payload, timeout=120)

    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    content_disposition = response.headers.get("content-disposition", "")
    assert "sinyal_raporu.xlsx" in content_disposition

    dataframe = _read_export_dataframe(response.content)
    assert isinstance(dataframe, pd.DataFrame)


def test_export_excel_schema_and_filter_subset(api_client: requests.Session):
    # Targeted filter: NASDAQ + AL should export only records present in /signals?market=US&action=AL
    expected_resp = api_client.get(
        f"{API_BASE}/signals",
        params={"market": "US", "action": "AL", "limit": 1200},
        timeout=90,
    )
    assert expected_resp.status_code == 200
    expected_data = expected_resp.json()
    expected_symbols = {item["symbol"] for item in expected_data}

    export_resp = api_client.post(
        f"{API_BASE}/signals/export/excel",
        json={"markets": ["NASDAQ"], "actions": ["AL"]},
        timeout=120,
    )
    assert export_resp.status_code == 200

    dataframe = _read_export_dataframe(export_resp.content)

    expected_columns = [
        "Hisse Kodu",
        "Mevcut Sinyal",
        "Hedef Süresi",
        "Take Profit",
        "Stop Loss",
        "Analiz Notu",
    ]
    assert list(dataframe.columns) == expected_columns

    exported_symbols = set(dataframe["Hisse Kodu"].dropna().astype(str).tolist())
    assert exported_symbols.issubset(expected_symbols)

    signal_values = set(dataframe["Mevcut Sinyal"].dropna().astype(str).tolist())
    assert signal_values.issubset({"Al"})

    if not dataframe.empty:
        target_values = dataframe["Hedef Süresi"].dropna().astype(str).tolist()
        assert all(value.strip() != "" for value in target_values)


def test_export_excel_filter_subset_symbols_and_signal_values(api_client: requests.Session):
    expected_resp = api_client.get(
        f"{API_BASE}/signals",
        params={"market": "US", "action": "AL", "limit": 1200},
        timeout=90,
    )
    assert expected_resp.status_code == 200
    expected_data = expected_resp.json()
    expected_symbols = {item["symbol"] for item in expected_data}

    export_resp = api_client.post(
        f"{API_BASE}/signals/export/excel",
        json={"markets": ["NASDAQ"], "actions": ["AL"]},
        timeout=120,
    )
    assert export_resp.status_code == 200

    dataframe = _read_export_dataframe(export_resp.content)
    exported_symbols = set(dataframe["Hisse Kodu"].dropna().astype(str).tolist())
    assert exported_symbols.issubset(expected_symbols)

    signal_values = set(dataframe["Mevcut Sinyal"].dropna().astype(str).tolist())
    assert signal_values.issubset({"Al"})
