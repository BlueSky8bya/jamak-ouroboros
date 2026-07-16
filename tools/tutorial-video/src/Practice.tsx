/** Practice video screen (PLAN P2 + 시각 큐 확장).
 *
 *  원칙 유지: 발화 문장은 절대 표시하지 않는다 (듣기 검수 연습).
 *  추가: 대사가 조작을 시키는 줄에서는 그 조작의 애니메이션(키캡 눌림,
 *  버튼 탭, 체크 토글, 화면 위치 미니맵, 나누기/합치기/드래그)을 대사
 *  시작부터 다음 대사 직전(= 사용자가 실제로 조작하는 쉼 구간 포함)까지
 *  중앙 무대에 띄운다. timing.json과 프레임 단위로 동기.
 */

// [WH-CHANGE v0.9.52 | FIX | 2026-07-16 | CHG-20260716-074]
// Reason: 이 영상은 에디터 왼쪽 열(.left = minmax(390px,440px), padding 14)
//   안에서 재생된다 → 실제 표시 폭 ~362px. 캔버스 1920 대비 배율 0.19.
//   기존 크기(fontSize 40 = 화면 7.6px, 진행 점 16px = 3px)는 판독 불가였다.
//   판독 기준을 "화면 16px 이상"으로 잡아 캔버스 최소 본문 84px(=16/0.19)로
//   전면 확대하고, 저배율에서 사라지는 요소(점 진행표시·상시 하단 안내)는
//   진행 바 + 큰 숫자로 대체해 중앙 무대에 픽셀을 몰아줬다.
// Related: docs/tutorial/재설계계획-2026-07.md §0
const DISPLAY_SCALE = 362 / 1920; // ≈0.19 — 크기 판단 기준 (읽을 글씨 ≥84px)

import { Audio, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { VISUALS, type Visual, type Zone } from "./visuals";

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

const INK = "#eaf1ff";
const BLUE = "#6ea8ff";
const SURFACE = "rgba(255,255,255,0.07)";
const LINE = "rgba(255,255,255,0.22)";

/* ── 애니메이션 프리미티브 ─────────────────────────────────────────── */

/** 반복 탭 사이클 0..1 (주기 seconds) */
function cycle(t: number, period = 1.6): number {
  return (t % period) / period;
}

/** 눌림 정도 0..1: 사이클 앞부분에서 꾹 눌렀다 떼는 곡선 */
function press(t: number, period = 1.6): number {
  const c = cycle(t, period);
  return interpolate(c, [0, 0.12, 0.3, 1], [0, 1, 0, 0]);
}

function KeyCap({ label, t }: { label: string; t: number }) {
  const p = press(t);
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        minWidth: 200,
        height: 190,
        padding: "0 48px",
        borderRadius: 32,
        background: `linear-gradient(180deg, rgba(255,255,255,${0.16 - p * 0.06}), rgba(255,255,255,0.05))`,
        border: `4px solid ${LINE}`,
        boxShadow: p > 0.3 ? `0 4px 0 rgba(0,0,0,0.5), 0 0 60px ${BLUE}66` : "0 14px 0 rgba(0,0,0,0.5)",
        transform: `translateY(${p * 12}px)`,
        color: INK,
        fontSize: 88,
        fontWeight: 800,
      }}
    >
      {label}
    </span>
  );
}

function KeysVisual({ rows, t }: { rows: string[][]; t: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 30 }}>
      {rows.map((keys, ri) => (
        <div key={ri} style={{ display: "flex", alignItems: "center", gap: 22 }}>
          {ri > 0 && <span style={{ fontSize: 56, color: INK, opacity: 0.6, marginRight: 10 }}>또는</span>}
          {keys.map((k, i) => (
            <span key={i} style={{ display: "flex", alignItems: "center", gap: 22 }}>
              {i > 0 && <span style={{ fontSize: 84, color: INK, opacity: 0.7 }}>+</span>}
              <KeyCap label={k} t={t + ri * 0.4} />
            </span>
          ))}
        </div>
      ))}
    </div>
  );
}

