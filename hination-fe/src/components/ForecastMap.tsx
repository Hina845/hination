"use client";

import type { Feature, FeatureCollection, Geometry, MultiPolygon, Polygon } from "geojson";
import L, { type LatLngTuple, type Layer, type PathOptions } from "leaflet";
import { ArrowClockwise, Bell, CaretDown, Lifebuoy, MapTrifold, Megaphone, NavigationArrow, PaperPlaneTilt, Ruler, SignIn, Stack, UsersThree, X } from "@phosphor-icons/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { GeoJSON, MapContainer, TileLayer, useMap } from "react-leaflet";
import { useCallback, useEffect, useMemo, useRef, useState, useTransition } from "react";

import AreaBriefCard from "@/components/AreaBriefCard";
import AreaHoverTip from "@/components/AreaHoverTip";
import BlastDropdown from "@/components/BlastDropdown";
import EmergencyHelp from "@/components/EmergencyHelp";
import { forecastIdFor } from "@/components/forecast-area-id";
import type { ChiefSummary } from "@/components/ForecastMapShell";
import HelpRequestLayer, { type HelpDot } from "@/components/HelpRequestLayer";
import OnboardingTour from "@/components/onboarding/OnboardingTour";
import TourHelpButton from "@/components/onboarding/TourHelpButton";
import TimelineDock from "@/components/TimelineDock";
import { mockHelpRequests } from "@/lib/mock-help-requests";
import { useIsMobile } from "@/lib/use-is-mobile";
import {
  DANGEROUS_LEVEL,
  DANGER_TIERS,
  DISASTER_FILTERS,
  DISASTER_LABELS,
  VI_WEEKDAYS,
  colorForLevel,
  temperatureLevel,
  tierForLevel,
} from "@/components/map-theme";
import type { AreaBriefInput } from "@/types/area-brief";
import type { ForecastArea, ForecastHour, ForecastResponse } from "@/types/forecast";

type CommuneProperties = {
  kind: "commune" | "outside-mask" | "province-boundary";
  name: string;
  osmRelationId?: number;
  forecastId?: string | null;
};

const PROVINCE_BOUNDS: [LatLngTuple, LatLngTuple] = [[20.72, 102.08], [22.54, 103.62]];

