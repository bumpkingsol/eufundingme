import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, FONT_BODY, FONT_DISPLAY } from "../constants";

const GRANT_TITLES = [
  "HORIZON-CL4-2024-DIGITAL-EMERGING",
  "HORIZON-CL5-2024-D4-01",
  "HORIZON-EIC-2024-ACCELERATOR",
  "HORIZON-CL3-2024-CS-ESS",
  "DIGITAL-ECCC-2024-DEPLOY-AI",
  "LIFE-2024-SAP-CLIMA",
  "CREA-CROSS-2024-INNOVLAB",
  "ERASMUS-EDU-2024-PCOOP-ENGO",
  "HORIZON-CL6-2024-FARM2FORK",
  "CEF-T-2024-GENCALL",
  "HORIZON-HLTH-2024-IND-06",
  "HORIZON-MISS-2024-CLIMA",
];

const Card: React.FC<{ title: string; deadline: string }> = ({ title, deadline }) => {
  return (
    <div
      style={{
        background: COLORS.paperSolid,
        border: `1px solid ${COLORS.line}`,
        borderRadius: 16,
        padding: "16px 20px",
        marginBottom: 14,
        color: COLORS.ink,
        fontSize: 18,
        fontFamily: FONT_BODY,
        boxShadow: "0 10px 30px rgba(56, 43, 24, 0.08)",
      }}
    >
      <div
        style={{
          color: COLORS.accentStrong,
          fontSize: 12,
          letterSpacing: "0.12em",
          textTransform: "uppercase",
          marginBottom: 6,
          fontWeight: 600,
        }}
      >
        Call · EU
      </div>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>{title}</div>
      <div style={{ color: COLORS.muted, fontSize: 14 }}>Deadline {deadline}</div>
    </div>
  );
};

const ScrollColumn: React.FC<{ speed: number; offset: number; items: string[] }> = ({
  speed,
  offset,
  items,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const y = interpolate(frame, [0, fps * 8], [0, -speed]) + offset;
  return (
    <div
      style={{
        flex: 1,
        transform: `translateY(${y}px)`,
        padding: "0 14px",
      }}
    >
      {[...items, ...items].map((t, i) => (
        <Card
          key={i}
          title={t}
          deadline={`2025-${String(((i * 3) % 12) + 1).padStart(2, "0")}-${String(((i * 7) % 28) + 1).padStart(2, "0")}`}
        />
      ))}
    </div>
  );
};

export const Problem: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const overlayOpacity = interpolate(frame, [fps * 0.4, fps * 1.2], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        background: `linear-gradient(180deg, ${COLORS.bgSoft} 0%, ${COLORS.bg} 100%)`,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          filter: "blur(1.5px)",
          opacity: 0.45,
        }}
      >
        <ScrollColumn speed={1200} offset={-200} items={GRANT_TITLES} />
        <ScrollColumn speed={900} offset={-600} items={GRANT_TITLES.slice().reverse()} />
        <ScrollColumn speed={1400} offset={-100} items={GRANT_TITLES.slice(3)} />
        <ScrollColumn
          speed={1050}
          offset={-800}
          items={GRANT_TITLES.slice(2).concat(GRANT_TITLES.slice(0, 2))}
        />
      </div>

      <AbsoluteFill
        style={{
          background:
            "radial-gradient(circle at center, rgba(244, 241, 232, 0) 0%, rgba(244, 241, 232, 0.85) 55%, rgba(244, 241, 232, 0.98) 100%)",
        }}
      />

      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          opacity: overlayOpacity,
        }}
      >
        <div
          style={{
            textAlign: "center",
            color: COLORS.ink,
            fontFamily: FONT_DISPLAY,
            fontSize: 80,
            fontWeight: 700,
            letterSpacing: "-0.04em",
            lineHeight: 1.1,
          }}
        >
          Thousands of calls.
          <br />
          Scattered portals.
          <br />
          <span style={{ color: COLORS.warm }}>Hours of filtering.</span>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
