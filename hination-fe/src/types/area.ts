// Lightweight per-area option for the villager area select and the SMS scope selectors.
// Pure type — no server imports — so it can cross into client components freely.

export type AreaOption = {
  id: string; // forecast area id (see hination/model/areas.py)
  name: string; // Vietnamese commune/ward name
  level: number; // current display danger level (overall ?? raw, 0–5) for the selected day
  count: number; // villagers the chief has tagged to this area
};
