export function cloneObject<T>(item: T): T {
  // Try structuredClone first; fall back to JSON-clone when the input contains
  // values that aren't structured-cloneable (Vue reactive proxies wrapping
  // class instances, functions, etc.). The fallback drops non-JSON values,
  // which is fine for the plain-data params we clone in stores.
  try {
    return structuredClone(item);
  } catch {
    return JSON.parse(JSON.stringify(item));
  }
}