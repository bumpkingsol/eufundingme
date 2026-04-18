import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, FONT_DISPLAY } from "../constants";
import { Ambient } from "../components/Ambient";

export const Cta: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const s = spring({ frame, fps, config: { damping: 14, stiffness: 140 } });
  const scale = interpolate(s, [0, 1], [0.85, 1]);
  const opacity = interpolate(s, [0, 1], [0, 1]);

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
      }}
    >
      <Ambient />
      <div
        style={{
          opacity,
          transform: `scale(${scale})`,
          textAlign: "center",
        }}
      >
        <div style={{ fontSize: 140, marginBottom: 12 }}>🇪🇺</div>
        <div
          style={{
            fontFamily: FONT_DISPLAY,
            fontWeight: 700,
            fontSize: 108,
            color: COLORS.ink,
            letterSpacing: "-0.04em",
            lineHeight: 1,
            marginBottom: 18,
          }}
        >
          EU Grant Matcher
        </div>
        <div
          style={{
            color: COLORS.accentStrong,
            fontSize: 30,
            fontWeight: 600,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
          }}
        >
          Open source · MIT licensed
        </div>
      </div>
    </AbsoluteFill>
  );
};
