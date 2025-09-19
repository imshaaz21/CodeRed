import { BOARD_SIZE } from "./rules";

const TEMPLATE = [
  "TW .. .. DL .. .. .. TW .. .. .. DL .. .. TW",
  ".. DW .. .. DL .. TL .. TL .. DL .. .. DW ..",
  ".. .. DW .. .. TL .. .. .. TL .. .. DW .. ..",
  "DL .. .. DW .. .. .. DL .. .. .. DW .. .. DL",
  ".. DL .. .. DW .. .. .. .. .. DW .. .. DL ..",
  ".. .. TL .. .. TL .. .. .. TL .. .. TL .. ..",
  ".. .. .. DL .. .. .. .. .. .. .. DL .. .. ..",
  "TW .. .. DL .. .. .. DW .. .. .. DL .. .. TW",
  ".. .. .. DL .. .. .. .. .. .. .. DL .. .. ..",
  ".. .. TL .. .. TL .. .. .. TL .. .. TL .. ..",
  ".. DL .. .. DW .. .. .. .. .. DW .. .. DL ..",
  "DL .. .. DW .. .. .. DL .. .. .. DW .. .. DL",
  ".. .. DW .. .. TL .. .. .. TL .. .. DW .. ..",
  ".. DW .. .. DL .. TL .. TL .. DL .. .. DW ..",
  "TW .. .. DL .. .. .. TW .. .. .. DL .. .. TW",
];

export type PremiumCode = "TW" | "DW" | "TL" | "DL" | null;

export const PREMIUM_MAP: Record<string, PremiumCode> = {};

for (let row = 0; row < BOARD_SIZE; row += 1) {
  const cols = TEMPLATE[row].split(" ");
  for (let col = 0; col < BOARD_SIZE; col += 1) {
    const token = cols[col];
    PREMIUM_MAP[`${row}:${col}`] = token === ".." ? null : (token as PremiumCode);
  }
}

export function getPremium(row: number, col: number): PremiumCode {
  return PREMIUM_MAP[`${row}:${col}`] ?? null;
}
