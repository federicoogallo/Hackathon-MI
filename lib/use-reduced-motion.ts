"use client";

import { useEffect, useState } from "react";

/** Keep server rendering still and respond to preference changes during a visit. */
export function useReducedMotionPreference(): boolean {
  const [reduced, setReduced] = useState(true);

  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(preference.matches);
    update();
    preference.addEventListener("change", update);
    return () => preference.removeEventListener("change", update);
  }, []);

  return reduced;
}
