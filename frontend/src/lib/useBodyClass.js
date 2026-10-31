import { useEffect } from "react";

// Some screens colour the whole page (IT panel, mission control, Backstage, the lock screen,
// the game-style drill). They set a class on <body> while mounted.
export function useBodyClass(className) {
  useEffect(() => {
    if (!className) return undefined;
    const names = className.split(" ");
    document.body.classList.add(...names);
    return () => document.body.classList.remove(...names);
  }, [className]);
}
