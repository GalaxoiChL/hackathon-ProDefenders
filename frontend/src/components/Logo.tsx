// Logo-ul SwapBoard: lumea pe un panou, schițată cu stiloul (liniile tremură ușor, ca trase de mână).
// Culoarea liniilor vine din `color` (currentColor); rutele dintre țări sunt în culoarea de accent.
import { useId } from "react";

export function LogoMark({ size = 36, className = "" }: { size?: number; className?: string }) {
  const pen = `pen-${useId().replace(/:/g, "")}`;
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" className={className}>
      <defs>
        <filter id={pen} x="-10%" y="-10%" width="120%" height="120%">
          <feTurbulence type="fractalNoise" baseFrequency="0.04" numOctaves="2" seed="7" result="n" />
          <feDisplacementMap in="SourceGraphic" in2="n" scale="2.4" />
        </filter>
      </defs>
      <g filter={`url(#${pen})`} fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round">
        <path d="M5 7.5 C20 6, 44 6.8, 59.5 6 L58.8 44.5 C42 45.6, 22 44.4, 5.6 45.2 Z" strokeWidth="2.6" />
        <path d="M17 45.5 L16.2 59.5 M46.5 45 L47.8 59.2" strokeWidth="3" />
        <circle cx="32" cy="25.5" r="14.5" strokeWidth="2" />
        <path d="M32 11 C24 17, 24 34, 32 40 M32 11 C40 17, 40 34, 32 40" strokeWidth="1.2" opacity=".6" />
        <path d="M18.5 20 C26 21.5, 38 21.5, 45.5 20 M18.2 31 C26 29.5, 38 29.6, 45.8 31" strokeWidth="1.2" opacity=".6" />
      </g>
      <g filter={`url(#${pen})`} fill="none" stroke="var(--accent)" strokeWidth="2.2" strokeLinecap="round">
        <path d="M13 34 C17 18, 27 10, 37 15.5 C44 19, 48 16, 52.5 11.5" />
        <path d="M37 15.5 C34 24, 37 32, 45 34.5" strokeDasharray="3 3" />
      </g>
      <g fill="var(--accent)" filter={`url(#${pen})`}>
        <circle cx="13" cy="34" r="2.7" />
        <circle cx="37" cy="15.5" r="2.7" />
        <circle cx="52.5" cy="11.5" r="2.7" />
        <circle cx="45" cy="34.5" r="2.7" />
      </g>
    </svg>
  );
}