const NAV_ITEMS: { label: string; active: boolean; href?: string }[] = [
  { label: "Bản đồ", active: true, href: "/app" },
  { label: "Quản lý", active: false, href: "/manage" },
  { label: "Đài phát thanh", active: false, href: "/radio" },
  { label: "Cứu hộ", active: false, href: "/rescue" },
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

// The timeline snaps in 4-hour slots (6 per day → 42 across the week). A slot's danger is
// the worst hour inside its window; the draggable handle steps between these slots.
const SLOTS_PER_DAY = 6;
const HOURS_PER_SLOT = 4;

function hourDangerLevel(hour: ForecastHour): number {
  return hour.overallLevel ?? hour.level;
}
// The worst (highest level, then highest risk) hour inside a day's 6-hour slot — the hour a
// danger call for that window keys on. Falls back to the day's first hour if data is thin.
function worstHourInSlot(area: ForecastArea, slot: number): ForecastHour {
  const start = slot * HOURS_PER_SLOT;
  let worst = area.hours[start] ?? area.hours[0];
  for (let i = start + 1; i < start + HOURS_PER_SLOT; i += 1) {
    const hour = area.hours[i];
    if (!hour) continue;
    if (hourDangerLevel(hour) > hourDangerLevel(worst) || (hourDangerLevel(hour) === hourDangerLevel(worst) && hour.overallRisk > worst.overallRisk)) {
      worst = hour;
    }
  }
  return worst;
}
// The day's most dangerous slot (max risk across areas) — where the scrubber lands when the
// chief jumps to a day.
function worstSlotOfDay(dayAreas: ForecastArea[]): number {
  let bestSlot = 0;
  let bestRisk = -1;
  for (let slot = 0; slot < SLOTS_PER_DAY; slot += 1) {
    let risk = 0;
    for (const area of dayAreas) risk = Math.max(risk, worstHourInSlot(area, slot).overallRisk);
    if (risk > bestRisk) {
      bestRisk = risk;
      bestSlot = slot;
    }
  }
  return bestSlot;
}

export default function ForecastMap({ forecast, tileUrl, chief }: { forecast: ForecastResponse; tileUrl: string; chief: ChiefSummary | null }) {
  const router = useRouter();
  const canSend = chief !== null;
  const citizensByArea = chief?.citizensByArea ?? {};
  const [isRefreshing, startRefresh] = useTransition();
  // Re-run the server component to re-fetch the forecast (cache: "no-store") and the
  // warmed AI briefs — a full "refresh all" of everything the map renders.
  const refreshAll = useCallback(() => startRefresh(() => router.refresh()), [router]);
  // The data shown is as fresh as the later of the two generation stamps.
  const lastUpdatedMs = Math.max(Date.parse(forecast.weatherGeneratedAt), Date.parse(forecast.riskGeneratedAt));

  const [selectedDay, setSelectedDay] = useState(0);
  // 0..3 slot within the selected day. Starts on day 0's most dangerous slot.
  const [selectedSlot, setSelectedSlot] = useState(() => worstSlotOfDay(forecast.days[0]?.areas ?? []));
  const [geography, setGeography] = useState<FeatureCollection<Geometry, CommuneProperties> | null>(null);
  const [disasterKey, setDisasterKey] = useState(DISASTER_FILTERS[0].key);
  const [navOpen, setNavOpen] = useState(false);
  const [disasterOpen, setDisasterOpen] = useState(true);
  const [dangerOpen, setDangerOpen] = useState(true);
  // Toggles the citizen SOS / emergency-help dots on the map (legend "Cứu hộ" button).
  const [helpVisible, setHelpVisible] = useState(true);
  const [notifOpen, setNotifOpen] = useState(false);
  const [activeAreaId, setActiveAreaId] = useState<string | null>(null);
  const [hoverAreaId, setHoverAreaId] = useState<string | null>(null);
  const [hoverAnchor, setHoverAnchor] = useState<{ x: number; y: number; radius: number } | null>(null);
  const hoverCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const notifRef = useRef<HTMLDivElement>(null);
  const bellRef = useRef<HTMLButtonElement>(null);

  // Two experiences share this component: the chief's "map" and the citizen "help" SOS
  // screen. Phones default to the SOS screen, desktop to the map; the bottom-right FAB
  // toggles either way. `userToggledView` freezes that choice once the user picks manually
  // so a later viewport change (rotate / resize) doesn't yank them back.
  const isMobile = useIsMobile();
  const [view, setView] = useState<"map" | "help">("map");
  const userToggledView = useRef(false);
  useEffect(() => {
    if (!userToggledView.current) setView(isMobile ? "help" : "map");
  }, [isMobile]);
  const toggleView = useCallback(() => {
    userToggledView.current = true;
    setView((current) => (current === "map" ? "help" : "map"));
  }, []);

  // Live citizen SOS requests, shown as pulsing dots — but only at "now" (see nowIndex).
  const [helpRequests, setHelpRequests] = useState<HelpDot[]>([]);

  // "Send SMS to dangerous areas" blast lives in its own component (BlastDropdown) so its
  // form/action state resets on each open — we bump `blastKey` to remount it. See below.
  const [blastOpen, setBlastOpen] = useState(false);
  const [blastKey, setBlastKey] = useState(0);
  const blastBtnRef = useRef<HTMLButtonElement>(null);
  const openBlast = useCallback(() => {
    setBlastKey((key) => key + 1);
    setBlastOpen((open) => !open);
  }, []);

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

  // The representative hour for an area at the currently selected slot (the worst hour in the
  // 6-hour window). Everything the map shows about the selected window — coloring, cards,
  // notifications — reads through this, so nudging the timeline updates the whole map.
  const hourFor = useCallback(
    (area: ForecastArea) => worstHourInSlot(area, selectedSlot),
    [selectedSlot],
  );
  // Combined danger level at the selected slot, mirroring displayLevel() but slot-accurate.
  const hourLevel = useCallback(
    (area: ForecastArea) => {
      const hour = hourFor(area);
      return hour?.overallLevel ?? hour?.level ?? displayLevel(area);
    },
    [hourFor],
  );

  // The level an area contributes for the *selected* forecast at the selected hour: its
  // combined danger level for disaster filters, or its temperature alert level (a daily
  // concept — weather stays a daily summary) when the temperature filter is on.
  const levelForArea = useCallback(
    (area: ForecastArea) =>
      disasterFilter.kind === "temperature" ? temperatureLevel(area.weather) : hourLevel(area),
    [disasterFilter, hourLevel],
  );
  // Day-peak level for an area, independent of the scrubbed hour — drives the day tabs so
  // each tab keeps showing that day's worst case while the scrubber details a single hour.
  const dayLevelForArea = useCallback(
    (area: ForecastArea) =>
      disasterFilter.kind === "temperature" ? temperatureLevel(area.weather) : displayLevel(area),
    [disasterFilter],
  );
  // Headline forecast line for an area, following the selected forecast: temperature band,
  // or the dominant disaster with its level and peak hour. Shared by the merged hover card.
  const forecastLineFor = useCallback(
    (area: ForecastArea) => {
      if (disasterFilter.kind === "temperature") return `Nhiệt độ · cấp ${levelForArea(area)}`;
      const hour = hourFor(area);
      return `${DISASTER_LABELS[hour.dominantDisaster]} · cấp ${hourLevel(area)} · lúc ${formatHour(hour.time)}`;
    },
    [disasterFilter, levelForArea, hourFor, hourLevel],
  );
  // Areas emphasized on the map: matching the selected hour's dominant disaster, or
  // (temperature) any area that has crossed into an alert band (level ≥ 2).
  const emphasizes = useCallback(
    (area: ForecastArea) =>
      disasterFilter.kind === "temperature"
        ? temperatureLevel(area.weather) >= 2
        : disasterFilter.matches.includes(hourFor(area).dominantDisaster),
    [disasterFilter, hourFor],
  );

  // Per-day max level for the selected forecast, so the timeline day labels track the filter.
  // Hour-independent (day peak) — the labels show each day's worst case; the slider details it.
  const dayLevels = useMemo(
    () => forecast.days.map((forecastDay) => forecastDay.areas.reduce((max, area) => Math.max(max, dayLevelForArea(area)), 0)),
    [forecast.days, dayLevelForArea],
  );

  // The wall clock, sampled in an effect (never during render, which must stay pure) and
  // ticked each minute so "now" advances on its own.
  const [nowMs, setNowMs] = useState<number | null>(null);
  useEffect(() => {
    const tick = () => setNowMs(Date.now());
    tick();
    const timer = setInterval(tick, 60000);
    return () => clearInterval(timer);
  }, []);

  // Absolute-hour geometry for the continuous timeline. The forecast starts at 00:00 of
  // day 0, so an hour index is a clock hour and the whole horizon (days×24h) maps linearly
  // onto the track. `selectedIndex` is the flat slot 0..(days×slots−1).
  const totalHours = forecast.days.length * 24;
  const selectedIndex = selectedDay * SLOTS_PER_DAY + selectedSlot;

  // "Now" as an hour offset from day-0 00:00, and the slot/day it lands in. The forecast
  // hours carry absolute ISO times, so matching by offset is timezone-agnostic. Null-guarded
  // when now falls outside the 7-day horizon.
  const day0StartMs = Date.parse(forecast.days[0]?.areas[0]?.hours[0]?.time ?? "");
  const nowOffsetHours = nowMs !== null && !Number.isNaN(day0StartMs) ? (nowMs - day0StartMs) / 3_600_000 : null;
  const nowInHorizon = nowOffsetHours !== null && nowOffsetHours >= 0 && nowOffsetHours < totalHours;
  const nowDay = nowInHorizon ? Math.floor(nowOffsetHours / 24) : -1;
  const nowSlot = nowInHorizon ? Math.floor((nowOffsetHours % 24) / HOURS_PER_SLOT) : -1;
  const nowIndex = nowInHorizon ? nowDay * SLOTS_PER_DAY + nowSlot : -1;
  const nowFraction = nowInHorizon ? nowOffsetHours / totalHours : null;

  // On first load (and after a reload) start the scrubber at "now" rather than day 0's worst
  // slot. `nowMs` is null until the clock effect fires post-mount, so we wait for it and seed
  // the selection once — a ref guards against clobbering the chief's later manual scrubbing.
  const didInitNow = useRef(false);
  useEffect(() => {
    if (didInitNow.current || nowMs === null) return;
    didInitNow.current = true;
    if (nowInHorizon) {
      setSelectedDay(nowDay);
      setSelectedSlot(nowSlot);
    }
  }, [nowMs, nowInHorizon, nowDay, nowSlot]);

  // Live SOS dots are only shown when the handle sits on the "now" slot: they are a
  // present-moment signal, not a forecast.
  const isNow = selectedIndex === nowIndex;
  const showHelpDots = isNow && view === "map" && helpVisible;

  // Handle position (0..1 across the week). Snapped stops sit at each slot's END boundary;
  // the slot containing "now" instead sits exactly at the current time, so today reads e.g.
  // 04, 07, 12, 16… rather than 04, 08, 12…
  const selectedFraction = isNow && nowFraction !== null
    ? nowFraction
    : (selectedDay * 24 + (selectedSlot + 1) * HOURS_PER_SLOT) / totalHours;
  // Tooltip: "T2 20 - 08:00" (weekday date - time); the now-slot shows the live clock time.
  const selectedDate = new Date(`${day.date}T00:00:00+07:00`);
  const selectedClock = isNow && nowMs !== null
    ? new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit" }).format(new Date(nowMs))
    : `${String((selectedSlot + 1) * HOURS_PER_SLOT).padStart(2, "0")}:00`;
  const selectedLabel = `${VI_WEEKDAYS[selectedDate.getDay()]} ${selectedDate.getDate()} - ${selectedClock}`;

  // Demo dot field: ~1k synthetic SOS reports fabricated from the live danger levels so the map
  // reads like a province mid-emergency. Only areas at danger level 3+ get dots (calmer areas
  // show none), and the more dangerous an area the more dots. Purely visual and in-memory
  // (nothing stored); regenerated only when the selected hour's levels change.
  const mockDots = useMemo(
    () =>
      mockHelpRequests(
        day.areas
          .filter((area) => hourLevel(area) >= 3)
          .map((area) => ({ id: area.id, lat: area.coordinates.lat, lng: area.coordinates.lng, level: hourLevel(area) })),
      ),
    [day, hourLevel],
  );
  // What the layer actually draws: the fabricated field plus any real citizen requests polled in.
  const helpDots = useMemo(() => [...mockDots, ...helpRequests], [mockDots, helpRequests]);

  // Poll live help requests only while their dots are actually on screen (at "now", map view),
  // refreshing every 30s so new SOS signals appear without a manual reload.
  useEffect(() => {
    if (!showHelpDots) return;
    let active = true;
    const load = () => {
      fetch("/api/help-requests")
        .then((response) => (response.ok ? response.json() : null))
        .then((data: { requests?: HelpDot[] } | null) => {
          if (active && data?.requests) {
            setHelpRequests(data.requests.map((request) => ({ lat: request.lat, lng: request.lng })));
          }
        })
        .catch(() => {});
    };
    load();
    const timer = setInterval(load, 30000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [showHelpDots]);

  // Notification list: every area dangerous *at the selected hour*, worst risk first, so
  // scrubbing the timeline updates the bell to that hour's active alerts.
  const dangerousAreas = useMemo(
    () =>
      day.areas
        .filter((area) => hourLevel(area) >= DANGEROUS_LEVEL)
        .sort((a, b) => hourFor(b).overallRisk - hourFor(a).overallRisk),
    [day, hourLevel, hourFor],
  );

  const activeArea = activeAreaId ? areaById.get(activeAreaId) ?? null : null;

  const hoverArea = hoverAreaId ? areaById.get(hoverAreaId) ?? null : null;
  const briefDate = day.date.slice(0, 10);
  // The full brief is now driven by the clicked (pinned) area, not hover.
  const briefInput = useMemo<AreaBriefInput | null>(
    () =>
      activeArea
        ? {
            areaId: activeArea.id,
            name: activeArea.name,
            adminCode: activeArea.administrativeCode,
            date: briefDate,
            danger: {
              level: activeArea.danger.level,
              dominantDisaster: activeArea.danger.dominantDisaster,
              message: activeArea.danger.message,
              overallRisk: activeArea.danger.overallRisk,
            },
          }
        : null,
    [activeArea, briefDate],
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

  // Day tab → jump to that day, landing on its most dangerous slot.
  const onSelectDay = useCallback(
    (index: number) => {
      setSelectedDay(index);
      setSelectedSlot(worstSlotOfDay(forecast.days[index]?.areas ?? []));
    },
    [forecast.days],
  );
  // Timeline nudge → a global 0..27 index the strip works in; split back into day + slot.
  const onSelectIndex = useCallback((index: number) => {
    setSelectedDay(Math.floor(index / SLOTS_PER_DAY));
    setSelectedSlot(index % SLOTS_PER_DAY);
  }, []);

  // Areas matching the selected disaster type are emphasized (stronger fill + border);
  // the rest stay muted. This is the map-level effect the dots used to carry.
  const communeStyle = useCallback((feature?: Feature<Geometry, CommuneProperties>): PathOptions => {
    if (!feature) return {};
    const forecastId = forecastIdFor(feature.properties);
    const area = forecastId ? areaById.get(forecastId) : undefined;
    if (!area) {
      return { color: "rgba(255,255,255,.7)", weight: 1, fillColor: "#cbd5e1", fillOpacity: 0.16 };
    }
    const emphasized = emphasizes(area);
    return {
      color: "rgba(255,255,255,.7)",
      weight: emphasized ? 1.5 : 1,
      fillColor: colorForLevel(levelForArea(area)),
      fillOpacity: emphasized ? 0.62 : 0.3,
    };
  }, [areaById, emphasizes, levelForArea]);

  function bindCommune(feature: Feature<Geometry, CommuneProperties>, layer: Layer) {
    const forecastId = forecastIdFor(feature.properties);
    const area = forecastId ? areaById.get(forecastId) : undefined;
    // Areas without forecast data get no hover surface at all — the separate low-info
    // Leaflet tooltip is gone, so the merged AI + weather card is the one and only popup.
    if (!area) return;
    // Two surfaces: hover shows a lightweight preview tip (danger level + headline numbers
    // and a "click to expand" nudge — see AreaHoverTip); click opens the full merged AI +
    // weather brief, pinned to the left (see AreaBriefCard). Clicking dismisses the tip so
    // it doesn't linger over the pinned card.
    layer.on({
      mouseover: () => openHover(area, 14 + area.danger.overallRisk * 18),
      mouseout: scheduleHoverClose,
      click: () => {
        cancelHoverClose();
        setHoverAreaId(null);
        setActiveAreaId(area.id);
      },
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

  return (
    <main className="map-page">
      <MapContainer className="forecast-map" center={[21.65, 103.05]} zoom={8} zoomControl={false} zoomSnap={0.25} preferCanvas>
        <TileLayer url={tileUrl} attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' />
        <MapBoundsController />
        <MapRefBridge mapRef={mapRef} />
        {overlayFeatures.length > 0 && <GeoJSON data={{ type: "FeatureCollection", features: overlayFeatures } as FeatureCollection<Geometry, CommuneProperties>} style={overlayStyle} />}
        {communeFeatures.length > 0 && (
          <GeoJSON
            key={`${selectedDay}-${selectedSlot}-${disasterKey}`}
            data={{ type: "FeatureCollection", features: communeFeatures } as FeatureCollection<Geometry, CommuneProperties>}
            style={communeStyle}
            onEachFeature={bindCommune}
          />
        )}
        <HelpRequestLayer requests={helpDots} visible={showHelpDots} />
      </MapContainer>

      {/* Navigation menu */}
      <nav className={`nav-menu${navOpen ? " nav-menu--open" : ""}`} aria-label="Điều hướng" data-tour="map-nav">
        <button type="button" className="nav-brand" aria-expanded={navOpen} onClick={() => setNavOpen((open) => !open)}>
          <NavigationArrow weight="fill" />
          <span>Điện Biên Forecast</span>
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
            {/* Shown only to anonymous viewers — a chief is already signed in. */}
            {!chief && (
              <li>
                <Link href="/login" className="nav-item nav-item--login">
                  <SignIn weight="bold" />
                  Đăng nhập
                </Link>
              </li>
            )}
          </ul>
        )}
      </nav>

      {/* Chief summary — total citizens covered + emergency SMS sent. Logged-in only. */}
      {chief && (
        <section className="map-summary" aria-label="Tổng quan">
          <div className="map-summary__stat">
            <UsersThree weight="fill" />
            <span className="map-summary__value">{chief.totalCitizens.toLocaleString("vi-VN")}</span>
            <span className="map-summary__label">Tổng số người dân</span>
          </div>
          <div className="map-summary__stat">
            <PaperPlaneTilt weight="fill" />
            <span className="map-summary__value">{chief.smsSent.toLocaleString("vi-VN")}</span>
            <span className="map-summary__label">SMS đã gửi</span>
          </div>
        </section>
      )}

      {/* Top-right toolbar */}
      <div className="map-toolbar">
        <div className="data-status">
          <span className="data-status__text">
            <span className="data-status__label">Cập nhật lần cuối</span>
            <span className="data-status__time">
              {Number.isNaN(lastUpdatedMs) ? "—" : formatUpdated(lastUpdatedMs)}
            </span>
          </span>
          <button type="button" className="data-status__refresh" data-tour="map-refresh" onClick={refreshAll} disabled={isRefreshing} title="Tải lại toàn bộ dữ liệu">
            <ArrowClockwise weight="bold" className={isRefreshing ? "spin" : undefined} />
            <span className="data-status__refresh-text">Làm mới tất cả</span>
          </button>
        </div>
        <button
          ref={bellRef}
          type="button"
          className="alert-bell"
          data-tour="map-bell"
          aria-label="Cảnh báo"
          aria-expanded={notifOpen}
          onClick={() => setNotifOpen((open) => !open)}
        >
          <Bell weight="fill" />
          {dangerousAreas.length > 0 && <span className="alert-dot" aria-hidden />}
        </button>
        {canSend && (
          <button
            ref={blastBtnRef}
            type="button"
            className="alert-bell blast-btn"
            data-tour="map-blast"
            aria-label="Gửi SMS tới khu vực nguy hiểm"
            title="Gửi SMS tới khu vực nguy hiểm"
            aria-expanded={blastOpen}
            onClick={openBlast}
          >
            <Megaphone weight="fill" />
          </button>
        )}
        <div className="legends-bar" data-tour="map-legend">
          <button type="button" className="legends-toggle" onClick={toggleAllLegends}>Chú giải</button>
          <button type="button" className={`tool-btn${disasterOpen ? " tool-btn--active" : ""}`} aria-label="Loại thiên tai" aria-pressed={disasterOpen} title="Loại thiên tai" onClick={() => setDisasterOpen((open) => !open)}><Ruler weight="regular" /></button>
          <button type="button" className={`tool-btn${dangerOpen ? " tool-btn--active" : ""}`} aria-label="Mức độ nguy hiểm" aria-pressed={dangerOpen} title="Mức độ nguy hiểm" onClick={() => setDangerOpen((open) => !open)}><Stack weight="regular" /></button>
          <button type="button" className={`tool-btn${helpVisible ? " tool-btn--active" : ""}`} aria-label="Yêu cầu cứu hộ" aria-pressed={helpVisible} title="Yêu cầu cứu hộ" onClick={() => setHelpVisible((open) => !open)}><Lifebuoy weight="regular" /></button>
          <TourHelpButton page="map" className="tool-btn" />
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
                const hour = hourFor(area);
                const level = hourLevel(area);
                return (
                  <li key={area.id}>
                    <button type="button" className="notif-row" onClick={() => openFromNotif(area.id)}>
                      <span className="notif-row__level" style={{ backgroundColor: colorForLevel(level) }} aria-hidden />
                      <span className="notif-row__body">
                        <span className="notif-row__name">{area.name}</span>
                        <span className="notif-row__meta">
                          {DISASTER_LABELS[hour.dominantDisaster]} · Cấp {level} · {tierForLevel(level).label}
                        </span>
                      </span>
                      <span className="notif-row__time">lúc {formatHour(hour.time)}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}

      {/* Blast dropdown — send one SMS to every villager in a band of dangerous areas.
          Keyed so it remounts (fresh form state) each time it opens. */}
      {blastOpen && canSend && (
        <BlastDropdown
          key={blastKey}
          dayAreas={day.areas}
          citizensByArea={citizensByArea}
          triggerRef={blastBtnRef}
          onClose={() => setBlastOpen(false)}
          onSent={() => router.refresh()}
        />
      )}

      {/* Legend stack — disaster-type filter on top, danger-level legend directly below it */}
      <div className="panel-stack">
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
      </div>

      {/* Lightweight hover preview — headline numbers + a "click to expand" nudge */}
      {hoverArea && (
        <AreaHoverTip
          key={`tip-${hoverArea.id}`}
          name={hoverArea.name}
          anchor={hoverAnchor}
          levelColor={colorForLevel(hourLevel(hoverArea))}
          levelLabel={tierForLevel(hourLevel(hoverArea)).label}
          forecastLine={forecastLineFor(hoverArea)}
          weather={hoverArea.weather}
        />
      )}

      {/* Full AI news brief — opens on click, pinned to the left. Replaced when another
          area is clicked, dismissed via its close button. */}
      {activeArea && briefInput && (
        <AreaBriefCard
          key={`${activeArea.id}|${briefDate}`}
          input={briefInput}
          anchor={null}
          levelColor={colorForLevel(hourLevel(activeArea))}
          levelLabel={tierForLevel(hourLevel(activeArea)).label}
          forecastLine={forecastLineFor(activeArea)}
          weather={activeArea.weather}
          coordinates={activeArea.coordinates}
          canSend={canSend}
          citizenCount={citizensByArea[activeArea.id] ?? 0}
          onSent={() => router.refresh()}
          onClose={() => setActiveAreaId(null)}
          onPointerEnter={() => {}}
          onPointerLeave={() => {}}
        />
      )}

      <TimelineDock
        days={forecast.days}
        dayLevels={dayLevels}
        selected={selectedDay}
        onSelect={onSelectDay}
        slotsPerDay={SLOTS_PER_DAY}
        selectedIndex={selectedIndex}
        onSelectIndex={onSelectIndex}
        selectedFraction={selectedFraction}
        selectedLabel={selectedLabel}
        nowIndex={nowIndex}
        nowFraction={nowFraction}
      />

      {/* Citizen SOS screen — replaces the map on phones, reachable via the FAB anywhere. */}
      {view === "help" && (
        <div className="emergency-overlay">
          <EmergencyHelp places={forecast.days[0]?.areas ?? []} />
        </div>
      )}

      {/* Bottom-right toggle between the map and the emergency-help screen. */}
      <button
        type="button"
        className="help-fab"
        data-tour="map-sos"
        onClick={toggleView}
        aria-label={view === "map" ? "Mở màn hình trợ giúp khẩn cấp" : "Quay lại bản đồ"}
      >
        {view === "map" ? (
          <>
            <Lifebuoy weight="fill" />
            <span className="help-fab__label">Trợ giúp khẩn cấp</span>
          </>
        ) : (
          <>
            <MapTrifold weight="fill" />
            <span className="help-fab__label">Bản đồ</span>
          </>
        )}
      </button>

      <OnboardingTour page="map" />
    </main>
  );
}
