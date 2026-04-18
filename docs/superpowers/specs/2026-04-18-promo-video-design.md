# EU Grant Matcher — Promo Video Design

Product demo video (30–60s, 16:9) for social sharing, Product Hunt launches, and pitch decks. Lead with the "money on the table" angle; close with a CTA to try the open-source app.

## Output

- **Duration:** 45s @ 30fps (1350 frames)
- **Resolution:** 1920×1080 (16:9 landscape)
- **Audio:** ElevenLabs TTS voiceover per scene + burned-in captions (social autoplay is muted)
- **Format:** MP4 (H.264 + AAC)

## Visual style

Hybrid per earlier decision:

- **Stylized open/close** — dark background (`#0b0d12`), accent color `#7cf` (matches the app's electric-blue accents), Inter typography, large kinetic numerals.
- **Middle section** — a faithful *mock* of the EU Grant Matcher UI, built as Remotion components (not a screen capture). Gives pixel-perfect control of pacing and captions while still looking like the real product.

## Scene breakdown

| # | Scene    | Range     | Frames   | VO (target) |
|---|----------|-----------|----------|-------------|
| 1 | Hook     | 0–8s      | 0–240    | "Horizon Europe put ninety-five-point-five billion euros on the table. Most of it never reaches the companies that qualify." |
| 2 | Problem  | 8–14s     | 240–420  | "Thousands of calls. Scattered portals. Hours of filtering." |
| 3 | Demo     | 14–38s    | 420–1140 | "Paste your company. We expand it into a profile, index live EU grants, and rank the best matches with an explanation for every score." |
| 4 | Payoff   | 38–43s    | 1140–1290| "Thirty seconds from company name to ranked EU grants." |
| 5 | CTA      | 43–45s    | 1290–1350| "Open source. Try it free." |

### Scene 1 — Hook (0–8s)

Dark background. `€0` counts up to `€95.5 B` over ~2s with spring easing, then holds. Below, in smaller type, "Horizon Europe 2021–2027." Below that, after a 4s delay, the line fades in: "Most companies never find the grants they qualify for."

### Scene 2 — Problem (8–14s)

Columns of stylized grant cards (title, acronym, deadline, eligibility chips) scroll upward at different speeds, slightly blurred. A centered text block reads "Thousands of calls. Scattered portals. Hours of filtering." A subtle vignette pulls focus to the center.

### Scene 3 — Demo (14–38s) — *the beef*

A faithful mock of the app, centered in a rounded "browser" frame. Five beats, each ~4–5s:

1. **Input (14–18s):** Landing state with the input and "Try OpenAI" button visible. Cursor types "OpenAI" into the textarea (typewriter effect on string slicing, per text-animations rule).
2. **Profile resolution (18–22s):** Loading shimmer, then the resolved profile chips fade in ("sector: AI", "size: large", "countries: EU-wide", "stage: growth", "focus: safety tooling").
3. **Indexing status (22–26s):** A status banner animates: "Indexed 247 live EU grants" with the number ticking up. Progress bar fills.
4. **Ranked results (26–34s):** Top 3 result cards slide in (stagger 8f). Each card: score (e.g., `92`), title, call prefix, a one-line "Why this matches" explanation. Score dial animates from 0 to target value.
5. **Explanation pop-out (34–38s):** The top card expands, highlighting a specific phrase ("Aligned with Horizon Europe's Cluster 4 - Digital, Industry & Space") via the word-highlight pattern.

### Scene 4 — Payoff (38–43s)

Clean slate, back to the dark aesthetic. Large text on two lines:
"Thirty seconds." (line 1, fades in)
"Company name → ranked EU grants." (line 2, slides in 6f later)

### Scene 5 — CTA (43–45s)

Logo mark + URL `eufundingme.com` (or whichever domain is live; parametrized) + a small line "Open source. MIT licensed."

## Architecture

New isolated sub-project at `video/` (keeps Remotion's Node/TS tooling separate from the FastAPI backend):

```
video/
  package.json
  tsconfig.json
  remotion.config.ts
  public/
    voiceover/promo/      # generated MP3s
    captions/             # optional srt
  scripts/
    generate-voiceover.ts # ElevenLabs TTS generator
  src/
    Root.tsx              # <Composition>
    Promo.tsx             # top-level composition (Series of scenes)
    scenes/
      Hook.tsx
      Problem.tsx
      Demo.tsx            # wraps the mock UI
      Payoff.tsx
      Cta.tsx
    mock/
      BrowserFrame.tsx
      InputCard.tsx
      ProfileChips.tsx
      IndexBanner.tsx
      ResultCard.tsx
    components/
      Caption.tsx         # burned-in caption renderer
      BigNumber.tsx
    constants.ts          # FPS, dimensions, colors, scene durations
    voiceover.ts          # scene → mp3 mapping + calculateMetadata helper
```

## Timing model

Use `<Series>` to sequence the five scenes one after another. Inside each scene use local `useCurrentFrame()` (per sequencing rule — local frames start at 0 inside a Sequence).

Scene durations are fixed in `constants.ts` first (frame-budgeted). If/when real voiceover is generated, `calculateMetadata` measures each MP3 with Mediabunny's `getAudioDuration` and passes scene lengths into the component as props, overriding the fixed budget. If voiceover files are missing, the composition falls back to the fixed budget so the composition still renders without an ElevenLabs key.

## Voiceover generation

`scripts/generate-voiceover.ts` reads scene VO text from a single source-of-truth `SCENES` array (shared with the composition for caption rendering), calls ElevenLabs per scene, and writes `public/voiceover/promo/scene-0N-<id>.mp3`. ElevenLabs voice + settings per the voiceover rule; stability 0.5 / similarity 0.75 / style 0.3 as a starting point.

Required env: `ELEVENLABS_API_KEY`. Default voice: a clear, mid-pitch "narrator" voice (e.g., Adam/Rachel — configurable via `ELEVENLABS_VOICE_ID`).

## Captions

Each scene's VO string also renders as a burned-in caption at the bottom of the frame via `components/Caption.tsx`. Word highlight pattern for emphasized terms ("€95.5B", "30 seconds"). No per-word timing — scene-level captions synced to scene windows are fine for a 45s ad.

## Fonts

`@remotion/google-fonts/Inter` (400, 600, 800). Loaded at the top of `Root.tsx` so render is blocked until ready.

## Open questions / placeholders

- **Exact funding figure:** Default to €95.5B (Horizon Europe 2021–2027 total budget — publicly sourced). Spec treats this as a prop so it's easy to swap for a tighter "unclaimed" figure if the user sources one.
- **Music bed:** Out of scope v1. Composition leaves an audio slot to drop in a royalty-free track later.
- **Final domain in CTA:** Default `eufundingme.com`; prop-driven.

## Verification

- `cd video && npm install`
- `npm run dev` — opens Remotion Studio at `http://localhost:3000`. Scrub all five scenes, confirm timing reads right without VO (silent mode).
- `npm run build` — renders `out/promo.mp4`. Confirm it plays end-to-end.
- If `ELEVENLABS_API_KEY` is set: `npm run voiceover` to generate MP3s, then re-render.

## Non-goals (v1)

- Multiple aspect ratios (9:16, 1:1). The spec is 16:9-only; if needed, extract layout into a parametrized composition later.
- Real screen recording. Mock UI only.
- Translated captions.
- Sentry/analytics instrumentation of the video itself.
