import { AbsoluteFill, Audio, Series, staticFile } from "remotion";
import { COLORS, FONT_BODY } from "./constants";
import { SCENES } from "./scenes";
import { Hook } from "./scenes/Hook";
import { Problem } from "./scenes/Problem";
import { Demo } from "./scenes/Demo";
import { Payoff } from "./scenes/Payoff";
import { Cta } from "./scenes/Cta";
import { Caption } from "./components/Caption";

export type PromoProps = {
  fundingFigure: string;
  programLabel: string;
  sceneFrames: number[];
  voiceoverFiles: string[];
  voiceoverEnabled: boolean;
};

export const Promo: React.FC<PromoProps> = ({
  fundingFigure,
  programLabel,
  sceneFrames,
  voiceoverFiles,
  voiceoverEnabled,
}) => {
  const [hookF, problemF, demoF, payoffF, ctaF] = sceneFrames;
  const vo = (i: number) =>
    voiceoverEnabled && voiceoverFiles[i] ? voiceoverFiles[i]! : null;

  return (
    <AbsoluteFill style={{ background: COLORS.bg, fontFamily: FONT_BODY, color: COLORS.ink }}>
      <Series>
        <Series.Sequence durationInFrames={hookF!}>
          <SceneWrap voiceoverFile={vo(0)}>
            <Hook fundingFigure={fundingFigure} programLabel={programLabel} />
            <Caption text={SCENES[0]!.caption} />
          </SceneWrap>
        </Series.Sequence>

        <Series.Sequence durationInFrames={problemF!}>
          <SceneWrap voiceoverFile={vo(1)}>
            <Problem />
            <Caption text={SCENES[1]!.caption} />
          </SceneWrap>
        </Series.Sequence>

        <Series.Sequence durationInFrames={demoF!}>
          <SceneWrap voiceoverFile={vo(2)}>
            <Demo />
            <Caption text={SCENES[2]!.caption} />
          </SceneWrap>
        </Series.Sequence>

        <Series.Sequence durationInFrames={payoffF!}>
          <SceneWrap voiceoverFile={vo(3)}>
            <Payoff />
            <Caption text={SCENES[3]!.caption} />
          </SceneWrap>
        </Series.Sequence>

        <Series.Sequence durationInFrames={ctaF!}>
          <SceneWrap voiceoverFile={vo(4)}>
            <Cta />
            <Caption text={SCENES[4]!.caption} />
          </SceneWrap>
        </Series.Sequence>
      </Series>
    </AbsoluteFill>
  );
};

const SceneWrap: React.FC<{
  voiceoverFile: string | null;
  children: React.ReactNode;
}> = ({ voiceoverFile, children }) => {
  return (
    <AbsoluteFill>
      {children}
      {voiceoverFile ? <Audio src={staticFile(voiceoverFile)} /> : null}
    </AbsoluteFill>
  );
};
