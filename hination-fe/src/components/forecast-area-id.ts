export type ForecastAreaProperties = {
  forecastId?: string | null;
  osmRelationId?: number;
};

export function forecastIdFor(properties: ForecastAreaProperties) {
  return properties.forecastId ?? (properties.osmRelationId ? `commune_${properties.osmRelationId}` : undefined);
}
