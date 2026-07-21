import { useEffect, useState } from "react";

/**
 * Cycles through a set of status messages while `active` is true, so long-running
 * AI calls feel responsive. Advances through the list then holds on the last one.
 */
export function useRotatingMessage(active: boolean, messages: string[], intervalMs = 1800) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (!active) {
      setIndex(0);
      return;
    }
    setIndex(0);
    const id = setInterval(() => {
      setIndex((i) => (i < messages.length - 1 ? i + 1 : i));
    }, intervalMs);
    return () => clearInterval(id);
  }, [active, intervalMs, messages.length]);

  return messages[Math.min(index, messages.length - 1)] || "";
}
