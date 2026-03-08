import os
import time
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

# API coverage: hybrid 500/500 market universe, scanner stability, on-demand analyze/reanalyze,
# pattern payload fields (Cup&Handle + Symmetrical Triangle), visualize/explain integration,
# weighted scoring model (40/30/30), and fundamental hard-cap rule.


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


def _request_with_retry(method, url, retries=1, **kwargs):
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return method(url, **kwargs)
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(1)
    raise last_exc


@pytest.fixture(scope="session")
def api_client() -> requests.Session:
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="session")
def scanned_state(api_client: requests.Session):
    trigger = _request_with_retry(api_client.post, f"{API_BASE}/scanner/run", timeout=60, retries=1)
    assert trigger.status_code == 200
    trigger_data = trigger.json()
    assert trigger_data.get("status") in {"started", "already_running"}

    # Verify state endpoint remains stable during expanded-universe scans.
    seen_running_state = False
    last_state = None
    for _ in range(20):
        poll = _request_with_retry(api_client.get, f"{API_BASE}/scanner/state", timeout=60, retries=1)
        assert poll.status_code == 200
        state = poll.json()
        assert isinstance(state.get("running"), bool)
        assert isinstance(state.get("last_scanned_count"), int)
        if state.get("running") is True:
            seen_running_state = True
        last_state = state
        time.sleep(1.2)

    assert last_state is not None
    # Accept either (still running) or (already completed), but state schema must be valid.
    assert isinstance(last_state.get("last_error"), (str, type(None)))
    return {"seen_running_state": seen_running_state, "last_state": last_state}


@pytest.fixture(scope="session")
def analyzed_symbols(api_client: requests.Session):
    out = {}
    for symbol in ["PENTA", "RIVN"]:
        response = None
        for _ in range(4):
            response = _request_with_retry(
                api_client.post,
                f"{API_BASE}/signals/analyze/{symbol}",
                timeout=120,
                retries=1,
            )
            if response.status_code == 200:
                break
            time.sleep(2)

        assert response is not None
        assert response.status_code == 200, response.text
        payload = response.json()
        out[symbol] = payload

        assert payload["symbol"] in {symbol, f"{symbol}.IS"}
        assert payload["market"] in {"US", "BIST"}
        assert isinstance(payload.get("patterns", []), list)
        assert isinstance(payload.get("price_history", []), list)
        assert len(payload.get("price_history", [])) > 0
        assert isinstance(payload.get("score_breakdown"), dict)
        assert isinstance(payload.get("risk"), dict)
    return out


def _assert_weighted_breakdown(signal: dict):
    breakdown = signal["score_breakdown"]
    required_keys = {
        "technical",
        "fundamental",
        "volume",
        "raw_technical",
        "raw_fundamental",
        "raw_volume",
    }
    assert required_keys.issubset(set(breakdown.keys()))

    assert 0 <= breakdown["technical"] <= 40
    assert 0 <= breakdown["fundamental"] <= 30
    assert 0 <= breakdown["volume"] <= 30

    assert breakdown["technical"] == int(round(breakdown["raw_technical"] * 0.40))
    assert breakdown["fundamental"] == int(round(breakdown["raw_fundamental"] * 0.30))
    assert breakdown["volume"] == int(round(breakdown["raw_volume"] * 0.30))


# --- Core endpoint and payload contract tests ---

def test_config_returns_500_us_and_500_bist(api_client: requests.Session):
    response = _request_with_retry(api_client.get, f"{API_BASE}/config", timeout=90, retries=1)
    assert response.status_code == 200
    data = response.json()

    assert data["refresh_seconds"] == 300
    assert len(data["markets"]["US"]) == 500
    assert len(data["markets"]["BIST"]) == 500
    assert all(symbol.endswith(".IS") for symbol in data["markets"]["BIST"])


def test_scanner_state_endpoint_stability(scanned_state):
    assert "seen_running_state" in scanned_state
    assert "last_state" in scanned_state


def test_on_demand_analyze_out_of_universe_symbols(analyzed_symbols):
    assert "PENTA" in analyzed_symbols
    assert "RIVN" in analyzed_symbols


def test_reanalyze_refreshes_same_symbol(api_client: requests.Session, analyzed_symbols):
    original = analyzed_symbols["RIVN"]
    symbol = original["symbol"]

    response = _request_with_retry(api_client.post, f"{API_BASE}/signals/{symbol}/reanalyze", timeout=120, retries=1)
    assert response.status_code == 200
    refreshed = response.json()

    assert refreshed["symbol"] == symbol
    assert refreshed["market"] == original["market"]
    assert refreshed["updated_at"] >= original["updated_at"]


