import { useEffect, useRef, useState } from "react";

export interface DropOption {
  value: string;
  label: string;
  disabled?: boolean;
  note?: string; // small trailing hint (e.g. "완료")
}

/** Sleek custom dropdown — replaces the browser's native <select> so the open
 *  menu can be styled to match the app (native option lists can't be). */
export function Dropdown({
  value,
  options,
  onChange,
  className = "",
  title,
  ariaLabel,
  stopPropagation = false,
}: {
  value: string;
  options: DropOption[];
  onChange: (v: string) => void;
  className?: string;
  title?: string;
  ariaLabel?: string;
  stopPropagation?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  // the menu is position:fixed at the button's screen coords so it escapes any
  // ancestor overflow:hidden (e.g. the job card, which clipped it before).
  const [pos, setPos] = useState<React.CSSProperties | null>(null);
  const current = options.find((o) => o.value === value);

  const place = () => {
    const b = btnRef.current?.getBoundingClientRect();
    if (!b) return;
    const estH = Math.min(options.length * 40 + 12, 280);
    const below = window.innerHeight - b.bottom;
    const up = below < estH && b.top > below; // flip up if not enough room below
    setPos({
      position: "fixed",
      left: b.left,
      minWidth: b.width,
      maxHeight: 280,
      ...(up
        ? { bottom: window.innerHeight - b.top + 4, top: "auto" }
        : { top: b.bottom + 4, bottom: "auto" }),
    });
  };

  useEffect(() => {
    if (!open) return;
    place();
    const onDoc = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    // the fixed menu can't follow a page scroll — close it. But ignore scrolls
    // that happen INSIDE the menu (its own option list can scroll when long).
    const onScroll = (e: Event) => {
      if (ref.current && e.target instanceof Node && ref.current.contains(e.target)) return;
      setOpen(false);
    };
    window.addEventListener("pointerdown", onDoc);
    window.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("pointerdown", onDoc);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const stop = (e: { stopPropagation: () => void }) => {
    if (stopPropagation) e.stopPropagation();
  };

  return (
    <div
      ref={ref}
      className={"dd " + className + (open ? " open" : "")}
      onClick={stop}
      onPointerDown={stop}
    >
      <button
        ref={btnRef}
        type="button"
        className="dd-btn"
        title={title}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={(e) => {
          stop(e);
          setOpen((o) => !o);
        }}
      >
        <span className="dd-val">{current?.label ?? value}</span>
        <span className="dd-arrow" aria-hidden>
          ▾
        </span>
      </button>
      {open && (
        <div className="dd-menu" role="listbox" style={pos ?? undefined}>
          {options.map((o) => (
            <button
              key={o.value}
              type="button"
              role="option"
              aria-selected={o.value === value}
              disabled={o.disabled}
              className={"dd-opt" + (o.value === value ? " sel" : "")}
              onClick={(e) => {
                stop(e);
                if (o.disabled) return;
                onChange(o.value);
                setOpen(false);
              }}
            >
              <span className="dd-opt-label">{o.label}</span>
              {o.note && <span className="dd-note">{o.note}</span>}
              {o.value === value && <span className="dd-check">✓</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
