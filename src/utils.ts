export function cloneObject<T>(item: T): T {
  return structuredClone(item);
}