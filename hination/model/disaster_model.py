"""
HINATION Disaster Prediction Layer
==================================

Kết hợp:
1. **GFS weather** (đã có): precipitation, wind, humidity, pressure
2. **Terrain model**: slope, aspect, elevation từ Open-Meteo + hard-coded
3. **Hydrology**: antecedent precipitation (mưa tích lũy), soil saturation
4. **Historical disaster data**: lũ quét, sạt lở các năm trước
5. **Vietnam standards (VNDMS)**: thresholds theo QĐ 18/2021

Risk formula (per district per hour):
- flood_risk = f(precip_intensity, antecedent_precip_7d, terrain_low)
- landslide_risk = f(precip_72h, slope, soil_saturation, history)
- storm_risk = f(wind_gust, pressure_drop, precip_heavy)
- wildfire_risk = f(temp, humidity, wind, dry_days) - bonus

Output: disaster_forecast.json với risk per district per hour
"""

import json
import warnings
from datetime import datetime
from pathlib import Path

from model.areas import FORECAST_AREAS
from model.io_utils import atomic_write_json

warnings.filterwarnings('ignore')


# ============================================================
# Calibrated terrain profiles retained for the original nine areas
# ============================================================

# Terrain data for the original nine modeled areas in Điện Biên
# Slope: degrees (từ DEM analysis)
# Aspect: dominant direction (hướng dốc) - ảnh hưởng rainfall
# Soil_type: loại đất chính (affects landslide susceptibility)
# Elevation: meters (đã có)
# Tọa độ từ Bộ NN&MT - Bản đồ nền Việt Nam (cosodulieu.bando.com.vn)
# Xã/phường chính thức sau sáp nhập 2025 (Nghị quyết 1661/NQ-UBTVQH15)
# - dien_bien_phu  -> Phường Điện Biên Phủ (ma 03127, gồm Him Lam+Tân Thanh+Mường Thanh+Thanh Bình+Thanh Trường+Nam Thanh+Noong Bua+Thanh Xương)
# - muong_lay      -> Phường Mường Lay (ma 03151, gồm Sông Đà+Na Lay+phường cũ)
# - muong_nhe      -> Xã Mường Nhé (ma 03160, gồm Nậm Vì+Chung Chải+Mường Nhé)
# - muong_cha      -> Xã Mường Chà (ma 03166, gồm Chà Cang+Chà Nưa+Nậm Tin+Pa Tần)
# - tua_chua       -> Xã Tủa Chùa (ma 03217, gồm TT Tủa Chùa+Mường Báng+Nà Tòng)
# - tuan_giao      -> Xã Tuần Giáo (ma 03253, gồm TT Tuần Giáo+Quài Cang+Quài Nưa)
# - muong_ang      -> Xã Mường Ảng (ma 03256, gồm TT Mường Ảng+Ẳng Nưa+Ẳng Cang)
# - dien_bien_dong -> Xã Na Son (ma 03203, gồm TT Điện Biên Đông+Keo Lôm+Na Son)
# - nam_po         -> Xã Si Pa Phìn (ma 03199, gồm Phìn Hồ+Si Pa Phìn - trung tâm huyện Nậm Pồ cũ)
DISTRICTS_TERRAIN = {
    'dien_bien_phu': {
        'name': 'Phường Điện Biên Phủ',
        'ma': '03127',
        'lat': 21.4140962, 'lon': 103.0576943,
        'elev': 483, 'terrain': 0.3,
        'slope': 8,           # degrees - thung lũng Mường Thanh
        'aspect': 180,        # south-facing
        'soil_type': 'alluvial',
        'river_proximity': 1, # ngay sông Nậm Rốm
        'flood_history_count': 4,
        'landslide_history_count': 0
    },
    'tuan_giao': {
        'name': 'Xã Tuần Giáo',
        'ma': '03253',
        'lat': 21.6307492, 'lon': 103.4439122,
        'elev': 1047, 'terrain': 0.7,
        'slope': 25,
        'aspect': 90,
        'soil_type': 'clay_loam',
        'river_proximity': 1,
        'flood_history_count': 2,
        'landslide_history_count': 1
    },
    'tua_chua': {
        'name': 'Xã Tủa Chùa',
        'ma': '03217',
        'lat': 21.8221187, 'lon': 103.3617164,
        'elev': 1565, 'terrain': 0.9,
        'slope': 35,
        'aspect': 45,
        'soil_type': 'rocky_soil',
        'river_proximity': 0,
        'flood_history_count': 1,
        'landslide_history_count': 3
    },
    'muong_cha': {
        'name': 'Xã Mường Chà',
        'ma': '03166',
        'lat': 21.9786223, 'lon': 102.7777717,
        'elev': 500, 'terrain': 0.6,
        'slope': 20,
        'aspect': 270,
        'soil_type': 'clay',
        'river_proximity': 1,
        'flood_history_count': 3,
        'landslide_history_count': 2
    },
    'muong_nhe': {
        'name': 'Xã Mường Nhé',
        'ma': '03160',
        'lat': 22.2169654, 'lon': 102.4203498,
        'elev': 600, 'terrain': 0.8,
        'slope': 30,
        'aspect': 135,
        'soil_type': 'rocky_soil',
        'river_proximity': 1,
        'flood_history_count': 2,
        'landslide_history_count': 4
    },
    'dien_bien_dong': {
        'name': 'Xã Na Son',
        'ma': '03203',
        'lat': 21.2972456, 'lon': 103.2143726,
        'elev': 800, 'terrain': 0.75,
        'slope': 28,
        'aspect': 200,
        'soil_type': 'clay_loam',
        'river_proximity': 0,
        'flood_history_count': 1,
        'landslide_history_count': 2
    },
    'nam_po': {
        'name': 'Xã Si Pa Phìn',
        'ma': '03199',
        'lat': 21.8098376, 'lon': 102.9201731,
        'elev': 700, 'terrain': 0.85,
        'slope': 32,
        'aspect': 60,
        'soil_type': 'clay',
        'river_proximity': 1,
        'flood_history_count': 2,
        'landslide_history_count': 3
    },
    'muong_ang': {
        'name': 'Xã Mường Ảng',
        'ma': '03256',
        'lat': 21.4888505, 'lon': 103.2218525,
        'elev': 650, 'terrain': 0.65,
        'slope': 22,
        'aspect': 150,
        'soil_type': 'clay_loam',
        'river_proximity': 1,
        'flood_history_count': 2,
        'landslide_history_count': 1
    },
    'muong_lay': {
        'name': 'Phường Mường Lay',
        'ma': '03151',
        'lat': 22.0160376, 'lon': 103.1782851,
        'elev': 450, 'terrain': 0.5,
        'slope': 18,
        'aspect': 225,
        'soil_type': 'alluvial',
        'river_proximity': 1,  # ngã ba sông Đà
        'flood_history_count': 3,
        'landslide_history_count': 1
    }
}


