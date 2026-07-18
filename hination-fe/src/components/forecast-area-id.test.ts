import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { forecastIdFor, type ForecastAreaProperties } from "@/components/forecast-area-id";

type CommuneFeature = {
  properties: ForecastAreaProperties & { kind: string };
};

describe("forecastIdFor", () => {
  it("maps every current commune polygon to a unique API area ID", () => {
    const geography = JSON.parse(
      readFileSync(join(process.cwd(), "public", "dien-bien-communes.geojson"), "utf-8"),
    ) as { features: CommuneFeature[] };
    const communes = geography.features.filter((feature) => feature.properties.kind === "commune");
    const ids = communes.map((feature) => forecastIdFor(feature.properties));

    expect(communes).toHaveLength(45);
    expect(ids.every(Boolean)).toBe(true);
    expect(new Set(ids).size).toBe(45);
    expect(ids).toContain("dien_bien_phu");
    expect(ids).toContain("commune_19537811");
  });
});
