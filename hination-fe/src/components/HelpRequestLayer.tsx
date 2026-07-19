"use client";

import L from "leaflet";
import { useEffect } from "react";
import { useMap } from "react-leaflet";

// `group` ties a dot to its area (commune). Clustering never merges across groups, so the map
// always shows at least one dot per area — many communes can never collapse into a single blob.
export type HelpDot = { lat: number; lng: number; group?: string };

type Cluster = { lat: number; lng: number; count: number };

// A whole-world grid whose cell shrinks by half per zoom level. At low zoom nearby requests
// within the same area share a cell and merge into one big dot; zooming in shrinks the cell so
// each area's dot splits into smaller, more specific ones — the "zoom in slices to smaller"
// behaviour. The grid key is namespaced by `group`, so different areas are always separate dots.
const BASE_CELL_DEG = 360;

function clusterRequests(requests: HelpDot[], zoom: number): Cluster[] {
  const cell = BASE_CELL_DEG / 2 ** zoom;
  const buckets = new Map<string, { latSum: number; lngSum: number; count: number }>();
  for (const request of requests) {
    const gx = Math.floor(request.lng / cell);
    const gy = Math.floor(request.lat / cell);
    const key = `${request.group ?? ""}:${gx}:${gy}`;
    const bucket = buckets.get(key) ?? { latSum: 0, lngSum: 0, count: 0 };
    bucket.latSum += request.lat;
    bucket.lngSum += request.lng;
    bucket.count += 1;
    buckets.set(key, bucket);
  }
  return [...buckets.values()].map((bucket) => ({
    lat: bucket.latSum / bucket.count,
    lng: bucket.lngSum / bucket.count,
    count: bucket.count,
  }));
}

function dotIcon(count: number): L.DivIcon {
  // Diameter grows with how many requests the dot represents. A log scale keeps a lone dot
  // small while letting a hot spot of hundreds/thousands read as a genuinely big marker; the
  // cap stops the province-wide cluster from swallowing the map.
  const size = Math.min(150, 20 + Math.log2(count + 1) * 13) * 0.25;
  const label = count > 1 ? `<span class="help-dot__count">${count}</span>` : "";
  return L.divIcon({
    className: "help-dot-icon",
    html: `<span class="help-dot" style="--dot-size:${size}px"><span class="help-dot__ring"></span><span class="help-dot__core">${label}</span></span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

/**
 * Renders live citizen SOS requests as pulsing red dots, clustered by zoom. Imperative
 * (useMap + a layerGroup) rather than react-leaflet <Marker>s so we own the divIcon markup,
 * the pulse, and the re-cluster-on-zoom loop. Nothing is drawn when `visible` is false.
 */
export default function HelpRequestLayer({ requests, visible }: { requests: HelpDot[]; visible: boolean }) {
  const map = useMap();

  useEffect(() => {
    const group = L.layerGroup().addTo(map);

    const rebuild = () => {
      group.clearLayers();
      if (!visible) return;
      for (const cluster of clusterRequests(requests, map.getZoom())) {
        L.marker([cluster.lat, cluster.lng], {
          icon: dotIcon(cluster.count),
          interactive: false,
          keyboard: false,
        }).addTo(group);
      }
    };

    rebuild();
    map.on("zoomend", rebuild);
    return () => {
      map.off("zoomend", rebuild);
      group.remove();
    };
  }, [map, requests, visible]);

  return null;
}
