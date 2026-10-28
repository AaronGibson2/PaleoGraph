"use client";

import { useEffect, useRef, useState, type RefObject } from "react";

export type OpeningPhase = "preparing" | "arriving" | "playing" | "still";
// A new document always gets an entrance. SPA returns stay calm. Mark this only
// after a visible frame commits, so Strict Mode's setup/cleanup cannot consume it.
let enteredThisDocument = false;
const environmentDuration = 3200;

export function useOpeningMotion(root: RefObject<HTMLElement | null>) {
  const actions = useRef({ replay: () => {}, finish: () => {} });
  const [phase, setPhase] = useState<OpeningPhase>(() => enteredThisDocument ? "still" : "preparing");
  const [paused, setPaused] = useState(false);
  const [uncovered, setUncovered] = useState(() => enteredThisDocument);
  const [enhanced, setEnhanced] = useState(false);
  const [artFailed, setArtFailed] = useState(false);

  useEffect(() => {
    const element = root.current;
    if (!element) return;
    const image = element.querySelector<HTMLImageElement>(".opening-art");
    const reduced = matchMedia("(prefers-reduced-motion: reduce)");
    const fine = matchMedia("(pointer: fine) and (hover: hover) and (min-width: 900px)");
    let disposed = false;
    let current: OpeningPhase = enteredThisDocument ? "still" : "preparing";
    let firstFrame = 0;
    let secondFrame = 0;
    let inputFrame = 0;
    let introTimer: ReturnType<typeof setTimeout> | undefined;
    let endTimer: ReturnType<typeof setTimeout> | undefined;
    let remaining = environmentDuration;
    let resumedAt = 0;
    let artReady = !image;
    let decoding = false;
    let introReady = false;
    let onScreen = true;
    let point: { x: number; y: number } | null = null;
    const visible = () => document.visibilityState === "visible";
    const change = (next: OpeningPhase) => { current = next; setPhase(next); };
    const cancelFrames = () => { cancelAnimationFrame(firstFrame); cancelAnimationFrame(secondFrame); firstFrame = secondFrame = 0; };
    const clearTimers = () => { clearTimeout(introTimer); clearTimeout(endTimer); };
    const finish = () => {
      cancelFrames(); clearTimers(); enteredThisDocument = true; setUncovered(true); change("still");
    };
    const armEnd = () => {
      clearTimeout(endTimer);
      resumedAt = performance.now();
      endTimer = setTimeout(finish, remaining);
    };
    const uncover = () => {
      if (disposed || !visible() || reduced.matches || current !== "arriving" || !introReady || !artReady || secondFrame) return;
      firstFrame = requestAnimationFrame(() => {
        secondFrame = requestAnimationFrame(() => {
          firstFrame = secondFrame = 0;
          if (disposed || !visible() || current !== "arriving" || reduced.matches) return;
          enteredThisDocument = true;
          change("playing"); remaining = environmentDuration; armEnd();
        });
      });
    };
    const arrive = () => {
      if (disposed || !visible() || reduced.matches || current !== "preparing") return;
      firstFrame = requestAnimationFrame(() => {
        secondFrame = requestAnimationFrame(() => {
          firstFrame = secondFrame = 0;
          if (disposed || !visible() || reduced.matches || current !== "preparing") return;
          change("arriving");
          introTimer = setTimeout(() => { introReady = true; uncover(); }, 180);
        });
      });
    };
    const replay = () => {
      cancelFrames(); clearTimers(); introReady = false; setUncovered(false);
      if (reduced.matches) { finish(); return; }
      change("preparing"); arrive();
    };
    const loaded = async () => {
      if (!image || decoding) return;
      decoding = true;
      try { await image.decode(); } catch { /* A decoded fallback can replace a failed image. */ }
      if (disposed) return;
      setArtFailed(image.naturalWidth === 0);
      artReady = true; decoding = false; uncover();
    };
    const failed = () => { if (!disposed) { setArtFailed(true); artReady = true; uncover(); } };
    image?.addEventListener("load", loaded);
    image?.addEventListener("error", failed);
    // Account for loads and failures that precede hydration.
    if (image?.complete) { if (image.naturalWidth) void loaded(); else failed(); }

    const resetInput = () => {
      point = null; cancelAnimationFrame(inputFrame); inputFrame = 0;
      element.style.setProperty("--opening-x", "0px");
      element.style.setProperty("--opening-y", "0px");
      element.style.setProperty("--opening-scroll", "0px");
      element.style.setProperty("--opening-scroll-opacity", "1");
    };
    const paintInput = () => {
      inputFrame = 0;
      if (disposed || reduced.matches || !visible() || !onScreen) return;
      const bounds = element.getBoundingClientRect();
      const x = point && fine.matches ? Math.max(-5, Math.min(5, ((point.x - bounds.x) / bounds.width - .5) * 10)) : 0;
      const y = point && fine.matches ? Math.max(-3, Math.min(3, ((point.y - bounds.y) / bounds.height - .5) * 6)) : 0;
      const progress = Math.max(0, Math.min(1, -bounds.top / bounds.height));
      element.style.setProperty("--opening-x", `${x.toFixed(2)}px`);
      element.style.setProperty("--opening-y", `${y.toFixed(2)}px`);
      element.style.setProperty("--opening-scroll", `${(-progress * (innerWidth > 700 ? 32 : 12)).toFixed(2)}px`);
      element.style.setProperty("--opening-scroll-opacity", `${1 - progress * .15}`);
    };
    const queueInput = () => { if (!inputFrame && !reduced.matches && onScreen && visible()) inputFrame = requestAnimationFrame(paintInput); };
    const move = (event: PointerEvent) => { if (fine.matches && event.pointerType === "mouse") { point = { x: event.clientX, y: event.clientY }; queueInput(); } };
    const leave = () => { point = null; queueInput(); };
    const preferences = () => {
      if (!fine.matches) point = null;
      if (reduced.matches) { finish(); resetInput(); setPaused(false); }
      else queueInput();
    };
    const visibility = () => {
      setPaused(!visible());
      if (!visible()) {
        cancelFrames();
        if (current === "playing") { remaining = Math.max(0, remaining - (performance.now() - resumedAt)); clearTimeout(endTimer); }
        return;
      }
      if (current === "preparing") arrive();
      else if (current === "arriving") uncover();
      else if (current === "playing") armEnd();
      queueInput();
    };
    const observer = new IntersectionObserver(entries => {
      onScreen = entries[0].isIntersecting;
      if (!onScreen && (current === "playing" || current === "arriving")) finish();
      if (onScreen) queueInput();
    });
    const releaseReveal = (event: AnimationEvent) => {
      // Drop completed crop transforms/layer hints while annotations and the
      // signature continue. Keeping them filled delays the browser's image LCP.
      if (!disposed && current === "playing" && event.animationName === "opening-window-uncover") setUncovered(true);
    };
    observer.observe(element);
    actions.current = { replay, finish };
    const bootFrame = requestAnimationFrame(() => {
      setEnhanced(true); setPaused(!visible());
      if (reduced.matches || enteredThisDocument) finish(); else arrive();
    });
    element.addEventListener("pointermove", move, { passive: true });
    element.addEventListener("pointerleave", leave);
    element.addEventListener("animationend", releaseReveal);
    window.addEventListener("scroll", queueInput, { passive: true });
    window.addEventListener("resize", queueInput);
    document.addEventListener("visibilitychange", visibility);
    reduced.addEventListener("change", preferences);
    fine.addEventListener("change", preferences);
    return () => {
      disposed = true; cancelAnimationFrame(bootFrame); cancelFrames(); clearTimers(); resetInput(); observer.disconnect();
      image?.removeEventListener("load", loaded); image?.removeEventListener("error", failed);
      element.removeEventListener("pointermove", move); element.removeEventListener("pointerleave", leave);
      element.removeEventListener("animationend", releaseReveal);
      window.removeEventListener("scroll", queueInput); window.removeEventListener("resize", queueInput);
      document.removeEventListener("visibilitychange", visibility);
      reduced.removeEventListener("change", preferences); fine.removeEventListener("change", preferences);
      actions.current = { replay: () => {}, finish: () => {} };
    };
  }, [root]);

  return { phase, paused, uncovered, enhanced, artFailed, replay: () => actions.current.replay(), finish: () => actions.current.finish() };
}
