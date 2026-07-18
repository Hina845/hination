"use client";

import type { Feature, FeatureCollection, Geometry, MultiPolygon, Polygon } from "geojson";
import L, { type LatLngTuple, type Layer, type PathOptions } from "leaflet";
import { ArrowClockwise, Bell, CaretDown, NavigationArrow, PaperPlaneTilt, Ruler, Sparkle, Stack, X } from "@phosphor-icons/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { GeoJSON, MapContainer, TileLayer, useMap } from "react-leaflet";
import { useCallback, useEffect, useMemo, useRef, useState, useTransition } from "react";

import AreaBriefCard from "@/components/AreaBriefCard";
import { forecastIdFor } from "@/components/forecast-area-id";
import TimelineDock from "@/components/TimelineDock";
import {
  DANGEROUS_LEVEL,
  DANGER_TIERS,
  DISASTER_FILTERS,
  DISASTER_LABELS,
  VI_WEEKDAYS,
  colorForLevel,
  tierForLevel,
} from "@/components/map-theme";
import type { AreaBriefInput } from "@/types/area-brief";
import type { ForecastArea, ForecastResponse } from "@/types/forecast";

type CommuneProperties = {
  kind: "commune" | "outside-mask" | "province-boundary";
  name: string;
  osmRelationId?: number;
  forecastId?: string | null;
};

const PROVINCE_BOUNDS: [LatLngTuple, LatLngTuple] = [[20.72, 102.08], [22.54, 103.62]];

const NAV_ITEMS: { label: string; active: boolean; href?: string }[] = [
  { label: "Bản đồ", active: true, href: "/app" },
  { label: "Bảng điều khiển", active: false },
  { label: "Quản lý", active: false, href: "/manage" },
  { label: "Đài phát thanh", active: false },
];

function MapRefBridge({ mapRef }: { mapRef: { current: L.Map | null } }) {
  const map = useMap();
  useEffect(() => {
    mapRef.current = map;
    return () => {
      mapRef.current = null;
    };
  }, [map, mapRef]);
  return null;
}

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
  const date = new Date(value);
  const time = new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit" }).format(date);
  return `${VI_WEEKDAYS[date.getDay()]} ${date.getDate()} - ${time}`;
}

