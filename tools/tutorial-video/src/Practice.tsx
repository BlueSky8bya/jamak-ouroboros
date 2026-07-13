/** Practice video screen (PLAN.md §2.5).
 *
 *  Core constraint: the spoken sentence is NEVER shown — reviewers must
 *  listen and compare against the app's subtitles, not read the screen.
 *  The screen only shows: course badge, progress dots, a pulse that moves
 *  while speech is playing, a style icon, and a fixed bottom hint.
 */

import { Audio, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

export interface Cue {
  i: number;
  text: string;
  style: string;
  start: number;
  end: number;
}

export interface PracticeProps {
  n: number;
  title: string;
  timing: Cue[];
}

const STYLE_ICON: Record<string, string> = {
  빠르게: "⚡",
  느리게: "🐢",
  웅얼: "🙉",
  침묵: "🤫",
};

export const Practice: React.FC<PracticeProps> = ({ n, title, timing }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  const spoken = timing.filter((c) => c.style !== "침묵");
  const active = spoken.find((c) => t >= c.start && t < c.end) ?? null;
  const doneCount = spoken.filter((c) => c.end <= t).length + (active ? 1 : 0);

  // pulse: breathing ring while speaking, still when silent
  const phase = Math.sin(t * 2 * Math.PI * 1.6);
  const scale = active ? 1 + 0.1 * phase : 1;
  const glow = active ? interpolate(phase, [-1, 1], [24, 64]) : 8;
  const icon = active ? STYLE_ICON[active.style] ?? "🔊" : "🤫";

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        background: "linear-gradient(160deg, #101a2b 0%, #1b2a45 60%, #24365a 100%)",
        fontFamily: "'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif",
        color: "#eaf1ff",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "60px 80px",
        boxSizing: "border-box",
      }}
    >
      <Audio src={staticFile(`practice-${n}/audio.wav`)} />

      {/* top: course badge + progress */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 28 }}>
        <div
          style={{
            fontSize: 54,
            fontWeight: 700,
            background: "rgba(255,255,255,0.08)",
            border: "2px solid rgba(255,255,255,0.25)",
            borderRadius: 999,
            padding: "18px 56px",
          }}
        >
          연습 {n} · {title}
        </div>
        <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
          {spoken.map((c, idx) => (
            <div
              key={c.i}
              style={{
                width: 18,
                height: 18,
                borderRadius: 9,
                background:
                  idx < doneCount ? "#6ea8ff" : "rgba(255,255,255,0.18)",
              }}
            />
          ))}
          <span style={{ fontSize: 34, marginLeft: 18, opacity: 0.85 }}>
            {Math.min(doneCount, spoken.length)} / {spoken.length}
          </span>
        </div>
      </div>

      {/* center: speaking pulse + style icon */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 30 }}>
        <div
          style={{
            width: 300,
            height: 300,
            borderRadius: "50%",
            background: active
              ? "radial-gradient(circle, #6ea8ff 0%, #3b6fd4 70%)"
              : "radial-gradient(circle, #3a4a6a 0%, #2b3a58 70%)",
            transform: `scale(${scale})`,
            boxShadow: `0 0 ${glow}px ${active ? "#6ea8ffaa" : "#00000055"}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 130,
          }}
        >
          {icon}
        </div>
        <div style={{ fontSize: 40, opacity: 0.75, height: 50 }}>
          {active ? "말하는 중…" : "잠시 조용한 구간"}
        </div>
      </div>

      {/* bottom: fixed instruction (never the spoken sentence) */}
      <div
        style={{
          fontSize: 44,
          background: "rgba(0,0,0,0.35)",
          borderRadius: 20,
          padding: "24px 48px",
        }}
      >
        👂 귀로 듣고, 자막과 맞는지 확인하세요
      </div>
    </div>
  );
};
