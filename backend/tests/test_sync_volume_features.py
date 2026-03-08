import os
import time
from datetime import datetime
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

# Regression coverage for synchronization/live-analysis, directional target sanity,
# and volume + AI summary payload contracts.


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


def _post_with_retry(session: requests.Session, url: str, retries: int = 1, **kwargs):
    last_response = None
    for attempt in range(retries + 1):
        last_response = session.post(url, **kwargs)
        if last_response.status_code == 200:
            return last_response
        if attempt < retries:
            time.sleep(1.5)
    return last_response


@pytest.fixture(scope="session")
def ondemand_symbol(api_client: requests.Session) -> str:
    # US symbol is used for deterministic endpoint behavior in this suite.
    resp = _post_with_retry(api_client, f"{API_BASE}/signals/analyze/RIVN", timeout=180, retries=2)
    assert resp is not None
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert isinstance(payload.get("symbol"), str)
    return payload["symbol"]


def test_on_demand_analyze_consistent_with_detail_and_list(api_client: requests.Session, ondemand_symbol: str):
    analyze_resp = _post_with_retry(api_client, f"{API_BASE}/signals/analyze/{ondemand_symbol}", timeout=180, retries=1)
    assert analyze_resp.status_code == 200
    analyzed = analyze_resp.json()

    detail_resp = api_client.get(f"{API_BASE}/signals/{ondemand_symbol}", timeout=90)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()

    list_resp = api_client.get(f"{API_BASE}/signals", params={"search": ondemand_symbol, "limit": 50}, timeout=90)
    assert list_resp.status_code == 200
    listed = list_resp.json()

    assert analyzed["symbol"] == detail["symbol"]
    assert analyzed["action"] == detail["action"]
    assert analyzed["bullish_score"] == detail["bullish_score"]
    assert any(item["symbol"] == ondemand_symbol and item["action"] == analyzed["action"] for item in listed)


def test_reanalyze_force_live_updates_timestamp(api_client: requests.Session, ondemand_symbol: str):
    first_resp = _post_with_retry(api_client, f"{API_BASE}/signals/{ondemand_symbol}/reanalyze", timeout=180, retries=1)
    assert first_resp.status_code == 200
    first_payload = first_resp.json()
    first_updated = datetime.fromisoformat(first_payload["updated_at"])

    time.sleep(1.2)

    second_resp = _post_with_retry(api_client, f"{API_BASE}/signals/{ondemand_symbol}/reanalyze", timeout=180, retries=1)
    assert second_resp.status_code == 200
    second_payload = second_resp.json()
    second_updated = datetime.fromisoformat(second_payload["updated_at"])

    assert second_updated > first_updated
    assert second_payload["symbol"] == first_payload["symbol"]


def test_volume_analysis_fields_and_breakout_note_present(api_client: requests.Session, ondemand_symbol: str):
    detail_resp = api_client.get(f"{API_BASE}/signals/{ondemand_symbol}", timeout=90)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()

    volume = detail.get("volume_analysis") or {}
    expected_keys = {
        "avg_10",
        "avg_20",
        "prev_10",
        "breakout_volume",
        "breakout_reference_avg",
        "breakout_ratio",
        "volume_confirmed_breakout",
        "breakout_note",
        "change_10d_pct",
        "human_text",
    }
    assert expected_keys.issubset(set(volume.keys()))
    assert isinstance(volume["breakout_note"], str)
    assert volume["breakout_note"] in {"Hacim Onaylı Kırılım", "Hacim Onayı Bekleniyor"}
    assert isinstance(volume["human_text"], str)
    assert len(volume["human_text"].strip()) > 10


def test_explain_summary_contains_hacim_durumu_section(api_client: requests.Session, ondemand_symbol: str):
    explain_resp = _post_with_retry(api_client, f"{API_BASE}/signals/{ondemand_symbol}/explain", timeout=200, retries=1)
    assert explain_resp.status_code == 200
    payload = explain_resp.json()

    summary = payload.get("summary") or ""
    assert isinstance(summary, str)
    assert len(summary.strip()) > 30
    assert "Hacim Durumu" in summary


def test_directional_target_sanity_for_strong_actions(api_client: requests.Session, ondemand_symbol: str):
    detail_resp = api_client.get(f"{API_BASE}/signals/{ondemand_symbol}", timeout=90)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()

    action = detail.get("action")
    last_price = detail.get("last_price")
    atr = ((detail.get("indicators") or {}).get("atr14"))
    confirmed_patterns = [p for p in (detail.get("patterns") or []) if p.get("confirmed")]

    if action not in {"AL", "GÜÇLÜ AL", "SAT", "GÜÇLÜ SAT"}:
        pytest.skip("Action is neutral; directional target sanity not applicable")

    with_target = [p for p in confirmed_patterns if isinstance((p.get("geometry") or {}).get("target_price"), (float, int))]
    if not with_target:
        pytest.skip("No confirmed pattern with target_price returned")

    target = float(with_target[0]["geometry"]["target_price"])
    last_price = float(last_price)

    if action in {"AL", "GÜÇLÜ AL"}:
        min_expected = last_price + (3.0 * float(atr) if isinstance(atr, (float, int)) else last_price * 0.01)
        assert target >= min_expected or target >= last_price
    else:
        max_expected = last_price - (3.0 * float(atr) if isinstance(atr, (float, int)) else last_price * 0.01)
        assert target <= max_expected or target <= last_price
