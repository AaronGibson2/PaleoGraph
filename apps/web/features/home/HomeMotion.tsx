"use client";

import { useEffect } from "react";

/** Reveal each editorial section once; content remains available without JS. */
export function HomeMotion() {
  useEffect(() => {
    const root = document.querySelector(".home-experience");
    if (!root || !("IntersectionObserver" in window)) return;
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const animations = new Set<Animation>();
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        observer.unobserve(entry.target);
        if (motion.matches || entry.target.contains(document.activeElement)) continue;
        const animation = entry.target.animate([
          { opacity: .2, transform: "translateY(28px)" },
          { opacity: 1, transform: "translateY(0)" },
        ], { duration: 720, easing: "cubic-bezier(.2,.7,.2,1)" });
        animations.add(animation);
        animation.finished.then(() => animations.delete(animation), () => animations.delete(animation));
      }
    }, { threshold: .12 });
    root.querySelectorAll("[data-home-reveal]").forEach(element => observer.observe(element));
    const stopMotion = () => { for (const animation of animations) animation.cancel(); };
    const onPreference = () => { if (motion.matches) stopMotion(); };
    // Keyboard users should never have to wait for a section entrance.
    root.addEventListener("focusin", stopMotion);
    motion.addEventListener("change", onPreference);
    return () => {
      observer.disconnect();
      stopMotion();
      root.removeEventListener("focusin", stopMotion);
      motion.removeEventListener("change", onPreference);
    };
  }, []);
  return null;
}
