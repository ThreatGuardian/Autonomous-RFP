import { animate, motion, useInView, useMotionValue, useReducedMotion } from "motion/react";
import { type ReactNode, useEffect, useRef, useState } from "react";

export const EASE = [0.22, 1, 0.36, 1] as const;

/** Counts from the previous value to the new one; respects reduced-motion preferences. */
export function AnimatedNumber({ value, format, duration = 0.9 }: { value: number; format: (v: number) => string; duration?: number }) {
  const reduce = useReducedMotion();
  const mv = useMotionValue(reduce ? value : 0);
  const [text, setText] = useState(format(reduce ? value : 0));
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  useEffect(() => {
    if (!inView) return;
    if (reduce) { setText(format(value)); return; }
    const controls = animate(mv, value, { duration, ease: EASE, onUpdate: (v) => setText(format(v)) });
    return () => controls.stop();
  }, [value, inView]); // eslint-disable-line react-hooks/exhaustive-deps
  return <span ref={ref} className="tnum">{text}</span>;
}

/** Children rise into place one after another. */
export function Stagger({ children, className, delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  return (
    <motion.div className={className} initial="hidden" animate="show"
      variants={{ hidden: {}, show: { transition: { staggerChildren: 0.06, delayChildren: delay } } }}>
      {children}
    </motion.div>
  );
}

export function Rise({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.div className={className}
      variants={{ hidden: { opacity: 0, y: 12, filter: "blur(4px)" }, show: { opacity: 1, y: 0, filter: "blur(0px)", transition: { duration: 0.55, ease: EASE } } }}>
      {children}
    </motion.div>
  );
}
