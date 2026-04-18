import { FPS } from "./constants";

export type SceneId = "hook" | "problem" | "demo" | "payoff" | "cta";

export type Scene = {
  id: SceneId;
  voiceover: string;
  caption: string;
  fallbackSeconds: number;
};

export const SCENES: Scene[] = [
  {
    id: "hook",
    voiceover:
      "Horizon Europe put ninety-five point five billion euros on the table. Most of it never reaches the companies that qualify.",
    caption:
      "Horizon Europe: €95.5B on the table. Most of it never reaches the companies that qualify.",
    fallbackSeconds: 8,
  },
  {
    id: "problem",
    voiceover: "Thousands of calls. Scattered portals. Hours of filtering.",
    caption: "Thousands of calls. Scattered portals. Hours of filtering.",
    fallbackSeconds: 6,
  },
  {
    id: "demo",
    voiceover:
      "Paste your company. We expand it into a profile, index live EU grants, and rank the best matches with an explanation for every score.",
    caption:
      "Paste your company → profile → live grants → ranked matches with explanations.",
    fallbackSeconds: 24,
  },
  {
    id: "payoff",
    voiceover: "Thirty seconds from company name to ranked EU grants.",
    caption: "30 seconds. Company name → ranked EU grants.",
    fallbackSeconds: 5,
  },
  {
    id: "cta",
    voiceover: "Open source. Try it free.",
    caption: "Open source. Try it free.",
    fallbackSeconds: 2,
  },
];

export const fallbackSceneFrames = () =>
  SCENES.map((s) => Math.round(s.fallbackSeconds * FPS));

export const voiceoverFile = (id: SceneId, index: number) =>
  `voiceover/promo/scene-${String(index + 1).padStart(2, "0")}-${id}.mp3`;
