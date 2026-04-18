import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, FONT_BODY, FONT_DISPLAY } from "../constants";
import { Ambient } from "../components/Ambient";

type Props = {
  fundingFigure: string;
  programLabel: string;
};

export const Hook: React.FC<Props> = ({ fundingFigure, programLabel }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const numberEntry = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 90 },
  });
  const numberScale = interpolate(numberEntry, [0, 1], [0.6, 1]);
  const numberOpacity = interpolate(numberEntry, [0, 1], [0, 1]);

  const programOpacity = interpolate(frame, [fps * 0.8, fps * 1.4], [0, 1], {
    extrapolateRight: "clamp",
  });

  const tagFrame = frame - fps * 3.2;
  const tagOpacity = interpolate(tagFrame, [0, fps * 0.6], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const tagY = interpolate(tagFrame, [0, fps * 0.6], [20, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        background: `
          radial-gradient(circle at top left, rgba(201, 106, 43, 0.22), transparent 34%),
          radial-gradient(circle at top right, rgba(0, 109, 91, 0.24), transparent 32%),
          linear-gradient(180deg, ${COLORS.bgSoft} 0%, ${COLORS.bg} 100%)
        `,
        justifyContent: "center",
        alignItems: "center",
        fontFamily: FONT_BODY,
      }}
    >
      <Ambient />

      <div
        style={{
          position: "absolute",
          top: 160,
          textAlign: "center",
          opacity: programOpacity,
          color: COLORS.accentStrong,
          fontSize: 28,
          fontWeight: 600,
          letterSpacing: "0.2em",
          textTransform: "uppercase",
        }}
      >
        {programLabel}
      </div>

      <div
        style={{
          transform: `scale(${numberScale})`,
          opacity: numberOpacity,
          fontFamily: FONT_DISPLAY,
          fontWeight: 700,
          fontSize: 420,
          lineHeight: 1,
          color: COLORS.ink,
          letterSpacing: "-0.04em",
        }}
      >
        {fundingFigure}
      </div>

      <div
        style={{
          position: "absolute",
          bottom: 260,
          textAlign: "center",
          opacity: tagOpacity,
          transform: `translateY(${tagY}px)`,
          color: COLORS.ink,
          fontFamily: FONT_DISPLAY,
          fontSize: 54,
          fontWeight: 700,
          maxWidth: 1200,
          letterSpacing: "-0.03em",
          lineHeight: 1.15,
        }}
      >
        Most companies never find the grants{" "}
        <span style={{ color: COLORS.accent }}>they qualify for.</span>
      </div>
    </AbsoluteFill>
  );
};
