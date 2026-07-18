"""
Tests for model.hazard_providers — the pre-trained flood (GloFAS) and landslide
(NASA LHASA) hazard signals. All network access is monkeypatched; these run
offline and fast, mirroring the pure-unit style of test_disaster_model_v2.py.
"""

from __future__ import annotations

import model.hazard_providers as hp
from model.areas import Area


def _areas(*specs):
    """Build a small {id: Area} map from (id, lat, lon) tuples."""
    return {
        aid: Area(aid, aid, "", 0, lat, lon)
        for aid, lat, lon in specs
    }


# ------------------------------------------------------------------
# Level mapping / percentile helpers
# ------------------------------------------------------------------

class TestLevelFromThresholds:
    THR = [0.10, 0.30, 0.50, 0.70]

    def test_below_all_is_level_1(self):
        assert hp.level_from_thresholds(0.0, self.THR) == 1
        assert hp.level_from_thresholds(0.09, self.THR) == 1

    def test_each_band(self):
        assert hp.level_from_thresholds(0.10, self.THR) == 2
        assert hp.level_from_thresholds(0.30, self.THR) == 3
        assert hp.level_from_thresholds(0.55, self.THR) == 4
        assert hp.level_from_thresholds(0.70, self.THR) == 5

    def test_capped_at_5(self):
        assert hp.level_from_thresholds(9.9, self.THR) == 5

    def test_empty_thresholds_is_level_1(self):
        assert hp.level_from_thresholds(100.0, []) == 1


class TestPercentile:
    def test_median_and_extremes(self):
        vals = list(range(0, 101))  # 0..100 sorted
        assert hp._percentile(vals, 0.0) == 0
        assert hp._percentile(vals, 1.0) == 100
        assert hp._percentile(vals, 0.5) == 50

    def test_empty(self):
        assert hp._percentile([], 0.9) == 0.0


# ------------------------------------------------------------------
# blend_external — the pure blend used per forecast hour
# ------------------------------------------------------------------

class TestBlendExternal:
    def test_missing_signals_keep_original(self):
        assert hp.blend_external(3, "storm", 0.5, None, None) == (3, "storm", 0.5)

    def test_weaker_signal_never_lowers(self):
        # existing storm level 4 must survive a flood level 2
        assert hp.blend_external(4, "storm", 0.6, {"level": 2}, None) == (4, "storm", 0.6)

    def test_flood_upgrades_and_sets_dominant(self):
        level, dominant, risk = hp.blend_external(
            1, "storm", 0.1, {"discharge": 9.0, "level": 4}, None
        )
        assert (level, dominant) == (4, "flood")
        assert risk == 0.8  # 4/5

    def test_landslide_upgrades(self):
        level, dominant, risk = hp.blend_external(
            2, "flood", 0.4, None, {"prob": 0.6, "level": 5}
        )
        assert (level, dominant) == (5, "landslide")
        assert risk == 1.0

    def test_more_alarming_of_the_two_wins(self):
        level, dominant, _ = hp.blend_external(
            1, "storm", 0.0, {"level": 3}, {"prob": 0.8, "level": 5}
        )
        assert (level, dominant) == (5, "landslide")

    def test_level_zero_signal_ignored(self):
        # a flood dict without a usable level (None) must not override
        assert hp.blend_external(2, "storm", 0.3, {"level": None}, None) == (2, "storm", 0.3)


# ------------------------------------------------------------------
# fetch_flood_levels — batched GloFAS discharge -> per-commune level
# ------------------------------------------------------------------

class TestFetchFloodLevels:
    def test_maps_discharge_to_levels(self, monkeypatch):
        areas = _areas(("a", 21.0, 103.0), ("b", 22.0, 104.0))
        monkeypatch.setattr(hp, "FLOOD_ENABLED", True)
        monkeypatch.setattr(hp, "FORECAST_DAYS", 3)
        monkeypatch.setattr(
            hp, "load_flood_climatology",
            lambda: {
                "a": {"thresholds": [10, 20, 30, 40]},
                "b": {"thresholds": [100, 200, 300, 400]},
            },
        )
        monkeypatch.setattr(hp, "_resilient_get", lambda *a, **k: [
            {"daily": {"river_discharge": [5.0, 25.0, 45.0]}},   # a: L1, L3, L5
            {"daily": {"river_discharge": [50.0, 250.0, None]}},  # b: L1, L3, (gap)
        ])

        out = hp.fetch_flood_levels(areas)

        assert out["a"] == {
            1: {"discharge": 5.0, "level": 1},
            2: {"discharge": 25.0, "level": 3},
            3: {"discharge": 45.0, "level": 5},
        }
        # None discharge day is skipped, not crashed
        assert set(out["b"]) == {1, 2}
        assert out["b"][2]["level"] == 3

    def test_missing_climatology_yields_none_level(self, monkeypatch):
        areas = _areas(("a", 21.0, 103.0))
        monkeypatch.setattr(hp, "FLOOD_ENABLED", True)
        monkeypatch.setattr(hp, "load_flood_climatology", lambda: {})  # no thresholds
        monkeypatch.setattr(hp, "_resilient_get", lambda *a, **k: [
            {"daily": {"river_discharge": [999.0]}},
        ])
        out = hp.fetch_flood_levels(areas)
        # discharge recorded, but level is None so it can't spuriously override
        assert out["a"][1] == {"discharge": 999.0, "level": None}

    def test_disabled_returns_empty(self, monkeypatch):
        monkeypatch.setattr(hp, "FLOOD_ENABLED", False)
        assert hp.fetch_flood_levels(_areas(("a", 1.0, 2.0))) == {}

    def test_failed_fetch_returns_empty_not_raise(self, monkeypatch):
        monkeypatch.setattr(hp, "FLOOD_ENABLED", True)
        monkeypatch.setattr(hp, "load_flood_climatology", lambda: {})
        monkeypatch.setattr(hp, "_resilient_get", lambda *a, **k: None)  # total failure
        assert hp.fetch_flood_levels(_areas(("a", 1.0, 2.0))) == {}


