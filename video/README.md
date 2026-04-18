# EU Grant Matcher — Promo Video

Remotion project for the 45s product demo video. See design spec at `docs/superpowers/specs/2026-04-18-promo-video-design.md`.

## Setup

```bash
cd video
npm install
```

## Preview

```bash
npm run dev
```

Opens Remotion Studio. The composition is `Promo`.

## Render

```bash
npm run build
# → out/promo.mp4
```

## Voiceover (optional)

The composition renders without voiceover using silent placeholder timing. To generate real voiceover:

```bash
export ELEVENLABS_API_KEY=...
export ELEVENLABS_VOICE_ID=...   # optional, defaults to Adam
npm run voiceover
npm run build
```

Generated MP3s land in `public/voiceover/promo/` and are picked up by `calculateMetadata` at render time.

## Scenes

| # | ID       | Target length | Copy |
|---|----------|---------------|------|
| 1 | hook     | 8s            | Horizon Europe put €95.5B on the table. Most of it never reaches the companies that qualify. |
| 2 | problem  | 6s            | Thousands of calls. Scattered portals. Hours of filtering. |
| 3 | demo     | 24s           | Paste your company. We expand it, index live EU grants, and rank the best matches. |
| 4 | payoff   | 5s            | 30 seconds from company name to ranked EU grants. |
| 5 | cta      | 2s            | Open source. Try it free. |

Edit `src/scenes.ts` to change copy or timing.
