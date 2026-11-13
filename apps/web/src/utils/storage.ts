import { useEffect, useState } from 'react';

export function useStoredState<T>(key: string, initial: T, migrate?: (value: unknown) => T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const saved = localStorage.getItem(key);
      if (!saved) return initial;
      const parsed: unknown = JSON.parse(saved);
      return migrate ? migrate(parsed) : parsed as T;
    } catch {
      return initial;
    }
  });
  useEffect(() => {
    localStorage.setItem(key, JSON.stringify(value));
  }, [key, value]);
  return [value, setValue] as const;
}
