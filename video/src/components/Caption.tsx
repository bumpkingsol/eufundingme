import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, FONT_BODY } from "../constants";

export const Caption: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const fadeIn = interpolate(frame, [0, fps * 0.3], [0, 1], {
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(
    frame,
    [durationInFrames - fps * 0.3, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp" },
  );
  const opacity = Math.min(fadeIn, fadeOut);

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: 64,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          opacity,
          maxWidth: 1400,
          padding: "18px 32px",
          borderRadius: 18,
          background: COLORS.paperSolid,
          border: `1px solid ${COLORS.line}`,
          color: COLORS.ink,
          fontFamily: FONT_BODY,
          fontSize: 34,
          fontWeight: 600,
          textAlign: "center",
          letterSpacing: "-0.005em",
          lineHeight: 1.25,
          boxShadow: COLORS.shadow,
        }}
      >
        {text}
      </div>
    </AbsoluteFill>
  );
};
