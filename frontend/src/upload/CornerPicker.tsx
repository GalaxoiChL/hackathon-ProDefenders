// Marcarea celor 4 colțuri ale panoului pe primul cadru (ca pipeline/pick_corners.py, dar în browser).
// Click de 4 ori în ordinea stânga-sus, dreapta-sus, dreapta-jos, stânga-jos; apoi colțurile se pot trage.
import { useRef, useState, type PointerEvent } from "react";
import type { Point } from "./homography";

const LABELS = ["Top left", "Top right", "Bottom right", "Bottom left"];

export function CornerPicker({
  frame,
  aspect,
  corners,
  onChange,
}: {
  /** imaginea primului cadru (data URL) */
  frame: string;
  /** lățime / înălțime a video-ului */
  aspect: number;
  /** colțurile, relative la cadru (0..1) */
  corners: Point[];
  onChange: (c: Point[]) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState<number | null>(null);

  const toPoint = (e: PointerEvent): Point => {
    const r = box.current!.getBoundingClientRect();
    return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))];
  };

  const onDown = (e: PointerEvent) => {
    if (corners.length < 4) onChange([...corners, toPoint(e)]);
  };
  const onMove = (e: PointerEvent) => {
    if (dragging === null) return;
    const next = [...corners];
    next[dragging] = toPoint(e);
    onChange(next);
  };

  return (
    <div>
      <div
        ref={box}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={() => setDragging(null)}
        onPointerLeave={() => setDragging(null)}
        className={`relative w-full touch-none select-none overflow-hidden bg-screen ${corners.length < 4 ? "cursor-crosshair" : ""}`}
        style={{ aspectRatio: String(aspect) }}
      >
        <img src={frame} alt="First frame of your video" className="pointer-events-none absolute inset-0 h-full w-full" draggable={false} />
        <svg viewBox="0 0 1 1" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 h-full w-full">
          {corners.length > 1 && (
            <polygon
              points={corners.map((p) => p.join(",")).join(" ")}
              fill={corners.length === 4 ? "rgba(34,227,161,0.18)" : "none"}
              stroke="#22e3a1"
              strokeWidth={2}
              vectorEffect="non-scaling-stroke"
            />
          )}
        </svg>
        {corners.map(([x, y], i) => (
          <button
            key={i}
            type="button"
            aria-label={`${LABELS[i]} corner`}
            onPointerDown={(e) => {
              e.stopPropagation();
              (e.currentTarget.parentElement as HTMLElement).setPointerCapture(e.pointerId);
              setDragging(i);
            }}
            className="absolute size-4 -translate-x-1/2 -translate-y-1/2 cursor-grab rounded-full border-2 border-paper bg-[#22e3a1] shadow active:cursor-grabbing"
            style={{ left: `${x * 100}%`, top: `${y * 100}%` }}
          />
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm">
        <p className="text-ink-2">
          {corners.length < 4 ? (
            <>
              Click the <b>{LABELS[corners.length].toLowerCase()}</b> corner of the billboard ({corners.length + 1} of 4).
            </>
          ) : (
            "All four corners are set. Drag a corner to adjust it."
          )}
        </p>
        {corners.length > 0 && (
          <button type="button" onClick={() => onChange([])} className="text-sm underline decoration-rule-strong underline-offset-4 hover:decoration-ink">
            Start over
          </button>
        )}
      </div>
    </div>
  );
}