def test_pattern_payload_supports_cup_and_handle_and_sym_triangle(api_client: requests.Session, analyzed_symbols):
    checked_patterns = []
    target_names = {"Cup and Handle", "Symmetrical Triangle"}

    symbols_to_check = {analyzed_symbols["PENTA"]["symbol"], analyzed_symbols["RIVN"]["symbol"]}
    list_response = _request_with_retry(
        api_client.get,
        f"{API_BASE}/signals",
        params={"limit": 200},
        timeout=90,
        retries=1,
    )
    assert list_response.status_code == 200
    for signal in list_response.json():
        symbols_to_check.add(signal["symbol"])

    matched_new_pattern = False
    for symbol in list(symbols_to_check)[:30]:
        detail = _request_with_retry(api_client.get, f"{API_BASE}/signals/{symbol}", timeout=60, retries=1)
        if detail.status_code != 200:
            continue
        payload = detail.json()
        for pattern in payload.get("patterns", []):
            checked_patterns.append(pattern.get("name"))
            if pattern.get("name") in target_names:
                matched_new_pattern = True
                assert isinstance(pattern.get("confirmed"), bool)
                assert isinstance(pattern.get("volume_validated"), bool)
                assert isinstance(pattern.get("points", []), list)
                assert isinstance(pattern.get("geometry", {}), dict)
                assert isinstance(pattern.get("detail", ""), str)

    assert len(checked_patterns) > 0
    # If this fails, either pattern detector never outputs new names or market data window didn't hit them.
    assert matched_new_pattern is True


def test_visualize_and_explain_return_image_and_summary(api_client: requests.Session, analyzed_symbols):
    symbol = analyzed_symbols["PENTA"]["symbol"]

    visualize_resp = _request_with_retry(api_client.post, f"{API_BASE}/signals/{symbol}/visualize", timeout=120, retries=1)
    assert visualize_resp.status_code == 200
    vis_payload = visualize_resp.json()
    assert vis_payload["symbol"] == symbol

    image_url = vis_payload.get("pattern_image_url")
    if image_url:
        image_absolute = image_url if image_url.startswith("http") else f"{BASE_URL}{image_url}"
        image_check = _request_with_retry(api_client.get, image_absolute, timeout=60, retries=1)
        assert image_check.status_code == 200
        assert image_check.headers.get("content-type", "").startswith("image/")

    explain_resp = _request_with_retry(api_client.post, f"{API_BASE}/signals/{symbol}/explain", timeout=180, retries=1)
    assert explain_resp.status_code == 200
    explain_payload = explain_resp.json()

    assert explain_payload["symbol"] == symbol
    assert isinstance(explain_payload.get("summary"), str)
    assert len(explain_payload.get("summary", "").strip()) > 40
    if explain_payload.get("pattern_image_url"):
        assert isinstance(explain_payload["pattern_image_url"], str)


def test_score_breakdown_respects_40_30_30_weights(api_client: requests.Session, analyzed_symbols):
    symbols = [analyzed_symbols["PENTA"]["symbol"], analyzed_symbols["RIVN"]["symbol"]]
    for symbol in symbols:
        detail = _request_with_retry(api_client.get, f"{API_BASE}/signals/{symbol}", timeout=90, retries=1)
        assert detail.status_code == 200
        payload = detail.json()
        _assert_weighted_breakdown(payload)


def test_fundamental_hard_cap_behavior_if_triggered(api_client: requests.Session):
    response = _request_with_retry(
        api_client.get,
        f"{API_BASE}/signals",
        params={"limit": 500},
        timeout=120,
        retries=1,
    )
    assert response.status_code == 200
    signals = response.json()
    assert len(signals) > 0

    def _assert_cap(signal: dict) -> bool:
        fundamental = signal.get("fundamental") or {}
        hard_cap_trigger = bool(fundamental.get("hard_cap_trigger"))
        current_ratio = fundamental.get("current_ratio")
        eps_growth = fundamental.get("eps_growth_qoq")

        if hard_cap_trigger:
            assert signal.get("bullish_score", 100) <= 45
            assert (current_ratio is not None and current_ratio < 0.75) or (
                eps_growth is not None and eps_growth < 0
            )
            return True
        return False

    triggered_count = sum(1 for signal in signals if _assert_cap(signal))

    # If current scan cache has no triggered examples, probe a few known high-beta symbols on-demand.
    if triggered_count == 0:
        probe_symbols = ["RIVN", "NIO", "SOFI", "AAL", "F", "PENTA", "KARSN"]
        for symbol in probe_symbols:
            probe = _request_with_retry(api_client.post, f"{API_BASE}/signals/analyze/{symbol}", timeout=120, retries=1)
            if probe.status_code != 200:
                continue
            if _assert_cap(probe.json()):
                triggered_count += 1
                break

    if triggered_count == 0:
        pytest.skip("No hard_cap_trigger=true sample returned by external fundamentals during this run")
