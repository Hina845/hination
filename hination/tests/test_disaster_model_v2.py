"""
Tests for disaster_model_v2 - ML-enhanced disaster prediction.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from model.disaster_model_v2 import (
    TerrainProfile,
    terrain_for_area,
    compute_api,
    compute_flood_risk_heuristic,
    compute_landslide_risk_heuristic,
    compute_storm_risk_heuristic,
    compute_wildfire_risk_heuristic,
    SOIL_LANDSLIDE_FACTOR,
    DISTRICTS_TERRAIN,
)


class TestComputeApi:
    """Test Antecedent Precipitation Index calculation."""

    def test_api_no_rain(self):
        assert compute_api([]) == 0.0
        assert compute_api([0, 0, 0]) == 0.0

    def test_api_single_day(self):
        assert compute_api([10.0]) == 10.0

    def test_api_with_decay(self):
        # API = 10 + 5*0.85 + 3*0.85^2 = 10 + 4.25 + 2.1675 = 16.4175
        result = compute_api([10.0, 5.0, 3.0], decay=0.85)
        assert result == pytest.approx(16.42, abs=0.01)

    def test_api_recent_matter_more(self):
        # Recent rain weighs more
        recent_heavy = compute_api([50.0, 0.0, 0.0], decay=0.85)
        old_heavy = compute_api([0.0, 0.0, 50.0], decay=0.85)
        assert recent_heavy > old_heavy


class TestTerrainForArea:
    """Test terrain profile resolution."""

    def test_calibrated_area_returns_calibrated(self):
        """Calibrated areas should have source='calibrated'."""
        weather_area = {"elevation": 483}
        profile = terrain_for_area("dien_bien_phu", weather_area)
        
        assert profile.profile_source == "calibrated"
        assert profile.confidence >= 0.9
        assert profile.slope == 8  # Valley floor

    def test_uncalibrated_area_returns_elevation_derived(self):
        """Uncalibrated areas should have source='elevation_derived'."""
        weather_area = {"elevation": 700}
        profile = terrain_for_area("commune_19537811", weather_area)
        
        assert profile.profile_source == "elevation_derived"
        assert profile.confidence < 0.6  # Low confidence

    def test_calibrated_areas_have_correct_slopes(self):
        """Calibrated areas should have realistic slopes."""
        calibrated = {
            "dien_bien_phu": 8,      # Valley
            "tua_chua": 35,           # Mountain
            "muong_nhe": 30,          # Highland
        }
        
        for area_id, expected_slope in calibrated.items():
            weather_area = {"elevation": DISTRICTS_TERRAIN.get(area_id, {}).get("elev", 500)}
            profile = terrain_for_area(area_id, weather_area)
            assert profile.slope == expected_slope, f"{area_id} slope mismatch"


class TestFloodRisk:
    """Test flood risk calculation."""

    def test_no_rain_low_flood(self):
        risk = compute_flood_risk_heuristic(0, 0, 0, 0, 0.3)
        assert risk < 0.1  # Very low risk, not exactly zero due to terrain

    def test_light_rain_low_flood(self):
        risk = compute_flood_risk_heuristic(1, 5, 10, 5, 0.3)
        assert risk < 0.2

    def test_extreme_rain_high_flood(self):
        risk = compute_flood_risk_heuristic(50, 150, 300, 100, 0.8)
        assert risk >= 0.8

    def test_low_lying_area_higher_risk(self):
        risk_high = compute_flood_risk_heuristic(20, 50, 100, 50, 0.8)
        risk_low = compute_flood_risk_heuristic(20, 50, 100, 50, 0.2)
        assert risk_high > risk_low

    def test_risk_capped_at_1(self):
        risk = compute_flood_risk_heuristic(100, 500, 1000, 500, 1.0)
        assert risk <= 1.0


class TestLandslideRisk:
    """Test landslide risk calculation."""

    def test_no_rain_no_landslide(self):
        risk = compute_landslide_risk_heuristic(10, 30, "clay", 5, 0, 0.9)
        assert risk == 0.0

    def test_steep_slope_high_risk(self):
        risk = compute_landslide_risk_heuristic(100, 45, "rocky_soil", 80, 0, 0.9)
        assert risk >= 0.7

    def test_gentle_slope_lower_risk(self):
        risk = compute_landslide_risk_heuristic(100, 10, "alluvial", 80, 0, 0.9)
        # Gentle slope + alluvial soil = low risk
        assert risk < 0.5

    def test_history_increases_risk(self):
        risk_no_history = compute_landslide_risk_heuristic(100, 30, "clay", 50, 0, 0.9)
        risk_with_history = compute_landslide_risk_heuristic(100, 30, "clay", 50, 3, 0.9)
        assert risk_with_history > risk_no_history

    def test_uncalibrated_terrain_reduces_risk(self):
        """Uncalibrated terrain (low confidence) should reduce landslide risk."""
        risk_calibrated = compute_landslide_risk_heuristic(100, 30, "clay", 50, 0, 0.9)
        risk_uncalibrated = compute_landslide_risk_heuristic(100, 30, "clay", 50, 0, 0.4)
        
        # With low confidence, risk should be significantly reduced
        assert risk_uncalibrated < risk_calibrated * 0.5


class TestStormRisk:
    """Test storm risk calculation."""

    def test_calm_no_storm(self):
        risk = compute_storm_risk_heuristic(20, 0, 1, 50)
        assert risk == 0.0

    def test_strong_wind_no_rain_no_storm(self):
        risk = compute_storm_risk_heuristic(70, 0, 1, 50)
        assert risk == 0.0

    def test_wind_and_rain_storm(self):
        risk = compute_storm_risk_heuristic(70, 5, 10, 85)
        assert risk >= 0.3

    def test_danger_wind_full_storm(self):
        risk = compute_storm_risk_heuristic(100, 10, 20, 90)
        assert risk >= 0.7


class TestWildfireRisk:
    """Test wildfire risk calculation."""

    def test_recent_rain_no_wildfire(self):
        risk = compute_wildfire_risk_heuristic(35, 50, 20, 20)
        assert risk == 0.0

    def test_hot_dry_high_wildfire(self):
        risk = compute_wildfire_risk_heuristic(38, 30, 25, 0)
        assert risk >= 0.5

    def test_cool_humid_no_wildfire(self):
        # Very cool, very humid, calm - minimal fire risk
        risk = compute_wildfire_risk_heuristic(10, 98, 1, 0)
        assert risk < 0.05  # Very low risk


class TestSoilFactors:
    """Test soil susceptibility factors."""

    def test_all_soil_types_present(self):
        expected = {"alluvial", "clay_loam", "clay", "rocky_soil", "karst"}
        assert set(SOIL_LANDSLIDE_FACTOR.keys()) == expected

    def test_factor_ordering(self):
        """Rocky soil should have highest landslide susceptibility."""
        assert SOIL_LANDSLIDE_FACTOR["rocky_soil"] > SOIL_LANDSLIDE_FACTOR["clay"]
        assert SOIL_LANDSLIDE_FACTOR["clay"] > SOIL_LANDSLIDE_FACTOR["alluvial"]


class TestV2VsV1Comparison:
    """Compare v2 model improvements over v1."""

    def test_api_now_used_in_flood_calculation(self):
        """V2 should use API in flood risk."""
        # In v2, flood risk includes api_7d
        # This test verifies the function signature accepts it
        risk = compute_flood_risk_heuristic(10, 30, 100, 50, 0.5)
        assert risk >= 0.2

    def test_terrain_confidence_affects_landslide(self):
        """V2 should adjust landslide risk based on terrain confidence."""
        risk_calibrated = compute_landslide_risk_heuristic(100, 30, "clay", 60, 0, 0.95)
        risk_uncalibrated = compute_landslide_risk_heuristic(100, 30, "clay", 60, 0, 0.4)
        
        # Uncalibrated terrain should have significantly reduced risk
        assert risk_uncalibrated < risk_calibrated * 0.4

    def test_wildfire_threshold_increased(self):
        """V2 increased wildfire fire-off threshold from 5 to 12mm."""
        # 8mm rain should still allow wildfire risk in v2
        risk = compute_wildfire_risk_heuristic(35, 40, 15, 8)
        # In v1 this would be 0, in v2 should be > 0
        # (threshold is 12mm, so 8mm doesn't extinguish)
        assert risk > 0
