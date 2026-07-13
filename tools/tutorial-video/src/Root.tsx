import { CalculateMetadataFunction, Composition, staticFile } from "remotion";
import { getAudioDurationInSeconds } from "@remotion/media-utils";
import { Cue, Practice, PracticeProps } from "./Practice";

const FPS = 30;

const TITLES: Record<number, string> = {
  1: "기본기",
  2: "재생 다루기",
  3: "빠르게 훑기",
  4: "나누기·합치기",
  5: "타이밍",
  6: "마무리",
};

// duration comes from the real audio (PLAN §2.5 — calculateMetadata, no guesses)
const calcMeta =
  (n: number): CalculateMetadataFunction<PracticeProps> =>
  async ({ props }) => {
    const timing: Cue[] = await fetch(staticFile(`practice-${n}/timing.json`)).then(
      (r) => r.json(),
    );
    const seconds = await getAudioDurationInSeconds(staticFile(`practice-${n}/audio.wav`));
    return {
      durationInFrames: Math.ceil(seconds * FPS),
      props: { ...props, timing },
    };
  };

export const RemotionRoot: React.FC = () => (
  <>
    {[1, 2, 3, 4, 5, 6].map((n) => (
      <Composition
        key={n}
        id={`practice-${n}`}
        component={Practice}
        fps={FPS}
        width={1920}
        height={1080}
        durationInFrames={60} // replaced by calculateMetadata
        defaultProps={{ n, title: TITLES[n], timing: [] as Cue[] }}
        calculateMetadata={calcMeta(n)}
      />
    ))}
  </>
);
