// Omografia (perspectiva) dintre colțurile panoului și pătratul unitate, ca în pipeline/insert_ad.py, dar în browser.

export type Point = [number, number];

/**
 * Matricea 3×3 (pe rânduri) care duce cele 4 puncte `from` în cele 4 puncte `to`.
 * Ordinea colțurilor: stânga-sus, dreapta-sus, dreapta-jos, stânga-jos (ca în CLAUDE.md).
 */
export function homography(from: Point[], to: Point[]): number[] {
  // 8 ecuații liniare cu necunoscutele h0..h7 (h8 = 1)
  const A: number[][] = [];
  for (let i = 0; i < 4; i++) {
    const [x, y] = from[i];
    const [u, v] = to[i];
    A.push([x, y, 1, 0, 0, 0, -u * x, -u * y, u]);
    A.push([0, 0, 0, x, y, 1, -v * x, -v * y, v]);
  }
  // eliminare Gauss cu pivotare parțială
  for (let c = 0; c < 8; c++) {
    let p = c;
    for (let r = c + 1; r < 8; r++) if (Math.abs(A[r][c]) > Math.abs(A[p][c])) p = r;
    [A[c], A[p]] = [A[p], A[c]];
    if (Math.abs(A[c][c]) < 1e-12) throw new Error("the four corners must not lie on one line");
    for (let r = 0; r < 8; r++) {
      if (r === c) continue;
      const f = A[r][c] / A[c][c];
      for (let k = c; k < 9; k++) A[r][k] -= f * A[c][k];
    }
  }
  const h = A.map((row, i) => row[8] / row[i]);
  return [...h, 1];
}

export const UNIT_SQUARE: Point[] = [
  [0, 0],
  [1, 0],
  [1, 1],
  [0, 1],
];

/** Raportul lățime / înălțime al panoului, din media laturilor opuse. */
export function quadAspect(c: Point[]): number {
  const d = (a: Point, b: Point) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  const w = (d(c[0], c[1]) + d(c[3], c[2])) / 2;
  const h = (d(c[0], c[3]) + d(c[1], c[2])) / 2;
  return h > 0 ? w / h : 1;
}
