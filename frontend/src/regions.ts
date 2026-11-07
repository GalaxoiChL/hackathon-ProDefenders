// Culoarea și numele fiecărei țări, folosite la fel în toate taburile.
// O țară care apare în date dar lipsește de aici primește culoarea implicită.

export interface RegionStyle {
  color: string;
  name: string;
}

const KNOWN: Record<string, RegionStyle> = {
  RO: { color: "#C69B2B", name: "Romania" },
  US: { color: "#2F5D8A", name: "United States" },
  JP: { color: "#4A7C59", name: "Japan" },
};

const FALLBACK_COLOR = "#7A766C";

export function regionStyle(code: string, label?: string): RegionStyle {
  return KNOWN[code] ?? { color: FALLBACK_COLOR, name: label ?? code };
}

/** Numele afișat: cel din tabelul de mai sus (UI-ul e în engleză), altfel eticheta din manifest. */
export const regionName = (code: string, label?: string) => regionStyle(code, label).name;
