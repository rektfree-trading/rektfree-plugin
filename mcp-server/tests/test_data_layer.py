"""Offline tests for the data layer (guards, timeframe map, retry helper)."""

import asyncio

import pytest

from data import binance
from tools._common import bias_str, crypto_only_error
from engines import smart_money


# --- shared guards --------------------------------------------------------

def test_crypto_only_error_rejects_forex():
    err = crypto_only_error("EUR_USD")
    assert err is not None and "forex" in err["error"].lower()


def test_crypto_only_error_allows_crypto():
    assert crypto_only_error("BTCUSDT") is None


def test_bias_str():
    assert bias_str(smart_money.BULLISH) == "bullish"
    assert bias_str(smart_money.BEARISH) == "bearish"
    assert bias_str(0) == "neutral"


# --- timeframe / parsing --------------------------------------------------

def test_normalize_timeframe_aliases():
    assert binance.normalize_timeframe("1H") == "1h"
    assert binance.normalize_timeframe("h4") == "4h"
    assert binance.normalize_timeframe("d") == "1d"


def test_normalize_timeframe_rejects_unknown():
    with pytest.raises(binance.BinanceError):
        binance.normalize_timeframe("3h")


def test_interval_seconds():
    assert binance.INTERVAL_SECONDS["1h"] == 3600
    assert binance.INTERVAL_SECONDS["1d"] == 86400


def test_parse_retry_after():
    assert binance._parse_retry_after("2") == 2.0
    assert binance._parse_retry_after(None) is None
    assert binance._parse_retry_after("garbage") is None


def test_kline_to_candle():
    row = [1_700_000_000_000, "100.5", "110", "99", "105", "12.5"]
    c = binance._kline_to_candle(row)
    assert c["time"] == 1_700_000_000.0
    assert c["open"] == 100.5 and c["high"] == 110.0
    assert c["low"] == 99.0 and c["close"] == 105.0 and c["volume"] == 12.5


# --- request_json retry/backoff (stub client, no network) -----------------

class _Resp:
    def __init__(self, status, body=None, text="", headers=None):
        self.status_code = status
        self._body = body
        self.text = text
        self.headers = headers or {}

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class _Client:
    """Minimal stand-in for httpx.AsyncClient that replays canned responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def get(self, url, params=None):
        item = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Make backoff instant so retry tests don't actually wait."""
    async def _instant(_seconds):
        return None
    monkeypatch.setattr(binance.asyncio, "sleep", _instant)


def test_request_json_retries_then_succeeds():
    client = _Client([_Resp(429, text="rl"), _Resp(429, text="rl"), _Resp(200, body=[1, 2, 3])])
    out = asyncio.run(binance.request_json(client, "klines", {"symbol": "BTCUSDT"}))
    assert out == [1, 2, 3]
    assert client.calls == 3


def test_request_json_exhausts_budget():
    client = _Client([_Resp(429, text="rl")])
    with pytest.raises(binance.BinanceError) as exc:
        asyncio.run(binance.request_json(client, "klines", {"symbol": "BTCUSDT"}))
    assert "after 4 attempts" in str(exc.value)
    assert client.calls == 4  # 1 + _MAX_RETRIES


def test_request_json_400_is_terminal():
    client = _Client([_Resp(400, body={"msg": "Invalid symbol."})])
    with pytest.raises(binance.BinanceError) as exc:
        asyncio.run(binance.request_json(client, "klines", {"symbol": "NOPE"}, context="request"))
    assert "rejected request for symbol 'NOPE': Invalid symbol." in str(exc.value)
    assert client.calls == 1  # no retry on a terminal 400


def test_request_json_network_error_retried():
    import httpx
    client = _Client([httpx.ConnectError("boom"), _Resp(200, body={"ok": 1})])
    out = asyncio.run(binance.request_json(client, "klines", {"symbol": "X"}))
    assert out == {"ok": 1}
    assert client.calls == 2
