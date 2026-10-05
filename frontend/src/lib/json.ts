export function sameJson(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== "object" || typeof b !== "object" || a === null || b === null) return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;

  const keysA = Object.keys(a);
  const keysB = Object.keys(b);
  if (keysA.length !== keysB.length) return false;
  return keysA.every(
    (key) => key in b && sameJson((a as Record<string, unknown>)[key], (b as Record<string, unknown>)[key]),
  );
}

export type ParsedArgs = { ok: true; value: Record<string, unknown> } | { ok: false; error: string };

export function parseArgs(text: string): ParsedArgs {
  try {
    const value: unknown = JSON.parse(text);
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      return { ok: false, error: "Arguments must be a JSON object." };
    }
    return { ok: true, value: value as Record<string, unknown> };
  } catch (error) {
    return { ok: false, error: `Invalid JSON: ${(error as Error).message}` };
  }
}
