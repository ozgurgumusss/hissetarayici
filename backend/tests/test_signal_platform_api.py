import os
import time
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

# API coverage: health, config, scanner lifecycle, signals schema, scoring/action consistency, risk block, AI explain endpoint.


def _load_base_url() -> str:
    base_url = os.environ.get("REACT_APP_BACKEND_URL")
    if not base_url:
        frontend_env_path = Path("/app/frontend/.env")
        if frontend_env_path.exists():
            values = dotenv_values(frontend_env_path)
            base_url = values.get("REACT_APP_BACKEND_URL")
    if not base_url:
        raise RuntimeError("REACT_APP_BACKEND_URL is not configured")
    return str(base_url).rstrip("/")


BASE_URL = _load_base_url()
API_BASE = f"{BASE_URL}/api"


def expected_action_for_score(score: int) -> str:
    if score > 75:
        return "GÜÇLÜ AL"
    if 60 <= score <= 75:
        return "AL"
    if 40 <= score < 60:
        return "TUT"
    if 25 <= score < 40:
        return "SAT"
    return "GÜÇLÜ SAT"


@pytest.fixture(scope="session")
def api_client() -> requests.Session:
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="session")
def scan_completed(api_client: requests.Session):
    state_response = api_client.get(f"{API_BASE}/scanner/state", timeout=30)
    assert state_response.status_code == 200

    trigger_response = api_client.post(f"{API_BASE}/scanner/run", timeout=30)
    assert trigger_response.status_code == 200
    trigger_data = trigger_response.json()
    assert trigger_data.get("status") in {"started", "already_running"}

    last_state = None
    for _ in range(80):  # up to ~400 seconds
        poll = api_client.get(f"{API_BASE}/scanner/state", timeout=30)
        assert poll.status_code == 200
        state = poll.json()
        last_state = state
        if state.get("running") is False and state.get("last_run"):
            break
        time.sleep(5)

    assert last_state is not None
    assert last_state.get("running") is False
    assert isinstance(last_state.get("last_scanned_count"), int)
    return last_state


def test_health_endpoint(api_client: requests.Session):
    response = api_client.get(f"{API_BASE}/", timeout=30)
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Algorithmic signal engine is active"
    assert data["scanner_interval_seconds"] == 300
    assert data["markets"]["US"] == 100
    assert data["markets"]["BIST"] == 100


def test_config_endpoint(api_client: requests.Session):
    response = api_client.get(f"{API_BASE}/config", timeout=30)
    assert response.status_code == 200
    data = response.json()
    assert data["refresh_seconds"] == 300
    assert len(data["markets"]["US"]) == 100
    assert len(data["markets"]["BIST"]) == 100
    assert all(symbol.endswith(".IS") for symbol in data["markets"]["BIST"])
    assert data["data_source"] == "Yahoo Finance (US + BIST .IS)"


def test_scanner_state_transitions_and_signals_schema(api_client: requests.Session, scan_completed):
    response = api_client.get(f"{API_BASE}/signals", params={"limit": 250}, timeout=45)
    assert response.status_code == 200
    signals = response.json()
    assert isinstance(signals, list)
    assert len(signals) > 0

    first = signals[0]
    for key in [
        "symbol",
        "market",
        "action",
        "bullish_score",
        "score_breakdown",
        "patterns",
        "risk",
        "price_history",
        "indicators",
        "fundamental",
    ]:
        assert key in first

    assert first["market"] in {"US", "BIST"}
    assert isinstance(first["bullish_score"], int)
    assert 0 <= first["bullish_score"] <= 100


def test_pattern_fields_and_price_history_integrity(api_client: requests.Session, scan_completed):
    response = api_client.get(f"{API_BASE}/signals", params={"limit": 200}, timeout=45)
    assert response.status_code == 200
    signals = response.json()
    assert len(signals) > 0

    any_pattern_seen = False
    for signal in signals:
        assert isinstance(signal.get("price_history", []), list)
        history = signal["price_history"]
        assert len(history) > 0
        sample = history[0]
        assert isinstance(sample.get("date"), str)
        assert isinstance(sample.get("close"), (int, float))
        assert isinstance(sample.get("volume"), (int, float))

        patterns = signal.get("patterns", [])
        for pattern in patterns:
            any_pattern_seen = True
            assert pattern["name"] in {
                "Double Top",
                "Double Bottom",
                "Head and Shoulders",
                "Inverse Head and Shoulders",
            }
            assert pattern["direction"] in {"bullish", "bearish"}
            assert isinstance(pattern["confirmed"], bool)
            assert "detail" in pattern and isinstance(pattern["detail"], str)
            assert isinstance(pattern.get("points", []), list)

    assert any_pattern_seen is True


def test_score_matrix_action_mapping_and_atr_risk(api_client: requests.Session, scan_completed):
    response = api_client.get(f"{API_BASE}/signals", params={"limit": 200}, timeout=45)
    assert response.status_code == 200
    signals = response.json()
    assert len(signals) > 0

    for signal in signals:
        score = signal["bullish_score"]
        expected = expected_action_for_score(score)
        assert signal["action"] == expected

        breakdown = signal["score_breakdown"]
        assert set(breakdown.keys()) == {"technical", "moving_average", "volume", "fundamental"}
        assert isinstance(breakdown["technical"], int)
        assert isinstance(breakdown["moving_average"], int)
        assert isinstance(breakdown["volume"], int)
        assert isinstance(breakdown["fundamental"], int)

        risk = signal["risk"]
        assert "entry_price" in risk
        assert "stop_loss" in risk
        assert "take_profit" in risk


def test_explain_endpoint_returns_turkish_three_part_summary(api_client: requests.Session, scan_completed):
    signals_resp = api_client.get(f"{API_BASE}/signals", params={"limit": 10}, timeout=45)
    assert signals_resp.status_code == 200
    signals = signals_resp.json()
    assert len(signals) > 0

    symbol = signals[0]["symbol"]
    explain_resp = api_client.post(f"{API_BASE}/signals/{symbol}/explain", timeout=80)
    assert explain_resp.status_code == 200
    payload = explain_resp.json()
    assert payload["symbol"] == symbol

    summary = payload.get("summary", "")
    assert isinstance(summary, str)
    assert len(summary.strip()) > 30
    assert "1." in summary and "2." in summary and "3." in summary
    assert any(token in summary for token in ["Teknik", "Temel", "Aksiyon", "Risk", "sinyali"])
