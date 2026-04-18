import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, FONT_DISPLAY } from "../constants";
import { Ambient } from "../components/Ambient";

export const Payoff: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const line1 = spring({ frame, fps, config: { damping: 200 } });
  const line1Opacity = interpolate(line1, [0, 1], [0, 1]);
  const line1Y = interpolate(line1, [0, 1], [24, 0]);

  const line2 = spring({
    frame: frame - fps * 0.5,
    fps,
    config: { damping: 200 },
  });
  const line2Opacity = interpolate(line2, [0, 1], [0, 1]);
  const line2X = interpolate(line2, [0, 1], [-30, 0]);

  return (
    <AbsoluteFill
      style={{
        background: `
          radial-gradient(circle at top left, rgba(201, 106, 43, 0.2), transparent 34%),
          radial-gradient(circle at top right, rgba(0, 109, 91, 0.22), transparent 32%),
          linear-gradient(180deg, ${COLORS.bgSoft} 0%, ${COLORS.bg} 100%)
        `,
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <Ambient />
      <div style={{ textAlign: "center" }}>
        <div
          style={{
            opacity: line1Opacity,
            transform: `translateY(${line1Y}px)`,
            fontFamily: FONT_DISPLAY,
            fontWeight: 700,
            fontSize: 240,
            color: COLORS.ink,
            letterSpacing: "-0.04em",
            lineHeight: 1,
            marginBottom: 24,
          }}
        >
          30 seconds.
        </div>
        <div
          style={{
            opacity: line2Opacity,
            transform: `translateX(${line2X}px)`,
            fontFamily: FONT_DISPLAY,
            fontSize: 56,
            fontWeight: 500,
            color: COLORS.muted,
            letterSpacing: "-0.02em",
          }}
        >
          Company name{" "}
          <span style={{ color: COLORS.accent, fontWeight: 700 }}>→</span>{" "}
          <span style={{ color: COLORS.ink, fontWeight: 700 }}>ranked EU grants.</span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
