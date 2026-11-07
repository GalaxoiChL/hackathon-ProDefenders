// Culoarea și numele fiecărei țări, folosite la fel în toate taburile.
// Sunt cele 15 piețe demo din backend (backend/config.py); o țară care lipsește de aici primește culoarea implicită.

export interface RegionStyle {
  color: string;
  name: string;
}

const KNOWN: Record<string, RegionStyle> = {
  RO: { color: "#C69B2B", name: "Romania" },
  US: { color: "#2F5D8A", name: "United States" },
  JP: { color: "#4A7C59", name: "Japan" },
  GB: { color: "#5B4A8B", name: "United Kingdom" },
  DE: { color: "#3E3E3E", name: "Germany" },
  FR: { color: "#3D6E9E", name: "France" },
  IT: { color: "#5E8C4A", name: "Italy" },
  ES: { color: "#B5562B", name: "Spain" },
  NL: { color: "#D07A2D", name: "Netherlands" },
  BE: { color: "#A88A1E", name: "Belgium" },
  PL: { color: "#A23B48", name: "Poland" },
  SE: { color: "#2C6A8F", name: "Sweden" },
  AT: { color: "#8C3B3B", name: "Austria" },
  PT: { color: "#356B4E", name: "Portugal" },
  GR: { color: "#4D7FB0", name: "Greece" },
};

/** Țările pe care le știm afișa, în ordinea din selectoare. */
export const KNOWN_REGIONS = Object.keys(KNOWN);

const FALLBACK_COLOR = "#7A766C";

export function regionStyle(code: string, label?: string): RegionStyle {
  return KNOWN[code.toUpperCase()] ?? { color: FALLBACK_COLOR, name: label ?? code };
}

/** Numele afișat: cel din tabelul de mai sus (UI-ul e în engleză), altfel eticheta din manifest. */
export const regionName = (code: string, label?: string) => regionStyle(code, label).name;