function formatHour(value: string) {
  return new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

// "Last updated" label for the forecast data: clock time plus a relative age, so a
// glance tells whether the map is showing recent numbers.
function formatUpdated(ms: number) {
  const time = new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit" }).format(new Date(ms));
  const minutes = Math.round((Date.now() - ms) / 60000);
  if (minutes < 1) return `${time} · vừa xong`;
  if (minutes < 60) return `${time} · ${minutes} phút trước`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${time} · ${hours} giờ trước`;
  return `${time} · ${Math.round(hours / 24)} ngày trước`;
}

// Level shown on the map is the server-computed overall level. The FE never derives
// or adjusts it — it only reads what the server injected (see app/app/page.tsx),
// falling back to the raw API level if the merge hasn't populated it.
function displayLevel(area: ForecastArea): number {
  return area.danger.overallLevel ?? area.danger.level;
}

export default function ForecastMap({ forecast, tileUrl }: { forecast: ForecastResponse; tileUrl: string }) {
  const router = useRouter();
  const [isRefreshing, startRefresh] = useTransition();
  // Re-run the server component to re-fetch the forecast (cache: "no-store") and the
  // warmed AI briefs — a full "refresh all" of everything the map renders.
  const refreshAll = useCallback(() => startRefresh(() => router.refresh()), [router]);
  // The data shown is as fresh as the later of the two generation stamps.
  const lastUpdatedMs = Math.max(Date.parse(forecast.weatherGeneratedAt), Date.parse(forecast.riskGeneratedAt));

  const [selectedDay, setSelectedDay] = useState(0);
  const [geography, setGeography] = useState<FeatureCollection<Geometry, CommuneProperties> | null>(null);
  const [disasterKey, setDisasterKey] = useState(DISASTER_FILTERS[0].key);
  const [navOpen, setNavOpen] = useState(false);
  const [disasterOpen, setDisasterOpen] = useState(true);
  const [dangerOpen, setDangerOpen] = useState(true);
  const [notifOpen, setNotifOpen] = useState(false);
  const [activeAreaId, setActiveAreaId] = useState<string | null>(null);
  const [hoverAreaId, setHoverAreaId] = useState<string | null>(null);
  const [hoverAnchor, setHoverAnchor] = useState<{ x: number; y: number; radius: number } | null>(null);
  const hoverCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const notifRef = useRef<HTMLDivElement>(null);
  const bellRef = useRef<HTMLButtonElement>(null);

  const cancelHoverClose = useCallback(() => {
    if (hoverCloseTimer.current) {
      clearTimeout(hoverCloseTimer.current);
      hoverCloseTimer.current = null;
    }
  }, []);
  // Open the brief next to the hovered marker, projecting its geo-center to a
  // container pixel so the card sits right beside the area it describes.
  const openHover = useCallback(
    (area: ForecastArea, radius: number) => {
      cancelHoverClose();
      const point = mapRef.current?.latLngToContainerPoint([area.coordinates.lat, area.coordinates.lng]);
      if (point) setHoverAnchor({ x: point.x, y: point.y, radius });
      setHoverAreaId(area.id);
    },
    [cancelHoverClose],
  );
  // Delay closing so the pointer can travel from the marker to the (interactive) card.
  const scheduleHoverClose = useCallback(() => {
    cancelHoverClose();
    hoverCloseTimer.current = setTimeout(() => setHoverAreaId(null), 400);
  }, [cancelHoverClose]);
  useEffect(() => cancelHoverClose, [cancelHoverClose]);

  const toggleAllLegends = useCallback(() => {
    const next = !(disasterOpen && dangerOpen);
    setDisasterOpen(next);
    setDangerOpen(next);
  }, [dangerOpen, disasterOpen]);

  const day = forecast.days[selectedDay];
  const areaById = useMemo(() => new Map(day.areas.map((area) => [area.id, area])), [day]);

  const disasterFilter = useMemo(
    () => DISASTER_FILTERS.find((option) => option.key === disasterKey) ?? DISASTER_FILTERS[0],
    [disasterKey],
  );
  const matchesDisaster = useCallback(
    (area: ForecastArea) => disasterFilter.matches.includes(area.danger.dominantDisaster),
    [disasterFilter],
  );

  // Highest-risk area of the selected day drives the timeline label and the default alert card.
  const peakArea = useMemo(
    () => day.areas.reduce<ForecastArea | null>((max, area) => (area.danger.overallRisk > (max?.danger.overallRisk ?? -1) ? area : max), null),
    [day],
  );
  const dangerousDay = day.maximumAlertLevel >= DANGEROUS_LEVEL;
  const peakLabel = peakArea ? formatPeakTime(peakArea.danger.peakTime) : null;

  // Notification list: every currently-dangerous area on the selected day, ordered by
  // peak time so the soonest-to-peak alert sits at the top of the bell dropdown.
  const dangerousAreas = useMemo(
    () =>
      day.areas
        .filter((area) => displayLevel(area) >= DANGEROUS_LEVEL)
        .sort((a, b) => new Date(a.danger.peakTime).getTime() - new Date(b.danger.peakTime).getTime()),
    [day],
  );

  const activeArea = activeAreaId ? areaById.get(activeAreaId) ?? null : null;

  const hoverArea = hoverAreaId ? areaById.get(hoverAreaId) ?? null : null;
  const briefDate = day.date.slice(0, 10);
  const briefInput = useMemo<AreaBriefInput | null>(
    () =>
      hoverArea
        ? {
            areaId: hoverArea.id,
            name: hoverArea.name,
            adminCode: hoverArea.administrativeCode,
            date: briefDate,
            danger: {
              level: hoverArea.danger.level,
              dominantDisaster: hoverArea.danger.dominantDisaster,
              message: hoverArea.danger.message,
              overallRisk: hoverArea.danger.overallRisk,
            },
          }
        : null,
    [hoverArea, briefDate],
  );

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

  // Areas matching the selected disaster type are emphasized (stronger fill + border);
  // the rest stay muted. This is the map-level effect the dots used to carry.
  const communeStyle = useCallback((feature?: Feature<Geometry, CommuneProperties>): PathOptions => {
    if (!feature) return {};
    const forecastId = forecastIdFor(feature.properties);
    const area = forecastId ? areaById.get(forecastId) : undefined;
    if (!area) {
      return { color: "rgba(255,255,255,.7)", weight: 1, fillColor: "#cbd5e1", fillOpacity: 0.16 };
    }
    const emphasized = matchesDisaster(area);
    return {
      color: "rgba(255,255,255,.7)",
      weight: emphasized ? 1.5 : 1,
      fillColor: colorForLevel(displayLevel(area)),
      fillOpacity: emphasized ? 0.62 : 0.3,
    };
  }, [areaById, matchesDisaster]);

  function bindCommune(feature: Feature<Geometry, CommuneProperties>, layer: Layer) {
    const forecastId = forecastIdFor(feature.properties);
    const area = forecastId ? areaById.get(forecastId) : undefined;
    if (!area) {
      layer.bindTooltip(`<strong>${feature.properties.name}</strong><br>Chưa có dữ liệu dự báo.`, { sticky: true });
      return;
    }
    // Rich weather tooltip + interactions live on the commune area itself now that the
    // dots are gone: hover opens the AI brief, click opens the alert detail card.
    layer.bindTooltip(
      `<div class="tooltip-content">`
      + `<strong>${area.name}</strong>`
      + `<span>${DISASTER_LABELS[area.danger.dominantDisaster]} · cấp ${displayLevel(area)} · đỉnh ${formatHour(area.danger.peakTime)}</span>`
      + `<span>${area.weather.temperatureMinC}–${area.weather.temperatureMaxC}°C · mưa ${area.weather.rainfallTotalMm} mm</span>`
      + `<span>Gió giật ${area.weather.windGustMaxKmh} km/h · ẩm ${area.weather.humidityAveragePct}%</span>`
      + `<em>${area.danger.message}</em>`
      + `</div>`,
      { sticky: true, direction: "top", className: "forecast-tooltip" },
    );
    layer.on({
      mouseover: () => openHover(area, 14 + area.danger.overallRisk * 18),
      mouseout: scheduleHoverClose,
      click: () => setActiveAreaId(area.id),
    });
  }

  const overlayStyle = useCallback((feature?: Feature<Geometry, CommuneProperties>): PathOptions => {
    if (feature?.properties.kind === "outside-mask") return { stroke: false, fillColor: "#ABABAB", fillOpacity: 0.75, interactive: false };
    return { color: "#004d13", weight: 1.5, fillOpacity: 0, interactive: false };
  }, []);

  // Selecting a notification opens that area's alert detail card and dismisses the dropdown.
  const openFromNotif = useCallback((areaId: string) => {
    setActiveAreaId(areaId);
    setNotifOpen(false);
  }, []);

  // Dismiss the dropdown on an outside click or Escape, but ignore clicks on the bell
  // itself so its toggle keeps working.
  useEffect(() => {
    if (!notifOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (notifRef.current?.contains(target) || bellRef.current?.contains(target)) return;
      setNotifOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setNotifOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [notifOpen]);

  const activeTier = activeArea ? tierForLevel(displayLevel(activeArea)) : null;

  return (
    <main className="map-page">
      <MapContainer className="forecast-map" center={[21.65, 103.05]} zoom={8} zoomControl={false} zoomSnap={0.25} preferCanvas>
        <TileLayer url={tileUrl} attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' />
        <MapBoundsController />
        <MapRefBridge mapRef={mapRef} />
        {overlayFeatures.length > 0 && <GeoJSON data={{ type: "FeatureCollection", features: overlayFeatures } as FeatureCollection<Geometry, CommuneProperties>} style={overlayStyle} />}
        {communeFeatures.length > 0 && (
          <GeoJSON
            key={`${selectedDay}-${disasterKey}`}
            data={{ type: "FeatureCollection", features: communeFeatures } as FeatureCollection<Geometry, CommuneProperties>}
            style={communeStyle}
            onEachFeature={bindCommune}
          />
        )}
      </MapContainer>

      {/* Navigation menu */}
      <nav className={`nav-menu${navOpen ? " nav-menu--open" : ""}`} aria-label="Điều hướng">
        <button type="button" className="nav-brand" aria-expanded={navOpen} onClick={() => setNavOpen((open) => !open)}>
          <NavigationArrow weight="fill" />
          <span>DB–MWAI</span>
          <CaretDown className="nav-caret" weight="bold" />
        </button>
        {navOpen && (
          <ul>
            {NAV_ITEMS.map((item) => (
              <li key={item.label}>
                {item.href ? (
                  <Link
                    href={item.href}
                    className={`nav-item${item.active ? " nav-item--active" : ""}`}
                    aria-current={item.active ? "page" : undefined}
                  >
                    {item.label}
                  </Link>
                ) : (
                  <button type="button" className="nav-item" disabled title="Sắp có">
                    {item.label}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </nav>

      {/* Top-right toolbar */}
      <div className="map-toolbar">
        <div className="data-status">
          <span className="data-status__text">
            <span className="data-status__label">Cập nhật lần cuối</span>
            <span className="data-status__time">
              {Number.isNaN(lastUpdatedMs) ? "—" : formatUpdated(lastUpdatedMs)}
            </span>
          </span>
          <button type="button" className="data-status__refresh" onClick={refreshAll} disabled={isRefreshing} title="Tải lại toàn bộ dữ liệu">
            <ArrowClockwise weight="bold" className={isRefreshing ? "spin" : undefined} />
            <span className="data-status__refresh-text">Làm mới tất cả</span>
          </button>
        </div>
        <button
          ref={bellRef}
          type="button"
          className="alert-bell"
          aria-label="Cảnh báo"
          aria-expanded={notifOpen}
          onClick={() => setNotifOpen((open) => !open)}
        >
          <Bell weight="fill" />
          {dangerousAreas.length > 0 && <span className="alert-dot" aria-hidden />}
        </button>
        <div className="legends-bar">
          <button type="button" className="legends-toggle" onClick={toggleAllLegends}>Chú giải</button>
          <button type="button" className={`tool-btn${disasterOpen ? " tool-btn--active" : ""}`} aria-label="Loại thiên tai" aria-pressed={disasterOpen} title="Loại thiên tai" onClick={() => setDisasterOpen((open) => !open)}><Ruler weight="regular" /></button>
          <button type="button" className={`tool-btn${dangerOpen ? " tool-btn--active" : ""}`} aria-label="Mức độ nguy hiểm" aria-pressed={dangerOpen} title="Mức độ nguy hiểm" onClick={() => setDangerOpen((open) => !open)}><Stack weight="regular" /></button>
        </div>
      </div>

      {/* Bell notification dropdown — currently dangerous areas, soonest peak first */}
      {notifOpen && (
        <div className="notif-dropdown" ref={notifRef} role="dialog" aria-label="Cảnh báo đang hoạt động">
          <header className="notif-dropdown__head">
            <h2>Cảnh báo đang hoạt động</h2>
            {dangerousAreas.length > 0 && <span className="notif-dropdown__count">{dangerousAreas.length}</span>}
            <button type="button" className="notif-dropdown__close" aria-label="Đóng" onClick={() => setNotifOpen(false)}><X /></button>
          </header>
          {dangerousAreas.length === 0 ? (
            <p className="notif-dropdown__empty">Không có khu vực nguy hiểm trong ngày này.</p>
          ) : (
            <ul className="notif-list">
              {dangerousAreas.map((area) => {
                const level = displayLevel(area);
                return (
                  <li key={area.id}>
                    <button type="button" className="notif-row" onClick={() => openFromNotif(area.id)}>
                      <span className="notif-row__level" style={{ backgroundColor: colorForLevel(level) }} aria-hidden />
                      <span className="notif-row__body">
                        <span className="notif-row__name">{area.name}</span>
                        <span className="notif-row__meta">
                          {DISASTER_LABELS[area.danger.dominantDisaster]} · Cấp {level} · {tierForLevel(level).label}
                        </span>
                      </span>
                      <span className="notif-row__time">đỉnh {formatHour(area.danger.peakTime)}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}

      {/* Disaster type filter */}
      {disasterOpen && (
        <section className="panel disaster-panel" aria-label="Loại thiên tai">
          <h2>Loại thiên tai</h2>
          <ul>
            {DISASTER_FILTERS.map((option) => (
              <li key={option.key}>
                <label className="radio-row">
                  <input
                    type="radio"
                    name="disaster-type"
                    checked={disasterKey === option.key}
                    onChange={() => setDisasterKey(option.key)}
                  />
                  <span className="radio-mark" aria-hidden />
                  {option.label}
                </label>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Danger level legend */}
      {dangerOpen && (
        <section className="panel danger-panel" aria-label="Mức độ nguy hiểm">
          <h2>Mức độ nguy hiểm</h2>
          <ul>
            {DANGER_TIERS.map((tier) => (
              <li key={tier.key}>
                <span className="danger-swatch" style={{ backgroundColor: tier.color }} aria-hidden />
                {tier.label}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Alert detail card */}
      {activeArea && activeTier && (
        <article className="alert-card" aria-label={`Cảnh báo ${activeArea.name}`}>
          <header className="alert-card__head">
            <div>
              <h3>{DISASTER_LABELS[activeArea.danger.dominantDisaster]}</h3>
              <p>{activeArea.name}</p>
            </div>
            <span className="alert-card__level" style={{ backgroundColor: activeTier.color }} title={activeTier.label} aria-hidden />
            <button type="button" className="alert-card__close" aria-label="Đóng" onClick={() => setActiveAreaId(null)}><X /></button>
          </header>
          <div className="alert-card__forecast">
            <div className="alert-card__forecast-head"><Sparkle weight="fill" /> Dự báo sớm</div>
            <p>{activeArea.danger.message}</p>
          </div>
          <button type="button" className="alert-card__cta"><PaperPlaneTilt weight="fill" /> Gửi yêu cầu xác nhận</button>
        </article>
      )}

      {/* AI news brief — appears on area hover, stays pinned while pointer is on the card */}
      {hoverArea && briefInput && (
        <AreaBriefCard
          key={`${hoverArea.id}|${briefDate}`}
          input={briefInput}
          anchor={hoverAnchor}
          levelColor={colorForLevel(displayLevel(hoverArea))}
          levelLabel={tierForLevel(displayLevel(hoverArea)).label}
          onClose={() => {
            cancelHoverClose();
            setHoverAreaId(null);
          }}
          onPointerEnter={cancelHoverClose}
          onPointerLeave={scheduleHoverClose}
        />
      )}

      <TimelineDock days={forecast.days} selected={selectedDay} onSelect={onSelectDay} peakLabel={peakLabel} dangerous={dangerousDay} />
    </main>
  );
}
