"use client";

import { useEffect, useRef, type ComponentProps } from "react";

export function IntentButton({ prepare, allowFocus, onPointerEnter, onPointerLeave, onFocus, onBlur, onClick, ...props }: ComponentProps<"button"> & { prepare: () => void; allowFocus?: () => boolean }) {
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const cancel = () => { clearTimeout(timer.current); timer.current=undefined; };
  const schedule = () => { cancel(); timer.current=setTimeout(prepare,100); };
  useEffect(()=>()=>clearTimeout(timer.current),[]);
  return <button {...props} onPointerEnter={event=>{schedule();onPointerEnter?.(event);}} onPointerLeave={event=>{cancel();onPointerLeave?.(event);}} onFocus={event=>{if(allowFocus?.()!==false)schedule();onFocus?.(event);}} onBlur={event=>{cancel();onBlur?.(event);}} onClick={event=>{cancel();onClick?.(event);}} />;
}
