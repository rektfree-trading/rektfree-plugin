"""Offline, deterministic tests for the position-sizing tool's pure helpers.

These exercise the module-level math helpers directly (no network, no MCP
decorator). The ATR-derivation path that fetches candles lives in the tool
wrapper and is covered by the live suite, not here.
"""

import math

from tools.position_sizing import (
    compute_sizing,
    derive_stop_from_atr,
    infer_side,
)


# --- core sizing math -----------------------------------------------------

def test_basic_long_sizing():
    r = compute_sizing(account_equity=10_000, risk_pct=1, entry=100, stop=95)
    assert "error" not in r
    assert r["risk_amount"] == 100.0
    assert r["stop_distance"] == 5.0
    assert r["stop_distance_pct"] == 5.0
    assert r["position_size_units"] == 20.0
    assert r["notional_value"] == 2000.0
    assert r["side"] == "long"
    assert isinstance(r["notes"], list) and r["notes"]


def test_risk_pct_scales_amount_and_size():
    r = compute_sizing(account_equity=50_000, risk_pct=2, entry=200, stop=190)
    assert r["risk_amount"] == 1000.0          # 2% of 50k
    assert r["stop_distance"] == 10.0
    assert r["position_size_units"] == 100.0   # 1000 / 10
    assert r["notional_value"] == 20_000.0


# --- target / R:R ---------------------------------------------------------

def test_rr_with_target():
    r = compute_sizing(account_equity=10_000, risk_pct=1, entry=100, stop=95, target=115)
    assert r["target_distance"] == 15.0
    assert r["rr_ratio"] == 3.0                # 15 / 5
    assert r["reward_amount"] == 300.0         # 20 units * 15
    assert r["r_multiples"]["reward_R"] == 3.0
    # breakeven win-rate ~25% for 3R
    assert "25.0%" in r["r_multiples"]["note"]


def test_target_on_wrong_side_warns():
    # long but target below entry → warning, R:R still absolute
    r = compute_sizing(account_equity=10_000, risk_pct=1, entry=100, stop=95, target=90)
    assert "target_warning" in r
    assert r["target_distance"] == 10.0


# --- side inference -------------------------------------------------------

def test_short_side_inference():
    # stop above entry → short
    r = compute_sizing(account_equity=10_000, risk_pct=1, entry=100, stop=105)
    assert r["side"] == "short"
    assert r["stop_distance"] == 5.0
    assert r["position_size_units"] == 20.0


def test_explicit_side_overrides():
    assert infer_side(entry=100, stop=0, target=0, side="short") == "short"
    assert infer_side(entry=100, stop=0, target=0, side="buy") == "long"


def test_infer_from_target_when_no_stop():
    assert infer_side(entry=100, stop=0, target=120) == "long"
    assert infer_side(entry=100, stop=0, target=80) == "short"


# --- leverage / margin ----------------------------------------------------

def test_leverage_margin():
    r = compute_sizing(account_equity=10_000, risk_pct=1, entry=100, stop=95, leverage=10)
    assert r["notional_value"] == 2000.0
    assert r["required_margin"] == 200.0       # 2000 / 10
    assert r["leverage"] == 10


def test_no_leverage_no_margin_key():
    r = compute_sizing(account_equity=10_000, risk_pct=1, entry=100, stop=95)
    assert "required_margin" not in r


# --- ATR-derived stop helper ----------------------------------------------

def test_derive_stop_from_atr_long_and_short():
    assert derive_stop_from_atr(entry=100, atr=2, mult=1.5, side="long") == 97.0
    assert derive_stop_from_atr(entry=100, atr=2, mult=1.5, side="short") == 103.0


def test_derive_stop_bad_inputs():
    assert derive_stop_from_atr(entry=0, atr=2, mult=1.5, side="long") == 0.0
    assert derive_stop_from_atr(entry=100, atr=0, mult=1.5, side="long") == 0.0
    assert derive_stop_from_atr(entry=100, atr=2, mult=0, side="long") == 0.0


# --- bad input → error dicts (never raise) --------------------------------

def test_bad_equity():
    assert "error" in compute_sizing(account_equity=0, risk_pct=1, entry=100, stop=95)
    assert "error" in compute_sizing(account_equity=-5, risk_pct=1, entry=100, stop=95)


def test_bad_risk_pct():
    assert "error" in compute_sizing(account_equity=10_000, risk_pct=0, entry=100, stop=95)
    assert "error" in compute_sizing(account_equity=10_000, risk_pct=150, entry=100, stop=95)


def test_bad_entry():
    assert "error" in compute_sizing(account_equity=10_000, risk_pct=1, entry=0, stop=95)


def test_stop_equals_entry():
    assert "error" in compute_sizing(account_equity=10_000, risk_pct=1, entry=100, stop=100)


def test_missing_stop():
    assert "error" in compute_sizing(account_equity=10_000, risk_pct=1, entry=100, stop=0)


def test_long_with_stop_above_entry_when_side_forced():
    # forcing long but stop above entry is contradictory → error
    r = compute_sizing(account_equity=10_000, risk_pct=1, entry=100, stop=105, side="long")
    assert "error" in r


def test_short_with_stop_below_entry_when_side_forced():
    r = compute_sizing(account_equity=10_000, risk_pct=1, entry=100, stop=95, side="short")
    assert "error" in r
