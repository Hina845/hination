# HINATION Domain Context

## Project Overview

HINATION là hệ thống dự báo thiên tai tỉnh Điện Biên, Việt Nam. Hệ thống kết hợp:
- **Weather Forecast**: NOAA GFS 13km qua Open-Meteo
- **Climate Baseline**: ERA5 Reanalysis (2015-nay)
- **Terrain**: SRTM/NASADEM + calibrated profiles
- **Historical Disasters**: IBTrACS + GLC + VDDMA
- **ML Models**: Random Forest + Gradient Boosting

## Domain Terms

### Geographic Entities

- **Commune (Xã/Phường)**: Đơn vị hành chính cơ sở. 45 communes trong tỉnh Điện Biên sau sáp nhập 2025.
- **District (Huyện)**: Đơn vị hành chính cấp trên.
- **Calibrated Commune**: 9 communes có terrain profile nghiên cứu chi tiết (dien_bien_phu, muong_lay, muong_nhe, muong_cha, tua_chua, tuan_giao, muong_ang, dien_bien_dong, nam_po).
- **Uncalibrated Commune**: 36 communes còn lại, terrain được ước tính từ elevation.

### Disaster Types

- **Flood (Ngập lụt)**: Nước tràn bờ sông/suối, ngập vùng trũng.
- **Flash Flood (Lũ quét)**: Lũ đột ngột, tốc độ cao, mang theo bùn đá.
- **Landslide (Sạt lở đất)**: Đất đá trượt trên sườn núi.
- **Storm (Bão/Áp thấp)**: Gió mạnh kèm mưa to.
- **Typhoon (Bão nhiệt đới)**: Bão cấp 1 trở lên.
- **Wildfire (Cháy rứng)**: cháy rừng trong mùa khô.

### Weather Data

- **GFS (Global Forecast System)**: Mô hình dự báo thời tiết NOAA, độ phân giải 13km.
- **ERA5**: Reanalysis, độ chính xác cao hơn GFS, dùng cho baseline.
- **CHIRPS/GPM**: Dữ liệu mưa vệ tinh độ phân giải cao.
- **API (Antecedent Precipitation Index)**: Chỉ số mưa tích lũy có trọng số, phản ánh độ ẩm đất.

### Risk Calculation

- **Risk Score**: Giá trị 0-1, xác suất xảy ra thiên tai.
- **Alert Level**: Cấp cảnh báo 1-5 (thấp → thảm họa).
- **VNDMS Standards**: Quy chuẩn Việt Nam QĐ 18/2021 về ngưỡng cảnh báo.
- **Climate Anomaly**: Độ lệch so với baseline khí hậu.

### ML Terms

- **Training**: Huấn luyện model từ historical data.
- **Backtest**: Kiểm tra model trên các sự kiện đã biết.
- **Feature Vector**: Tập hợp features cho một commune/ngày.
- **Random Forest**: Thuật toán ML cho flood và landslide.
- **Gradient Boosting**: Thuật toán ML cho storm.

## Architecture Modules

### Providers

- `HistoricalWeatherProvider`: Interface cho dữ liệu thời tiết quá khứ.
- `OpenMeteoHistoricalProvider`: Implementation dùng Open-Meteo Archive API.
- `OpenMeteoGfsProvider`: Dữ liệu forecast hiện tại (trong hourly_pipeline).

### Catalog

- `DisasterCatalog`: Tập hợp thiên tai quá khứ.
- `DisasterEvent`: Một sự kiện thiên tai đã xảy ra.
- Nguồn: IBTrACS (bão), GLC (sạt lở), VDDMA (lũ lụt).

### Terrain

- `TerrainProcessor`: Tính terrain features từ DEM.
- `TerrainFeatures`: Slope, aspect, elevation, TWI, soil type.
- Nguồn: SRTM/NASADEM qua GEE hoặc Open-Elevation API.

### Features

- `DailyFeatureVector`: Feature vector cho một commune/ngày.
- `FeatureStore`: Tập hợp tất cả features.
- Bao gồm: weather, accumulated rain, API, climate anomaly, terrain, temporal, historical.

### ML

- `ModelTrainer`: Huấn luyện và validate ML models.
- `TrainedModelSet`: Tập hợp trained models.
- Output: Random Forest (flood, landslide), Gradient Boosting (storm).

### Model (Inference)

- `disaster_model_v2.py`: Inference layer, kết hợp ML + heuristic.
- Fallback: Heuristic rules khi ML models không có.

## Data Sources

| Source | Content | Years | Provider |
|--------|---------|-------|----------|
| NOAA GFS | Weather forecast | 7 days ahead | Open-Meteo |
| ERA5 | Reanalysis | 2015-nay | Open-Meteo Archive |
| IBTrACS | Tropical cyclones | 1851-nay | NOAA |
| GLC | Global landslides | 1988-nay | NASA |
| VDDMA | Vietnam disasters | varies | VDDMA |
| SRTM/NASADEM | Elevation | static | NASA/USGS |
| Open-Elevation | Elevation | static | Open-Elevation API |

## VNDMS Standards (QĐ 18/2021)

| Metric | Warning | Danger | Extreme |
|--------|---------|--------|---------|
| Rain 24h | 50mm | 100mm | 200mm |
| Wind | 62 km/h | 89 km/h | - |

## Alert Levels

| Level | Risk Range | Description |
|-------|------------|-------------|
| 1 | 0.0-0.2 | Thấp - Theo dõi |
| 2 | 0.2-0.4 | Trung bình - Cảnh báo nhẹ |
| 3 | 0.4-0.6 | Cao - Cảnh báo |
| 4 | 0.6-0.8 | Rất cao - Nguy hiểm |
| 5 | 0.8-1.0 | Thảm họa - Sơ tán |