# ------------------------------------------------------------------
# fetch_landslide_levels — LHASA getSamples -> per-commune level
# ------------------------------------------------------------------

class TestFetchLandslideLevels:
    def test_parses_getsamples_and_maps_days(self, monkeypatch):
        areas = _areas(("a", 21.39, 103.02), ("b", 14.6, 121.0))
        monkeypatch.setattr(hp, "LANDSLIDE_ENABLED", True)

        # Same samples returned for both Today and Tomorrow services:
        # point 0 has an elevated prob, point 1 is NoData (empty value).
        def fake_get(url, params, timeout, label):
            return {"samples": [
                {"locationId": 0, "value": "0.55"},
                {"locationId": 1, "value": ""},
            ]}

        monkeypatch.setattr(hp, "_resilient_get", fake_get)
        out = hp.fetch_landslide_levels(areas)

        # area a present for both day 1 and day 2, mapped 0.55 -> level 4
        assert set(out["a"]) == {1, 2}
        assert out["a"][1] == {"prob": 0.55, "level": 4}
        # NoData point contributes nothing
        assert "b" not in out

    def test_day_fetch_failure_is_skipped(self, monkeypatch):
        areas = _areas(("a", 21.39, 103.02))
        monkeypatch.setattr(hp, "LANDSLIDE_ENABLED", True)
        # Today fails (None), Tomorrow succeeds.
        calls = {"n": 0}

        def fake_get(url, params, timeout, label):
            calls["n"] += 1
            if calls["n"] == 1:
                return None
            return {"samples": [{"locationId": 0, "value": "0.2"}]}

        monkeypatch.setattr(hp, "_resilient_get", fake_get)
        out = hp.fetch_landslide_levels(areas)
        # only the tomorrow day (offset 2) is present; no crash on the failed day
        assert set(out["a"]) == {2}
        assert out["a"][2]["level"] == 2

    def test_disabled_returns_empty(self, monkeypatch):
        monkeypatch.setattr(hp, "LANDSLIDE_ENABLED", False)
        assert hp.fetch_landslide_levels(_areas(("a", 1.0, 2.0))) == {}


# ------------------------------------------------------------------
# _resilient_get — retry/backoff must never raise on transient failure
# ------------------------------------------------------------------

class _Resp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


class TestResilientGet:
    def test_gives_up_gracefully_on_repeated_429(self, monkeypatch):
        monkeypatch.setattr(hp, "HAZARD_RETRIES", 2)
        monkeypatch.setattr(hp, "HAZARD_BACKOFF_S", [])  # no sleeping in tests
        monkeypatch.setattr(hp.requests, "get", lambda *a, **k: _Resp(429))
        assert hp._resilient_get("http://x", {}, 5, "t") is None

    def test_network_exception_returns_none(self, monkeypatch):
        monkeypatch.setattr(hp, "HAZARD_RETRIES", 1)
        monkeypatch.setattr(hp, "HAZARD_BACKOFF_S", [])

        def boom(*a, **k):
            raise ConnectionError("dns down")

        monkeypatch.setattr(hp.requests, "get", boom)
        assert hp._resilient_get("http://x", {}, 5, "t") is None

    def test_success_returns_payload(self, monkeypatch):
        monkeypatch.setattr(hp, "HAZARD_BACKOFF_S", [])
        monkeypatch.setattr(hp.requests, "get", lambda *a, **k: _Resp(200, {"ok": 1}))
        assert hp._resilient_get("http://x", {}, 5, "t") == {"ok": 1}

    def test_arcgis_error_body_is_retried_then_none(self, monkeypatch):
        monkeypatch.setattr(hp, "HAZARD_RETRIES", 1)
        monkeypatch.setattr(hp, "HAZARD_BACKOFF_S", [])
        monkeypatch.setattr(
            hp.requests, "get",
            lambda *a, **k: _Resp(200, {"error": {"code": 500, "message": "boom"}}),
        )
        assert hp._resilient_get("http://x", {}, 5, "t") is None

    def test_non_retryable_4xx_returns_none_immediately(self, monkeypatch):
        calls = {"n": 0}

        def counting(*a, **k):
            calls["n"] += 1
            return _Resp(400, text="bad request")

        monkeypatch.setattr(hp, "HAZARD_BACKOFF_S", [])
        monkeypatch.setattr(hp.requests, "get", counting)
        assert hp._resilient_get("http://x", {}, 5, "t") is None
        assert calls["n"] == 1  # not retried
