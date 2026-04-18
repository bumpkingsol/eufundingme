import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, FONT_DISPLAY } from "../constants";
import { Panel, PanelHead } from "./Panel";

const Stat: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => {
  return (
    <div
      style={{
        padding: 16,
        borderRadius: 14,
        background: "rgba(255, 255, 255, 0.56)",
        border: `1px solid ${COLORS.line}`,
      }}
    >
      <div
        style={{
          color: COLORS.muted,
          fontSize: 14,
          fontWeight: 500,
          marginBottom: 4,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontFamily: FONT_DISPLAY,
          fontWeight: 500,
          fontSize: 18,
          color: COLORS.ink,
        }}
      >
        {value}
      </div>
    </div>
  );
};

export const StatusPanel: React.FC<{ grantCountTarget: number }> = ({
  grantCountTarget,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const progress = interpolate(frame, [0, fps * 2.5], [0.08, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const grantCount = Math.round(
    interpolate(frame, [0, fps * 2.5], [0, grantCountTarget], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }),
  );

  // Sheen
  const sheenX = interpolate(frame % (fps * 2.4), [0, fps * 2.4], [-100, 160]);

  return (
    <Panel>
      <PanelHead
        title="Live Index Status"
        subtitle="Running with cached data while the live refresh catches up."
      />

      <div
        style={{
          position: "relative",
          height: 13,
          borderRadius: 999,
          background: "rgba(29, 27, 24, 0.08)",
          overflow: "hidden",
          marginBottom: 18,
        }}
      >
        <div
          style={{
            width: `${progress * 100}%`,
            height: "100%",
            borderRadius: 999,
            background: `linear-gradient(90deg, ${COLORS.warm}, ${COLORS.accent})`,
          }}
        />
        <div
          style={{
            position: "absolute",
            top: 0,
            bottom: 0,
            left: 0,
            width: "100%",
            background:
              "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.4) 48%, transparent 100%)",
            transform: `translateX(${sheenX}%)`,
          }}
        />
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 12,
        }}
      >
        <Stat
          label="Phase"
          value={<span style={{ color: COLORS.successInk }}>ready_degraded</span>}
        />
        <Stat label="Grants" value={grantCount} />
        <Stat label="Prefixes" value={`${Math.min(48, Math.round(progress * 48))} / 48`} />
        <Stat label="Failures" value="0" />
        <Stat label="Coverage" value="partial" />
        <Stat label="Embeddings" value="keyword-only" />
        <Stat
          label="Source"
          value={<span>bundled snapshot (18h old)</span>}
        />
        <Stat
          label="Refresh"
          value={<span style={{ color: COLORS.warm }}>refreshing in background</span>}
        />
      </div>
    </Panel>
  );
};
