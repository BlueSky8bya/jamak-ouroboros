import { useEffect, useRef, useState, type RefObject } from "react";

declare global {
  interface Window {
    YT: any;
    onYouTubeIframeAPIReady?: () => void;
  }
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