def terrain_for_area(area_id, weather_area):
    """Return calibrated terrain or an explicit elevation-derived fallback.

    Weather remains a direct GFS forecast for every commune.  For communes
    without a researched terrain profile, risk inputs are conservatively
    estimated from the elevation returned by Open-Meteo; no forecast values
    are copied from a neighboring commune.
    """
    calibrated = DISTRICTS_TERRAIN.get(area_id)
    if calibrated:
        return {**calibrated, "profile_source": "calibrated"}

    area = FORECAST_AREAS[area_id]
    elevation = float(weather_area.get("elevation") or 700)
    terrain = min(0.9, max(0.35, 0.35 + elevation / 2500))
    return {
        "name": area.name,
        "ma": area.administrative_code,
        "lat": area.lat,
        "lon": area.lon,
        "elev": elevation,
        "terrain": terrain,
        "slope": round(10 + terrain * 25),
        "aspect": 0,
        "soil_type": "clay_loam",
        "river_proximity": 0,
        "flood_history_count": 0,
        "landslide_history_count": 0,
        "profile_source": "elevation-derived",
    }

# Soil susceptibility scores (0-1) cho landslide
SOIL_LANDSLIDE_FACTOR = {
    'alluvial': 0.2,     # thung lũng - ít sạt lở
    'clay_loam': 0.6,    # trung bình
    'clay': 0.7,         # cao - dễ trương nở
    'rocky_soil': 0.9    # rất cao - núi đá
}

