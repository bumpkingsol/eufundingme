#!/usr/bin/env node --experimental-strip-types
/**
 * Generate MP3 voiceovers for each scene via ElevenLabs TTS.
 *
 * Env:
 *   ELEVENLABS_API_KEY  (required)
 *   ELEVENLABS_VOICE_ID (optional; defaults to Adam)
 *
 * Writes to: public/voiceover/promo/scene-0N-<id>.mp3
 *
 * After running, set `voiceoverEnabled: true` in the composition default props
 * (src/Root.tsx) and re-render.
 */

import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { SCENES, voiceoverFile } from "../src/scenes.ts";

const API_KEY = process.env.ELEVENLABS_API_KEY;
const VOICE_ID = process.env.ELEVENLABS_VOICE_ID ?? "pNInz6obpgDQGcFmaJgB"; // Adam
const MODEL_ID = "eleven_multilingual_v2";

if (!API_KEY) {
  console.error("ELEVENLABS_API_KEY is not set. Aborting.");
  process.exit(1);
}

const __dirname = dirname(fileURLToPath(import.meta.url));
const publicDir = resolve(__dirname, "..", "public");

async function generate(text: string, outPath: string) {
  const res = await fetch(
    `https://api.elevenlabs.io/v1/text-to-speech/${VOICE_ID}`,
    {
      method: "POST",
      headers: {
        "xi-api-key": API_KEY!,
        "Content-Type": "application/json",
        Accept: "audio/mpeg",
      },
      body: JSON.stringify({
        text,
        model_id: MODEL_ID,
        voice_settings: {
          stability: 0.5,
          similarity_boost: 0.75,
          style: 0.3,
        },
      }),
    },
  );

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`ElevenLabs ${res.status}: ${body}`);
  }

  const buf = Buffer.from(await res.arrayBuffer());
  mkdirSync(dirname(outPath), { recursive: true });
  writeFileSync(outPath, buf);
  console.log(`  wrote ${outPath} (${buf.length} bytes)`);
}

async function main() {
  console.log(`Generating ${SCENES.length} voiceover clips...`);
  for (let i = 0; i < SCENES.length; i++) {
    const scene = SCENES[i]!;
    const rel = voiceoverFile(scene.id, i);
    const out = resolve(publicDir, rel);
    console.log(`[${i + 1}/${SCENES.length}] ${scene.id}: "${scene.voiceover}"`);
    await generate(scene.voiceover, out);
  }
  console.log("Done. Set `voiceoverEnabled: true` in src/Root.tsx and re-render.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
