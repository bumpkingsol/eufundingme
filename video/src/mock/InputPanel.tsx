import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS } from "../constants";
import { Panel, PanelHead } from "./Panel";

export const InputPanel: React.FC<{
  typedChars: number;
  full: string;
  submitting: boolean;
}> = ({ typedChars, full, submitting }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const visible = full.slice(0, typedChars);
  const cursorOn = Math.floor(frame / (fps / 2)) % 2 === 0;

  return (
    <Panel>
      <PanelHead
        title="Company Profile"
        subtitle="Describe the company, product, market, and strategic focus."
      />

      {/* Quick fill row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 18,
          padding: "16px 18px",
          border: `1px solid ${COLORS.line}`,
          borderRadius: 20,
          background: "rgba(255, 255, 255, 0.52)",
          marginBottom: 16,
        }}
      >
        <button
          style={{
            padding: "10px 18px",
            borderRadius: 999,
            background: "rgba(255, 252, 247, 0.88)",
            color: COLORS.ink,
            border: `1px solid rgba(29, 27, 24, 0.12)`,
            fontWeight: 600,
            fontSize: 16,
          }}
        >
          Try OpenAI
        </button>
        <div style={{ color: COLORS.muted, fontSize: 16, lineHeight: 1.55 }}>
          One click loads the demo profile, or type a company name like{" "}
          <code
            style={{
              background: "rgba(0,109,91,0.08)",
              padding: "2px 8px",
              borderRadius: 6,
              fontFamily: "IBM Plex Mono, monospace",
              fontSize: 15,
            }}
          >
            OpenAI
          </code>{" "}
          and we auto-expand it.
        </div>
      </div>

      {/* Textarea */}
      <div
        style={{
          minHeight: 220,
          background: "rgba(255, 255, 255, 0.6)",
          border: `1px solid ${COLORS.line}`,
          borderRadius: 20,
          padding: "20px 22px",
          fontSize: 22,
          lineHeight: 1.6,
          color: COLORS.ink,
        }}
      >
        {typedChars === 0 ? (
          <span style={{ color: COLORS.muted }}>
            We build advanced AI safety systems for enterprise deployment across Europe...
            <span
              style={{
                display: "inline-block",
                width: 2,
                height: 24,
                background: COLORS.accent,
                marginLeft: 2,
                verticalAlign: "middle",
                opacity: cursorOn ? 1 : 0,
              }}
            />
          </span>
        ) : (
          <>
            {visible}
            <span
              style={{
                display: "inline-block",
                width: 2,
                height: 24,
                background: COLORS.accent,
                marginLeft: 2,
                verticalAlign: "middle",
                opacity: cursorOn ? 1 : 0,
              }}
            />
          </>
        )}
      </div>

      {/* Submit row */}
      <div
        style={{
          marginTop: 18,
          display: "flex",
          alignItems: "center",
          gap: 18,
        }}
      >
        <button
          style={{
            padding: "16px 30px",
            borderRadius: 999,
            background: `linear-gradient(135deg, ${COLORS.accent} 0%, #008e74 100%)`,
            color: "white",
            border: "none",
            fontWeight: 600,
            fontSize: 18,
            boxShadow: `0 14px 28px rgba(0, 109, 91, 0.22)`,
            letterSpacing: "0.01em",
            opacity: submitting ? 0.9 : 1,
          }}
        >
          {submitting ? "Finding…" : "Find Grants"}
        </button>
        <div style={{ color: COLORS.muted, fontSize: 16, lineHeight: 1.55, flex: 1 }}>
          Live indexing starts on page load. First load can take a short while; watch the
          status panel while matching unlocks.
        </div>
      </div>
    </Panel>
  );
};