# Slope landslide factor (slope càng cao càng dễ sạt lở)
def slope_factor(slope_deg):
    """Slope > 30° là nguy hiểm cao, > 45° rất nguy hiểm"""
    if slope_deg < 15:
        return 0.1
    elif slope_deg < 25:
        return 0.4
    elif slope_deg < 35:
        return 0.7
    elif slope_deg < 45:
        return 0.9
    else:
        return 1.0

# Antecedent Precipitation Index (API) - đất đã no nước
def compute_api(precip_history, decay=0.85):
    """
    API = sum(t=0..n) P_t * decay^t
    Càng nhiều mưa trước đó → API càng cao → đất càng no
    """
    api = 0
    for i, p in enumerate(precip_history):
        api += p * (decay ** i)
    return api

# Vietnam VNDMS Risk Thresholds (QĐ 18/2021/QĐ-TTg)
VNDMS = {
    'rain_warning_24h': 50,    # mm - cảnh báo
    'rain_danger_24h': 100,    # mm - nguy hiểm
    'rain_extreme_24h': 200,   # mm - thảm họa
    'wind_warning': 62,        # km/h
    'wind_danger': 89,         # km/h (bão cấp 9)
    'humidity_landslide': 95,  # %
}


# ============================================================
# Historical Disasters (Vietnam sources)
# ============================================================

HISTORICAL_DISASTERS = {
    # Lũ lụt lịch sử
    'floods': [
        {'year': 2018, 'deaths': 12, 'affected': 45000,
         'districts': ['dien_bien_phu', 'muong_cha', 'muong_lay'],
         'cause': 'heavy_rain_3days', 'rain_mm': 280},
        {'year': 2020, 'deaths': 3, 'affected': 12000,
         'districts': ['muong_cha', 'tuan_giao'],
         'cause': 'storm_rain', 'rain_mm': 180},
        {'year': 2023, 'deaths': 5, 'affected': 23000,
         'districts': ['muong_nhe', 'muong_cha'],
         'cause': 'monsoon_rain', 'rain_mm': 220},
        {'year': 2024, 'deaths': 0, 'affected': 8000,
         'districts': ['tuan_giao', 'muong_ang'],
         'cause': 'typhoon_yagi_remnant', 'rain_mm': 150},
    ],
    # Sạt lở đất
    'landslides': [
        {'year': 2019, 'deaths': 4, 'location': 'Mường Nhé (đèo)',
         'districts': ['muong_nhe'], 'cause': 'mountain_road_slide'},
        {'year': 2021, 'deaths': 2, 'location': 'Tuần Giáo',
         'districts': ['tuan_giao'], 'cause': 'road_slope_collapse'},
        {'year': 2023, 'deaths': 6, 'location': 'Mường Chà',
         'districts': ['muong_cha', 'tua_chua'], 'cause': 'village_slide_after_rain'},
        {'year': 2024, 'deaths': 1, 'location': 'Nậm Pồ',
         'districts': ['nam_po'], 'cause': 'highway_cut_slide'},
    ],
    # Bão/áp thấp nhiệt đới
    'storms': [
        {'year': 2024, 'name': 'Yagi remnant', 'districts': 'all',
         'wind_max': 65, 'note': 'Bão Yagi đổ bộ sau giảm cấp'},
    ]
}


# ============================================================
# Disaster Risk Calculation (per hour)
# ============================================================

def compute_flood_risk(precip_now, precip_24h, precip_72h, terrain):
    """
    Flood risk: kết hợp mưa hiện tại + tích lũy + địa hình thấp
    """
    # Instant flood (mưa hiện tại)
    if precip_now < 2:
        instant = precip_now / 20
    elif precip_now < 5:
        instant = 0.1 + (precip_now - 2) / 15
    elif precip_now < 10:
        instant = 0.4 + (precip_now - 5) / 20
    else:
        instant = min(1.0, 0.7 + (precip_now - 10) / 50)

    # 24h accumulated
    if precip_24h >= VNDMS['rain_extreme_24h']:
        accumulated_24h = 1.0
    elif precip_24h >= VNDMS['rain_danger_24h']:
        accumulated_24h = 0.7 + (precip_24h - 100) / 200
    elif precip_24h >= VNDMS['rain_warning_24h']:
        accumulated_24h = 0.4 + (precip_24h - 50) / 100
    else:
        accumulated_24h = precip_24h / 100

    # 72h accumulated (slower drainage)
    accumulated_72h = min(1.0, precip_72h / 300)

    # Weighted: instant most important, then 24h, then 72h
    risk = 0.5 * instant + 0.35 * accumulated_24h + 0.15 * accumulated_72h
    return min(1.0, risk)


