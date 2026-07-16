import { useEffect, useRef, useState, type RefObject } from "react";

declare global {
  interface Window {
    YT: any;
    onYouTubeIframeAPIReady?: () => void;
  }
}

/** Load the IFrame API once, then run `cb` (immediately if it's already up). */
function whenApiReady(cb: () => void): void {
  if (window.YT?.Player) {
    cb();
    return;
  }
  const prev = window.onYouTubeIframeAPIReady;
  window.onYouTubeIframeAPIReady = () => {
    prev?.();
    cb();
  };
  if (!document.querySelector('script[src*="youtube.com/iframe_api"]')) {
    const tag = document.createElement("script");
    tag.src = "https://www.youtube.com/iframe_api";
    document.head.appendChild(tag);
  }
}

// [WH-CHANGE v0.9.54 | FIX | 2026-07-17 | CHG-20260717-079]
// Reason: 검수 모달의 미니 영상이 일반 embed(<iframe src=...?start=N>)라
//   start 파라미터가 **정수 초만** 받는다 → 42:29.0 자막인데 42:28부터
//   재생돼 "표시 시각과 실제가 안 맞는다"(사용자 지적). 게다가 매번
//   리마운트해야 다시 재생돼 일시정지도 불가능했다. 메인 플레이어와 같은
//   IFrame API로 바꿔 seekTo(소수점)로 정확히 그 시점을 잡고 재생/정지도
//   직접 제어한다.
// Related: CHANGELOG CHG-20260717-079.
/** Mini player for the review modals — precise (float) seeking + real
 *  play/pause. Created only while `enabled` (the modal is open), and
 *  destroyed on close so it never plays behind the editor. */
// [WH-CHANGE v0.9.60 | FIX | 2026-07-17 | CHG-20260717-091]
// Reason: ref로 host를 받으니 **자리가 생기기 전에** 생성 신호가 울리는 모달에서
//   플레이어가 영영 안 만들어졌다 (맞춤법 모달: qcModal을 먼저 켜고 "검사 중..."을
//   띄운 뒤 결과가 와야 플레이어 자리가 렌더됨 → 그때 effect는 이미 host=null로
//   반환했고 deps가 안 바뀌어 재시도 없음 → 검은 칸 + 버튼 비활성. 한자 모달은
//   제안을 받은 뒤 모달을 켜서 우연히 동작했다). host를 **state로 받아** 자리가
//   붙는 순간이 곧 deps 변화가 되게 한다.
// Related: CHANGELOG CHG-20260717-091.
export function useMiniPlayer(
  videoId: string,
  enabled: boolean,
  host: HTMLDivElement | null,
) {
  const playerRef = useRef<any>(null);
  const [ready, setReady] = useState(false);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    let disposed = false;
    setReady(false);

    // 자리가 아직 없으면 만들지 않는다. host가 deps에 있으므로, 자리가 붙는
    // 순간 이 effect가 다시 돌아 그때 만든다 (맞춤법 모달처럼 늦게 렌더되는 경우).
    if (!host) return;
    // YT.Player는 대상 엘리먼트를 iframe으로 **치환**한다. 그래서 React가
    // 소유한 노드를 넘기면 언마운트 때 React가 이미 사라진 노드를 지우려다
    // 터진다(removeChild NotFoundError). React가 모르는 자식을 직접 만들어
    // 넘기고, 정리는 wrapper를 비우는 것으로 한다.
    const mount = document.createElement("div");
    mount.style.width = "100%";
    mount.style.height = "100%";
    host.appendChild(mount);

    whenApiReady(() => {
      if (disposed || !mount.isConnected) return;
      try {
        playerRef.current = new window.YT.Player(mount, {
          videoId,
          width: "100%",
          height: "100%",
          playerVars: { rel: 0, modestbranding: 1, disablekb: 1 },
          events: {
            onReady: () => setReady(true),
            onStateChange: (e: any) => setPlaying(e.data === 1),
            onError: () => setReady(false),
          },
        });
      } catch (e) {
        console.error("mini player init failed:", e);
        playerRef.current = null;
      }
    });

    return () => {
      disposed = true;
      setReady(false);
      setPlaying(false);
      playerRef.current?.destroy?.();
      playerRef.current = null;
      // destroy()가 남긴 잔해까지 정리 — 우리가 만든 자식이라 React는 모른다
      host.replaceChildren();
    };
  }, [videoId, enabled, host]);

  const p = () => playerRef.current;
  return {
    ready,
    playing,
    /** seek to an exact (fractional) second and play from there */
    cueAt: (t: number) => {
      const player = p();
      if (!player?.seekTo) return;
      player.seekTo(Math.max(0, t), true);
      player.playVideo?.();
    },
    play: () => p()?.playVideo?.(),
    pause: () => p()?.pauseVideo?.(),
    playPause: () => {
      const player = p();
      if (!player?.getPlayerState) return;
      if (player.getPlayerState() === 1) player.pauseVideo();
      else player.playVideo();
    },
  };
}