/** 탭 포인터: 대상 위로 들어와 콕 누르는 손가락 + 파문 링 */
function TapPointer({ t, x = 0, y = 0 }: { t: number; x?: number; y?: number }) {
  const c = cycle(t);
  const approach = interpolate(c, [0, 0.35, 0.45, 0.8, 1], [140, 16, 0, 16, 140]);
  const ring = interpolate(c, [0.45, 0.85], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{ position: "absolute", left: x, top: y, pointerEvents: "none" }}>
      {ring > 0 && ring < 1 && (
        <div
          style={{
            position: "absolute",
            left: -28,
            top: -28,
            width: 56 + ring * 180,
            height: 56 + ring * 180,
            marginLeft: -(ring * 180) / 2,
            marginTop: -(ring * 180) / 2,
            borderRadius: "50%",
            border: `6px solid ${BLUE}`,
            opacity: 1 - ring,
          }}
        />
      )}
      <div style={{ fontSize: 132, transform: `translate(${approach * 0.45}px, ${approach}px) rotate(-18deg)` }}>👆</div>
    </div>
  );
}

function ButtonVisual({ label, t }: { label: string; t: number }) {
  const p = press(t);
  return (
    <div style={{ position: "relative", display: "inline-block" }}>
      <div
        style={{
          padding: "44px 84px",
          borderRadius: 36,
          border: `4px solid ${p > 0.3 ? BLUE : LINE}`,
          background: p > 0.3 ? `${BLUE}33` : SURFACE,
          color: INK,
          fontSize: 88,
          fontWeight: 800,
          transform: `scale(${1 - p * 0.05})`,
          boxShadow: p > 0.3 ? `0 0 80px ${BLUE}55` : "none",
          whiteSpace: "nowrap",
        }}
      >
        {label}
      </div>
      <TapPointer t={t} x={300} y={80} />
    </div>
  );
}

function CheckVisual({ label, on, t }: { label: string; on: boolean; t: number }) {
  // 사이클마다 반대 상태에서 목표 상태로 토글 (탭 순간에 바뀜)
  const c = cycle(t, 2.2);
  const showTarget = c > 0.32;
  const checked = showTarget ? on : !on;
  return (
    <div style={{ position: "relative", display: "inline-block" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 30,
          padding: "38px 66px",
          borderRadius: 32,
          border: `4px solid ${LINE}`,
          background: SURFACE,
          color: INK,
          fontSize: 80,
          fontWeight: 700,
          whiteSpace: "nowrap",
        }}
      >
        <span
          style={{
            width: 84,
            height: 84,
            borderRadius: 16,
            border: `6px solid ${checked ? BLUE : LINE}`,
            background: checked ? BLUE : "transparent",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#fff",
            fontSize: 62,
            fontWeight: 900,
          }}
        >
          {checked ? "✓" : ""}
        </span>
        {label}
        <span style={{ fontSize: 52, opacity: 0.7 }}>{on ? "켜세요" : "꺼두세요"}</span>
      </div>
      <TapPointer t={t + 0.9} x={44} y={70} />
    </div>
  );
}

/** 자막 행을 눌러 고치기: 행 카드 + 탭 + 커서 깜빡임 */
function TapRowVisual({ t }: { t: number }) {
  const c = cycle(t, 2.4);
  const editing = c > 0.4;
  const caret = Math.floor(t * 2) % 2 === 0;
  return (
    <div style={{ position: "relative" }}>
      <div
        style={{
          width: 1080,
          padding: "44px 52px",
          borderRadius: 30,
          border: `4px solid ${editing ? BLUE : LINE}`,
          background: editing ? `${BLUE}1f` : SURFACE,
          color: INK,
          fontSize: 68,
          textAlign: "left",
        }}
      >
        자막 글을 누르면{editing && caret ? "▏" : ""} 고쳐요
      </div>
      <TapPointer t={t} x={560} y={-16} />
    </div>
  );
}