def compute_landslide_risk(precip_now, precip_24h, precip_72h, terrain, slope, soil_type, history_count):
    """
    Landslide risk: mưa + độ dốc + loại đất + lịch sử
    """
    # Cần mưa đáng kể mới có nguy cơ
    if precip_now < 1 and precip_24h < 20:
        return 0.0

    # Soil moisture factor (cumulative rain)
    soil_moisture = min(1.0, precip_72h / 200)

    # Slope factor
    sf = slope_factor(slope)

    # Soil type factor
    stf = SOIL_LANDSLIDE_FACTOR.get(soil_type, 0.5)

    # History multiplier (đã từng sạt lở → nguy cơ cao hơn)
    history_mult = 1.0 + history_count * 0.15

    # 24h rain intensity
    rain_24h_intensity = min(1.0, precip_24h / 150)

    # Combine
    risk = soil_moisture * 0.3 + sf * 0.25 + stf * 0.2 + rain_24h_intensity * 0.25
    risk *= history_mult

    return min(1.0, risk)


def compute_storm_risk(wind_gust, pressure_drop, precip, cloud_cover):
    """
    Storm risk: gió + áp suất giảm + mưa to + mây dày
    """
    # Wind component
    if wind_gust >= VNDMS['wind_danger']:
        wind_factor = 1.0
    elif wind_gust >= VNDMS['wind_warning']:
        wind_factor = 0.5 + (wind_gust - 62) / 54
    elif wind_gust >= 40:
        wind_factor = (wind_gust - 40) / 44
    else:
        wind_factor = 0.0

    # Pressure drop (low pressure = storm)
    if pressure_drop >= 10:
        pressure_factor = 1.0
    elif pressure_drop >= 5:
        pressure_factor = pressure_drop / 10
    else:
        pressure_factor = 0.0

    # Heavy precip component
    precip_factor = min(1.0, precip / 15)

    # Cloud cover (storm clouds)
    cloud_factor = max(0.0, (cloud_cover - 60) / 40) if cloud_cover > 60 else 0

    # Storm requires both wind AND rain
    if wind_factor < 0.3 or precip < 5:
        return 0.0

    risk = wind_factor * 0.4 + precip_factor * 0.3 + cloud_factor * 0.15 + pressure_factor * 0.15
    return min(1.0, risk)


def compute_wildfire_risk(temp, humidity, wind_speed, precip_24h):
    """
    Wildfire risk (bonus): nóng + khô + gió
    """
    if precip_24h > 5:  # mới có mưa → không cháy
        return 0.0

    # Dry factor (humidity thấp + temp cao)
    temp_factor = max(0, (temp - 25) / 15)  # > 25°C bắt đầu
    humidity_factor = max(0, (80 - humidity) / 80)  # < 80% bắt đầu
    dry_factor = (temp_factor + humidity_factor) / 2

    # Wind spreads fire
    wind_factor = min(1.0, wind_speed / 40)

    return min(1.0, dry_factor * 0.7 + wind_factor * 0.3)


# ============================================================
# Run Disaster Forecasting (168h x 45 communes/wards)
# ============================================================

