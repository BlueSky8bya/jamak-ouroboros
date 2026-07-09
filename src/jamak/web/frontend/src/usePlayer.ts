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

  useEffect(() => {
    let disposed = false;

    function create() {
      if (disposed) return;
      playerRef.current = new window.YT.Player("yt-player", {
        videoId,
        playerVars: { rel: 0 },
        events: { onReady: () => setReady(true) },
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

  return {
    ready,
    currentTime,
    seekTo: (t: number) => playerRef.current?.seekTo?.(t, true),
    playPause: () => {
      const p = playerRef.current;
      if (!p?.getPlayerState) return;
      // 1 = playing
      if (p.getPlayerState() === 1) p.pauseVideo();
      else p.playVideo();
    },
  };
}
