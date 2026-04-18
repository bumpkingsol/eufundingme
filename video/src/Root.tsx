import { Composition } from "remotion";
import { Promo } from "./Promo";
import type { PromoProps } from "./Promo";
import { FPS, HEIGHT, WIDTH } from "./constants";
import { SCENES, fallbackSceneFrames, voiceoverFile } from "./scenes";
import { loadFont as loadIBMPlex } from "@remotion/google-fonts/IBMPlexSans";
import { loadFont as loadSpaceGrotesk } from "@remotion/google-fonts/SpaceGrotesk";

loadIBMPlex("normal", { weights: ["400", "500", "600"], subsets: ["latin"] });
loadSpaceGrotesk("normal", { weights: ["500", "700"], subsets: ["latin"] });

const sceneFrames = fallbackSceneFrames();
const totalFrames = sceneFrames.reduce((a, b) => a + b, 0);

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Promo"
      component={Promo}
      durationInFrames={totalFrames}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
      defaultProps={{
        fundingFigure: "€95.5B",
        programLabel: "Horizon Europe 2021–2027",
        sceneFrames,
        voiceoverFiles: SCENES.map((s, i) => voiceoverFile(s.id, i)),
        voiceoverEnabled: false,
      } satisfies PromoProps}
    />
  );
};