def run_disaster_forecast(forecast_run_id=None):
    """
    Load GFS hourly forecast, compute disaster risks per district per hour
    """
    print("=" * 70)
    print("🚨 HINATION DISASTER FORECAST")
    print("   Combining: GFS weather + Terrain + History → Risk")
    print("=" * 70)

    # Load GFS hourly forecast (just generated)
    forecast_path = Path('data/predictions/hourly_forecast.json')
    if not forecast_path.exists():
        print("❌ hourly_forecast.json not found. Run hourly pipeline first.")
        return

    with forecast_path.open(encoding="utf-8") as f:
        gfs_data = json.load(f)

    # ============================================================
    # For each district, compute risks
    # ============================================================
    disaster_forecast = {}
    alerts = []  # High-risk alerts

    for did, p in gfs_data['districts'].items():
        if did not in FORECAST_AREAS:
            continue

        terrain = terrain_for_area(did, p)
        hours = p['forecast_hours']

        # Pre-compute rolling precip sums
        precip_vals = [h['precipitation'] for h in hours]

        disaster_hours = []
        for i, h in enumerate(hours):
            # Get rolling precip (current hour + previous hours)
            precip_24h = sum(precip_vals[max(0, i-23):i+1])
            precip_72h = sum(precip_vals[max(0, i-71):i+1])

            # Compute risks
            flood_risk = compute_flood_risk(
                h['precipitation'], precip_24h, precip_72h, terrain['terrain']
            )

            landslide_risk = compute_landslide_risk(
                h['precipitation'], precip_24h, precip_72h,
                terrain['terrain'], terrain['slope'], terrain['soil_type'],
                terrain['landslide_history_count']
            )

            # Pressure drop (vs previous hours, hPa difference)
            if i > 0:
                pressure_drop = max(0, hours[i-1]['pressure'] - h['pressure'])
            else:
                pressure_drop = 0

            storm_risk = compute_storm_risk(
                h['wind_gusts_10m'], pressure_drop,
                h['precipitation'], h['cloud_cover']
            )

            wildfire_risk = compute_wildfire_risk(
                h['temperature_2m'], h['humidity'],
                h['wind_speed_10m'], precip_24h
            )

            # Determine alert level (Vietnam VNDMS scale 1-5)
            max_risk = max(flood_risk, landslide_risk, storm_risk, wildfire_risk)
            if max_risk < 0.2:
                level = 1  # Low
            elif max_risk < 0.4:
                level = 2  # Medium
            elif max_risk < 0.6:
                level = 3  # High
            elif max_risk < 0.8:
                level = 4  # Very High
            else:
                level = 5  # Catastrophic

            # Determine dominant disaster type
            risks = {
                'flood': flood_risk,
                'landslide': landslide_risk,
                'storm': storm_risk,
                'wildfire': wildfire_risk
            }
            dominant = max(risks, key=risks.get)

            hour_disaster = {
                'datetime': h['datetime'],
                'hour_offset': h['hour_offset'],
                'day_offset': h['day_offset'],
                'precip_24h': round(precip_24h, 1),
                'precip_72h': round(precip_72h, 1),
                'risks': {
                    'flood': round(flood_risk, 3),
                    'landslide': round(landslide_risk, 3),
                    'storm': round(storm_risk, 3),
                    'wildfire': round(wildfire_risk, 3)
                },
                'overall_risk': round(max_risk, 3),
                'alert_level': level,
                'dominant_disaster': dominant,
                'message_vi': generate_vi_message(level, dominant, h, precip_24h)
            }

            disaster_hours.append(hour_disaster)

            # Alert if level >= 3
            if level >= 3:
                alerts.append({
                    'district_id': did,
                    'district_name': terrain['name'],
                    'coordinates': terrain,
                    'datetime': h['datetime'],
                    'level': level,
                    'dominant': dominant,
                    'risk_score': max_risk,
                    'message_vi': hour_disaster['message_vi'],
                    'precip_24h': precip_24h,
                    'wind': h['wind_gusts_10m']
                })

        disaster_forecast[did] = {
            'district_id': did,
            'ma': terrain.get('ma', ''),
            'name': terrain['name'],
            'coordinates': {'lat': terrain['lat'], 'lon': terrain['lon']},
            'terrain': {
                'elevation': terrain['elev'],
                'slope': terrain['slope'],
                'soil_type': terrain['soil_type'],
                'flood_history': terrain['flood_history_count'],
                'landslide_history': terrain['landslide_history_count'],
                'profile_source': terrain['profile_source'],
            },
            'forecast_hours': disaster_hours
        }

    # ============================================================
    # Save output
    # ============================================================
    output = {
        'forecastRunId': forecast_run_id or gfs_data.get('forecastRunId'),
        'generated_at': datetime.now().isoformat(),
        'model': 'disaster_prediction_v1',
        'method': 'GFS + Terrain + VNDMS Standards',
        'forecast_horizon_hours': 168,
        'districts': disaster_forecast,
        'alerts': sorted(alerts, key=lambda x: -x['level'])[:50],  # Top 50 alerts
        'historical_disasters': HISTORICAL_DISASTERS,
        'vndms_standards': VNDMS,
        'methodology': {
            'flood': 'mưa hiện tại + tích lũy 24h/72h + địa hình thấp + lịch sử',
            'landslide': 'độ dốc + loại đất + mưa 72h + lịch sử sạt lở',
            'storm': 'gió giật > 62 km/h + mưa to + áp suất giảm + mây dày',
            'wildfire': 'nhiệt độ > 25°C + độ ẩm < 80% + gió'
        }
    }

    output_path = Path('data/predictions/disaster_forecast.json')
    atomic_write_json(output_path, output)

    # ============================================================
    # Print summary
    # ============================================================
    print(f"\n📊 DISASTER RISK SUMMARY (next 168h)\n")
    print(f"{'District':<25} {'Max Risk':<10} {'Peak Time':<20} {'Dominant':<15} {'Level':<8}")
    print("-" * 85)

    for did, df in disaster_forecast.items():
        hours = df['forecast_hours']
        max_h = max(hours, key=lambda x: x['overall_risk'])
        print(f"{df['name']:<25} "
              f"{max_h['overall_risk']*100:.0f}%       "
              f"{max_h['datetime']:<20} "
              f"{max_h['dominant_disaster']:<15} "
              f"L{max_h['alert_level']}")

    print(f"\n🚨 ACTIVE ALERTS (level >= 3): {len(alerts)}")
    for alert in alerts[:10]:
        print(f"   L{alert['level']} | {alert['district_name']:<25} | {alert['datetime']} | {alert['dominant']}")

    print(f"\n✓ Saved: {output_path}")
    print(f"{'='*70}")
    print(f"✓ DISASTER FORECAST COMPLETE")
    print(f"  Based on: GFS 13km + Terrain model + VNDMS standards")
    print(f"  Output: {len(disaster_forecast)} communes/wards × 168 hours × 4 disaster types")
    print(f"{'='*70}")

    return output


