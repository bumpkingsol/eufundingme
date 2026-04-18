import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, FONT_DISPLAY } from "../constants";

export type Result = {
  score: number;
  callPrefix: string;
  title: string;
  why: string;
  highlight?: string;
  budget: string;
  deadline: string;
  keywords: string[];
};

export const scoreTier = (score: number): "high" | "medium" | "low" => {
  if (score >= 80) return "high";
  if (score >= 60) return "medium";
  return "low";
};

const scoreStyles = (score: number) => {
  const tier = scoreTier(score);
  if (tier === "high") return { bg: COLORS.successBg, fg: COLORS.successInk };
  if (tier === "medium") return { bg: COLORS.warningBg, fg: COLORS.warningInk };
  return { bg: COLORS.accentSoft, fg: COLORS.accentStrong };
};

export const ResultCard: React.FC<{
  result: Result;
  startFrame: number;
}> = ({ result, startFrame }) => {
  const frame = useCurrentFrame() - startFrame;
  const { fps } = useVideoConfig();

  const s = spring({
    frame,
    fps,
    config: { damping: 200 },
  });
  const opacity = interpolate(s, [0, 1], [0, 1]);
  const y = interpolate(s, [0, 1], [16, 0]);

  const scoreT = interpolate(frame, [fps * 0.2, fps * 1.0], [0, result.score], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const scoreValue = Math.round(scoreT);
  const scoreColor = scoreStyles(result.score);

  const parts = result.highlight ? result.why.split(result.highlight) : [result.why];

  return (
    <div
      style={{
        opacity,
        transform: `translateY(${y}px)`,
        background: COLORS.paper,
        border: `1px solid rgba(255, 255, 255, 0.6)`,
        boxShadow: COLORS.shadow,
        borderRadius: 20,
        padding: 24,
        marginBottom: 14,
      }}
    >
      <div
        style={{
          display: "flex",
          gap: 20,
          justifyContent: "space-between",
          alignItems: "flex-start",
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3
            style={{
              margin: 0,
              fontFamily: FONT_DISPLAY,
              fontWeight: 700,
              fontSize: 26,
              letterSpacing: "-0.03em",
              lineHeight: 1.15,
              color: COLORS.ink,
            }}
          >
            {result.title}
          </h3>
          <div
            style={{
              marginTop: 10,
              display: "flex",
              flexWrap: "wrap",
              gap: 10,
            }}
          >
            <MetaPill>{result.callPrefix}</MetaPill>
            <MetaPill>{result.budget}</MetaPill>
            <MetaPill>{result.deadline}</MetaPill>
          </div>
        </div>

        <div style={{ display: "grid", justifyItems: "end", gap: 8 }}>
          <div
            style={{
              color: COLORS.muted,
              fontSize: 12,
              fontWeight: 600,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
            }}
          >
            Match Score
          </div>
          <div
            style={{
              minWidth: 92,
              textAlign: "center",
              padding: "10px 18px",
              borderRadius: 999,
              background: scoreColor.bg,
              color: scoreColor.fg,
              fontFamily: FONT_DISPLAY,
              fontWeight: 700,
              fontSize: 20,
              letterSpacing: "-0.02em",
            }}
          >
            {scoreValue}
          </div>
        </div>
      </div>

      <div
        style={{
          marginTop: 18,
          borderLeft: `3px solid rgba(0, 109, 91, 0.28)`,
          paddingLeft: 16,
        }}
      >
        <div
          style={{
            color: COLORS.ink,
            fontWeight: 600,
            fontSize: 16,
            marginBottom: 4,
          }}
        >
          Why this matches
        </div>
        <div style={{ color: COLORS.muted, fontSize: 17, lineHeight: 1.5 }}>
          {parts.map((p, i) => (
            <span key={i}>
              {p}
              {i < parts.length - 1 && result.highlight ? (
                <span
                  style={{
                    color: COLORS.ink,
                    background: `${COLORS.accentSoft}`,
                    padding: "2px 6px",
                    borderRadius: 4,
                    fontWeight: 600,
                  }}
                >
                  {result.highlight}
                </span>
              ) : null}
            </span>
          ))}
        </div>
      </div>

      <div
        style={{
          marginTop: 16,
          display: "flex",
          flexWrap: "wrap",
          gap: 8,
        }}
      >
        {result.keywords.map((k) => (
          <div
            key={k}
            style={{
              padding: "6px 12px",
              borderRadius: 999,
              background: "rgba(0, 109, 91, 0.08)",
              border: `1px solid ${COLORS.line}`,
              color: COLORS.ink,
              fontSize: 14,
            }}
          >
            {k}
          </div>
        ))}
      </div>
    </div>
  );
};

const MetaPill: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <div
      style={{
        padding: "6px 12px",
        borderRadius: 999,
        border: `1px solid ${COLORS.line}`,
        background: "rgba(255, 255, 255, 0.62)",
        color: COLORS.ink,
        fontSize: 14,
      }}
    >
      {children}
    </div>
  );
};
