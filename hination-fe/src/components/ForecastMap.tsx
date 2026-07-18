"use client";

import type { Feature, FeatureCollection, Geometry, MultiPolygon, Polygon } from "geojson";
import L, { type LatLngTuple, type Layer, type PathOptions } from "leaflet";
import { CircleMarker, GeoJSON, MapContainer, TileLayer, Tooltip, useMap } from "react-leaflet";
import { useCallback, useEffect, useMemo, useState } from "react";

import { forecastIdFor } from "@/components/forecast-area-id";
import TimelineDock from "@/components/TimelineDock";
import { DISASTER_LABELS, LEVEL_COLORS } from "@/components/map-theme";
import type { DangerLevel, ForecastResponse } from "@/types/forecast";

type CommuneProperties = {
  kind: "commune" | "outside-mask" | "province-boundary";
  name: string;
  osmRelationId?: number;
  forecastId?: string | null;
};

const PROVINCE_BOUNDS: [LatLngTuple, LatLngTuple] = [[20.72, 102.08], [22.54, 103.62]];

function MapBoundsController() {
  const map = useMap();
  useEffect(() => {
    const bounds = L.latLngBounds(PROVINCE_BOUNDS);
    const padding = L.point(24, 24);
    const resize = () => {
      map.invalidateSize();
      const minimum = Math.max(7, map.getBoundsZoom(bounds, false, padding));
      map.setMinZoom(minimum);
      if (map.getZoom() < minimum || !bounds.contains(map.getCenter())) {
        map.fitBounds(bounds, { animate: false, padding: [24, 24] });
      }
    };
    map.setMaxBounds(bounds.pad(0.02));
    map.fitBounds(bounds, { animate: false, padding: [24, 24] });
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [map]);
  return null;
}

function formatPeakTime(value: string) {
  return new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

export default function ForecastMap({ forecast, tileUrl }: { forecast: ForecastResponse; tileUrl: string }) {
  const [selectedDay, setSelectedDay] = useState(0);
  const [geography, setGeography] = useState<FeatureCollection<Geometry, CommuneProperties> | null>(null);
  const day = forecast.days[selectedDay];
  const areaById = useMemo(() => new Map(day.areas.map((area) => [area.id, area])), [day]);

  useEffect(() => {
    let active = true;
    fetch("/dien-bien-communes.geojson")
      .then((response) => {
        if (!response.ok) throw new Error("Không thể tải dữ liệu địa lý");
        return response.json();
      })
      .then((data: FeatureCollection<Geometry, CommuneProperties>) => active && setGeography(data))
      .catch(() => active && setGeography({ type: "FeatureCollection", features: [] }));
    return () => { active = false; };
  }, []);

  const communeFeatures = useMemo(
    () => (geography?.features.filter((feature): feature is Feature<Polygon | MultiPolygon, CommuneProperties> =>
      feature.properties?.kind === "commune" && (feature.geometry.type === "Polygon" || feature.geometry.type === "MultiPolygon")) ?? []),
    [geography],
  );
  const overlayFeatures = useMemo(
    () => geography?.features.filter((feature) => feature.properties?.kind !== "commune") ?? [],
    [geography],
  );

  const onSelectDay = useCallback((index: number) => setSelectedDay(index), []);

  const communeStyle = useCallback((feature?: Feature<Geometry, CommuneProperties>): PathOptions => {
    if (!feature) return {};
    const forecastId = forecastIdFor(feature.properties);
    const level = forecastId ? areaById.get(forecastId)?.danger.level : undefined;
    return {
      color: "rgba(255,255,255,.6)",
      weight: 1,
      fillColor: level ? LEVEL_COLORS[level] : "#64748b",
      fillOpacity: level ? 0.52 : 0.28,
    };
  }, [areaById]);

  function bindCommune(feature: Feature<Geometry, CommuneProperties>, layer: Layer) {
    const forecastId = forecastIdFor(feature.properties);
    const automatic = forecastId ? areaById.get(forecastId)?.danger.level : undefined;
    layer.bindTooltip(`<strong>${feature.properties.name}</strong><br>${automatic ? `Cảnh báo tự động cấp ${automatic}` : "Chưa có dữ liệu dự báo."}`, { sticky: true });
  }

  const overlayStyle = useCallback((feature?: Feature<Geometry, CommuneProperties>): PathOptions => {
    if (feature?.properties.kind === "outside-mask") return { stroke: false, fillColor: "#ffffff", fillOpacity: 0.9, interactive: false };
    return { color: "#dbeafe", weight: 2, fillOpacity: 0, interactive: false };
  }, []);

  return (
    <main className="map-page">
      <MapContainer className="forecast-map" center={[21.65, 103.05]} zoom={8} zoomControl zoomSnap={0.25} preferCanvas>
        <TileLayer url={tileUrl} attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' />
        <MapBoundsController />
        {overlayFeatures.length > 0 && <GeoJSON data={{ type: "FeatureCollection", features: overlayFeatures } as FeatureCollection<Geometry, CommuneProperties>} style={overlayStyle} />}
        {communeFeatures.length > 0 && (
          <GeoJSON
            key={selectedDay}
            data={{ type: "FeatureCollection", features: communeFeatures } as FeatureCollection<Geometry, CommuneProperties>}
            style={communeStyle}
            onEachFeature={bindCommune}
          />
        )}
        {day.areas.map((area) => {
          const color = LEVEL_COLORS[area.danger.level];
          const radius = 8 + area.danger.overallRisk * 18;
          return (
            <CircleMarker key={area.id} center={[area.coordinates.lat, area.coordinates.lng]} radius={radius + 6} pathOptions={{ color, fillColor: color, fillOpacity: 0.12, weight: 1 }} className="danger-pulse">
              <CircleMarker center={[area.coordinates.lat, area.coordinates.lng]} radius={radius} pathOptions={{ color: "white", fillColor: color, fillOpacity: 0.86, weight: 2 }}>
                <Tooltip direction="top" offset={[0, -8]} opacity={1} className="forecast-tooltip">
                  <div className="tooltip-content">
                    <strong>{area.name}</strong>
                    <span>{DISASTER_LABELS[area.danger.dominantDisaster]} · cấp {area.danger.level} · đỉnh {formatPeakTime(area.danger.peakTime)}</span>
                    <span>{area.weather.temperatureMinC}–{area.weather.temperatureMaxC}°C · mưa {area.weather.rainfallTotalMm} mm</span>
                    <span>Gió giật {area.weather.windGustMaxKmh} km/h · ẩm {area.weather.humidityAveragePct}%</span>
                    <em>{area.danger.message}</em>
                  </div>
                </Tooltip>
              </CircleMarker>
            </CircleMarker>
          );
        })}
      </MapContainer>

      <header className="map-heading">
        <div><span className="eyebrow">DB–MWAI</span><h1>Bản đồ cảnh báo Điện Biên</h1></div>
        {forecast.stale && <span className="stale-badge">Dữ liệu đang cũ</span>}
      </header>

      <div className="map-legend" aria-label="Chú giải"><span>Cấp độ</span>{([1, 2, 3, 4, 5] as DangerLevel[]).map((level) => <i key={level} style={{ backgroundColor: LEVEL_COLORS[level] }}>{level}</i>)}</div>
      <TimelineDock days={forecast.days} selected={selectedDay} onSelect={onSelectDay} />
    </main>
  );
}