/** YouTube IFrame player bound to #yt-player; polls current time.
 *  `freezeRef` (optional): while true, the clock poll is skipped so the editor
 *  stops re-rendering — used during a timeline drag so the main thread stays
 *  free and the dragged handle tracks the pointer without stutter. */
export function usePlayer(videoId: string, freezeRef?: RefObject<boolean>) {
  const playerRef = useRef<any>(null);
  const [ready, setReady] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [rate, setRateState] = useState(1);

  useEffect(() => {
    let disposed = false;

    function create() {
      if (disposed) return;
      // the widget API throws synchronously on a malformed/blocked video —
      // that must degrade to "no player", never unmount the whole editor
      // (the subtitle list is still fully usable without playback)
      try {
        playerRef.current = new window.YT.Player("yt-player", {
          videoId,
          // fill the container instead of YouTube's default 640x360 (which was
          // getting cropped to the panel width — wrong ratio + too small)
          width: "100%",
          height: "100%",
          playerVars: { rel: 0, disablekb: 1 },
          events: {
            onReady: () => setReady(true),
            onStateChange: (e: any) => setPlaying(e.data === 1),
            onError: () => setReady(false), // deleted/embed-blocked/region-locked
          },
        });
      } catch (e) {
        console.error("youtube player init failed:", e);
        playerRef.current = null;
      }
    }

    if (window.YT?.Player) {
      create();
    } else {
      const prev = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = () => {
        prev?.();
        create();
      };
      if (!document.querySelector('script[src*="youtube.com/iframe_api"]')) {
        const tag = document.createElement("script");
        tag.src = "https://www.youtube.com/iframe_api";
        document.head.appendChild(tag);
      }
    }

    const timer = setInterval(() => {
      if (freezeRef?.current) return; // a timeline drag is in progress
      const p = playerRef.current;
      if (!p?.getCurrentTime) return;
      const t = p.getCurrentTime();
      // only re-render when the clock actually moved — a paused player would
      // otherwise fire a needless re-render every tick (returning prev makes
      // React bail out), which is what let the timeline handles jitter.
      setCurrentTime((prev) => (Math.abs(t - prev) > 0.02 ? t : prev));
    }, 250);

    return () => {
      disposed = true;
      clearInterval(timer);
      playerRef.current?.destroy?.();
    };
  }, [videoId]);

  const p = () => playerRef.current;

  return {
    ready,
    currentTime,
    playing,
    rate,
    setRate: (r: number) => {
      p()?.setPlaybackRate?.(r);
      setRateState(r);
    },
    seekTo: (t: number) => p()?.seekTo?.(t, true),
    seekBy: (delta: number) => {
      const cur = p()?.getCurrentTime?.() ?? 0;
      p()?.seekTo?.(Math.max(0, cur + delta), true);
    },
    play: () => p()?.playVideo?.(),
    pause: () => p()?.pauseVideo?.(),
    playPause: () => {
      if (!p()?.getPlayerState) return;
      if (p().getPlayerState() === 1) p().pauseVideo();
      else p().playVideo();
    },
  };
}
