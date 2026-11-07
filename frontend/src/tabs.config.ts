// Lista taburilor: adaugi, ascunzi sau reordonezi un tab modificând doar acest fișier.
import type { ComponentType } from "react";
import WatchTab from "./tabs/WatchTab";
import CompareTab from "./tabs/CompareTab";
import MarketplaceTab from "./tabs/MarketplaceTab";
import CompaniesTab from "./tabs/CompaniesTab";
import SignInTab from "./tabs/SignInTab";

export interface TabDef {
  id: string;
  label: string;
  component: ComponentType;
  enabled: boolean;
  /** "end" = împins în dreapta barei de navigare */
  align?: "end";
}

export const TABS: TabDef[] = [
  { id: "watch", label: "Watch", component: WatchTab, enabled: true },
  { id: "compare", label: "Compare", component: CompareTab, enabled: true },
  { id: "marketplace", label: "Marketplace", component: MarketplaceTab, enabled: true },
  { id: "companies", label: "Companies", component: CompaniesTab, enabled: true },
  { id: "signin", label: "Sign in", component: SignInTab, enabled: true, align: "end" },
];

export const visibleTabs = (): TabDef[] => TABS.filter((t) => t.enabled);
