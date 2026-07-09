import { useEffect, useRef, useState } from "react";

declare global {
  interface Window {
    YT: any;
    onYouTubeIframeAPIReady?: () => void;
  }
}

/** YouTube IFrame player bound to #yt-player; polls current time. */
export function usePlayer(videoId: string) {
  const playerRef = useRef<any>(null);
  const [ready, setReady] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    let disposed = false;

    function create() {
      if (disposed) return;
      playerRef.current = new window.YT.Player("yt-player", {
        videoId,
        playerVars: { rel: 0, disablekb: 1 },
        events: {
          onReady: () => setReady(true),
          onStateChange: (e: any) => setPlaying(e.data === 1),
        },
      });
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
      const p = playerRef.current;
      if (p?.getCurrentTime) setCurrentTime(p.getCurrentTime());
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