/** 긴 자막이 둘로 나뉘는 모션 */
function SplitVisual({ t }: { t: number }) {
  const c = cycle(t, 2.6);
  const gap = interpolate(c, [0.3, 0.75], [0, 90], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const bar = (w: number, dx: number) => (
    <div
      style={{
        width: w,
        height: 120,
        borderRadius: 26,
        background: `${BLUE}44`,
        border: `4px solid ${BLUE}`,
        transform: `translateX(${dx}px)`,
      }}
    />
  );
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 20 }}>
      <div style={{ display: "flex", alignItems: "center" }}>
        {bar(460, -gap / 2)}
        <div style={{ width: 0, position: "relative" }}>
          <span style={{ position: "absolute", left: -46, top: -104, fontSize: 92 }}>✂</span>
        </div>
        {bar(460, gap / 2)}
      </div>
      <span style={{ color: INK, opacity: 0.75, fontSize: 52 }}>커서 자리에서 둘로</span>
    </div>
  );
}

/** 토막 자막들이 하나로 합쳐지는 모션 */
function MergeVisual({ t }: { t: number }) {
  const c = cycle(t, 2.6);
  const together = interpolate(c, [0.3, 0.75], [72, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const bar = (w: number, dx: number) => (
    <div
      style={{
        width: w,
        height: 120,
        borderRadius: 26,
        background: `${BLUE}44`,
        border: `4px solid ${BLUE}`,
        transform: `translateX(${dx}px)`,
      }}
    />
  );
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 20 }}>
      <div style={{ display: "flex", alignItems: "center" }}>
        {bar(360, -together)}
        {bar(360, together)}
      </div>
      <span style={{ color: INK, opacity: 0.75, fontSize: 52 }}>아래 자막과 하나로</span>
    </div>
  );
}

/** 타임라인 손잡이 드래그 */
function DragVisual({ t }: { t: number }) {
  const c = cycle(t, 3.0);
  const dx = interpolate(c, [0.15, 0.6, 0.85], [0, 240, 240], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div style={{ position: "relative", width: 1180 }}>
      <div style={{ height: 40, borderRadius: 20, background: "rgba(255,255,255,0.12)" }} />
      <div
        style={{
          position: "absolute",
          top: -44,
          left: 200,
          width: 420 + dx,
          height: 128,
          borderRadius: 26,
          background: `${BLUE}3a`,
          border: `4px solid ${BLUE}`,
        }}
      />
      <div
        style={{
          position: "absolute",
          top: -60,
          left: 200 + 420 + dx - 16,
          width: 32,
          height: 160,
          borderRadius: 16,
          background: BLUE,
          boxShadow: `0 0 44px ${BLUE}88`,
        }}
      />
      <div style={{ position: "absolute", top: 16, left: 220 + 420 + dx, fontSize: 124, transform: "rotate(-18deg)" }}>
        👆
      </div>
      <div style={{ marginTop: 140, textAlign: "center", color: INK, opacity: 0.75, fontSize: 52 }}>
        밝은 손잡이를 좌우로
      </div>
    </div>
  );
}