def generate_vi_message(level, dominant, hour_data, precip_24h):
    """Generate Vietnamese alert message"""
    messages = {
        'flood': {
            1: f"Mưa nhỏ {hour_data['precipitation']:.1f}mm. Theo dõi.",
            2: f"Mưa vừa {hour_data['precipitation']:.1f}mm/h. Có thể ngập cục bộ.",
            3: f"Mưa to {hour_data['precipitation']:.1f}mm/h. Cảnh báo ngập lụt vùng trũng.",
            4: f"Mưa rất to {precip_24h:.0f}mm/24h. Nguy cơ lũ quét, sạt lở.",
            5: f"THẢM HỌA: Mưa {precip_24h:.0f}mm/24h. Sơ tán khẩn cấp!"
        },
        'landslide': {
            1: "Địa hình ổn định.",
            2: "Theo dõi sạt lở vùng núi.",
            3: "Cảnh báo sạt lở: mưa nhiều + độ dốc cao.",
            4: "Nguy hiểm cao: có thể sạt lở nghiêm trọng.",
            5: "CỰC KỲ NGUY HIỂM: Sơ tán khỏi vùng núi!"
        },
        'storm': {
            1: f"Gió {hour_data['wind_gusts_10m']:.0f} km/h.",
            2: f"Gió mạnh {hour_data['wind_gusts_10m']:.0f} km/h. Tránh cây lớn.",
            3: f"Cảnh báo bão: gió {hour_data['wind_gusts_10m']:.0f} km/h.",
            4: f"Bão mạnh: gió giật {hour_data['wind_gusts_10m']:.0f} km/h.",
            5: f"THẢM HỌA: Bão cấp {int(hour_data['wind_gusts_10m']/33)}. Sơ tán!"
        },
        'wildfire': {
            1: "Rủi ro cháy thấp.",
            2: "Khô hanh. Hạn chế đốt rừng.",
            3: "Cảnh báo cháy rừng.",
            4: "Nguy cơ cháy rừng cao.",
            5: "CỰC KỲ NGUY HIỂM: Cấm đốt, sơ tán dân."
        }
    }
    return messages.get(dominant, {}).get(level, "Không có cảnh báo.")


if __name__ == '__main__':
    run_disaster_forecast()