/** ① ② 모드 탭 — ②를 탭 */
function TabsVisual({ t }: { t: number }) {
  const c = cycle(t, 2.2);
  const active = c > 0.35;
  const tab = (label: string, on: boolean) => (
    <div
      style={{
        padding: "36px 66px",
        borderRadius: 28,
        border: `4px solid ${on ? BLUE : LINE}`,
        background: on ? `${BLUE}33` : SURFACE,
        color: INK,
        fontSize: 72,
        fontWeight: 800,
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </div>
  );
  return (
    <div style={{ position: "relative", display: "flex", gap: 24 }}>
      {tab("① 내용", !active)}
      {tab("② 타이밍", active)}
      <TapPointer t={t} x={520} y={70} />
    </div>
  );
}

/** 배속 버튼 줄 — 0.75×를 탭 */
function SpeedVisual({ t }: { t: number }) {
  const c = cycle(t, 2.2);
  const on = c > 0.35;
  const btn = (label: string, hot: boolean) => (
    <div
      style={{
        padding: "32px 48px",
        borderRadius: 24,
        border: `4px solid ${hot && on ? BLUE : LINE}`,
        background: hot && on ? `${BLUE}33` : SURFACE,
        color: INK,
        fontSize: 68,
        fontWeight: 800,
      }}
    >
      {label}
    </div>
  );
  return (
    <div style={{ position: "relative", display: "flex", gap: 20 }}>
      {btn("0.5×", false)}
      {btn("0.75×", true)}
      {btn("1×", false)}
      {btn("1.5×", false)}
      <TapPointer t={t} x={300} y={60} />
    </div>
  );
}

/** 화면 어디인지 미니맵: 에디터 와이어프레임 + 해당 구역 글로우.
 *  0.19배로 줄어드니 블록을 크고 성기게 — 잔선은 저배율에서 회색 뭉개짐이 된다. */
function MiniMap({ zone, t }: { zone: Zone; t: number }) {
  const glow = 0.55 + 0.45 * Math.sin(t * 5);
  const hi: Record<Zone, { x: number; y: number; w: number; h: number }> = {
    "top-left": { x: 16, y: 14, w: 150, h: 46 },
    "video-below": { x: 16, y: 190, w: 240, h: 50 },
    "left-bottom": { x: 16, y: 262, w: 240, h: 54 },
    "list-top": { x: 300, y: 14, w: 250, h: 54 },
    list: { x: 300, y: 84, w: 250, h: 226 },
    bottom: { x: 16, y: 246, w: 240, h: 38 },
  };
  const z = hi[zone];
  return (
    <div
      style={{
        position: "relative",
        width: 570,
        height: 336,
        borderRadius: 22,
        border: `4px solid ${LINE}`,
        background: "rgba(0,0,0,0.3)",
        flex: "0 0 auto",
      }}
    >
      {/* video */}
      <div style={{ position: "absolute", left: 16, top: 66, width: 240, height: 112, borderRadius: 12, background: "rgba(255,255,255,0.14)" }} />
      {/* rows */}
      {[0, 1, 2, 3].map((i) => (
        <div key={i} style={{ position: "absolute", left: 300, top: 78 + i * 62, width: 250, height: 44, borderRadius: 10, background: "rgba(255,255,255,0.1)" }} />
      ))}
      {/* highlight */}
      <div
        style={{
          position: "absolute",
          left: z.x,
          top: z.y,
          width: z.w,
          height: z.h,
          borderRadius: 12,
          border: `7px solid ${BLUE}`,
          boxShadow: `0 0 ${28 + glow * 34}px ${BLUE}`,
          opacity: 0.65 + glow * 0.35,
        }}
      />
      <div style={{ position: "absolute", bottom: -64, width: "100%", textAlign: "center", color: INK, opacity: 0.75, fontSize: 46 }}>
        화면에서 이 자리
      </div>
    </div>
  );
}

function VisualBlock({ v, t }: { v: Visual; t: number }) {
  switch (v.kind) {
    case "keys":
      return <KeysVisual rows={v.rows} t={t} />;
    case "button":
      return <ButtonVisual label={v.label} t={t} />;
    case "check":
      return <CheckVisual label={v.label} on={v.on} t={t} />;
    case "tap-row":
      return <TapRowVisual t={t} />;
    case "split":
      return <SplitVisual t={t} />;
    case "merge":
      return <MergeVisual t={t} />;
    case "drag":
      return <DragVisual t={t} />;
    case "tabs":
      return <TabsVisual t={t} />;
    case "speed":
      return <SpeedVisual t={t} />;
  }
}

/* ── 본체 ─────────────────────────────────────────────────────────── */

export const Practice: React.FC<PracticeProps> = ({ n, title, timing }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  const spoken = timing.filter((c) => c.style !== "침묵");
  const speaking = spoken.find((c) => t >= c.start && t < c.end) ?? null;
  const doneCount = spoken.filter((c) => c.end <= t).length + (speaking ? 1 : 0);

  // 시각 큐는 대사 시작 ~ 다음 대사 시작(쉼 = 실습 시간)까지 유지
  let holdLine: Cue | null = null;
  for (let i = 0; i < spoken.length; i++) {
    const next = spoken[i + 1];
    if (t >= spoken[i].start && (!next || t < next.start)) {
      holdLine = spoken[i];
      break;
    }
  }
  const visuals = holdLine ? VISUALS[n]?.[holdLine.i] ?? null : null;
  const vt = holdLine ? Math.max(0, t - holdLine.start) : 0;
  const entrance = holdLine
    ? interpolate(t - holdLine.start, [0, 0.35], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : 0;
  const zones = (visuals ?? [])
    .map((v) => ("zone" in v ? v.zone : undefined))
    .filter((z): z is Zone => !!z);

  // 말하기 펄스 (시각 큐 없을 때 중앙, 있을 때는 상단 배지 옆 미니 점)
  const phase = Math.sin(t * 2 * Math.PI * 1.6);
  const icon = speaking ? STYLE_ICON[speaking.style] ?? "🔊" : "🤫";
  const progress = spoken.length ? Math.min(doneCount, spoken.length) / spoken.length : 0;

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        background: "linear-gradient(160deg, #101a2b 0%, #1b2a45 60%, #24365a 100%)",
        fontFamily: "'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif",
        color: INK,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "44px 60px",
        boxSizing: "border-box",
      }}
    >
      <Audio src={staticFile(`practice-${n}/audio.wav`)} />

      {/* top: 배지 + 진행 바 (점 17개는 0.19배에서 3px = 안 보임 → 바 + 큰 숫자) */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 18 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 24,
            fontSize: 62,
            fontWeight: 800,
            background: "rgba(255,255,255,0.08)",
            border: "3px solid rgba(255,255,255,0.25)",
            borderRadius: 999,
            padding: "16px 56px",
          }}
        >
          <span
            style={{
              width: 34,
              height: 34,
              borderRadius: 17,
              background: speaking ? BLUE : "rgba(255,255,255,0.2)",
              transform: speaking ? `scale(${1 + 0.25 * phase})` : "none",
            }}
          />
          연습 {n} · {title}
          <span style={{ fontSize: 56 }}>{icon}</span>
        </div>
        <div style={{ display: "flex", gap: 20, alignItems: "center" }}>
          <div style={{ width: 620, height: 18, borderRadius: 9, background: "rgba(255,255,255,0.18)", overflow: "hidden" }}>
            <div style={{ width: `${progress * 100}%`, height: "100%", background: BLUE }} />
          </div>
          <span style={{ fontSize: 52, fontWeight: 800, opacity: 0.9 }}>
            {Math.min(doneCount, spoken.length)} / {spoken.length}
          </span>
        </div>
      </div>

      {/* center stage: 시각 큐 or 말하기 오브 — 화면 픽셀 대부분을 여기에 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 70,
          transform: `scale(${0.9 + entrance * 0.1})`,
          opacity: visuals ? entrance : 1,
          minHeight: 640,
        }}
      >
        {visuals ? (
          <>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 56 }}>
              {visuals.map((v, i) => (
                <VisualBlock key={i} v={v} t={vt} />
              ))}
            </div>
            {zones.length > 0 && <MiniMap zone={zones[0]} t={vt} />}
          </>
        ) : (
          <div
            style={{
              width: 460,
              height: 460,
              borderRadius: "50%",
              background: speaking
                ? "radial-gradient(circle, #6ea8ff 0%, #3b6fd4 70%)"
                : "radial-gradient(circle, #3a4a6a 0%, #2b3a58 70%)",
              transform: `scale(${speaking ? 1 + 0.1 * phase : 1})`,
              boxShadow: `0 0 ${speaking ? 90 : 16}px ${speaking ? "#6ea8ffaa" : "#00000055"}`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 210,
            }}
          >
            {icon}
          </div>
        )}
      </div>

      {/* bottom: 고정 안내 (발화 문장은 절대 표시하지 않음) */}
      <div
        style={{
          fontSize: 54,
          fontWeight: 700,
          background: "rgba(0,0,0,0.35)",
          borderRadius: 26,
          padding: "22px 52px",
        }}
      >
        👂 듣고, 화면에 뜨는 대로 해보세요
      </div>
    </div>
  );
};
