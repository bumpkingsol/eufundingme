import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, FONT_DISPLAY } from "../constants";
import { AppLayout, Hero } from "../mock/AppLayout";
import { InputPanel } from "../mock/InputPanel";
import { StatusPanel } from "../mock/StatusPanel";
import { ResultCard, type Result } from "../mock/ResultCard";

const TYPED =
  "OpenAI builds advanced AI safety systems for enterprise deployment across Europe. We partner with regulators on trustworthy deployment, and have offices in Dublin and Munich.";

const RESULTS: Result[] = [
  {
    score: 92,
    callPrefix: "HORIZON-CL4-2025-DIGITAL",
    title: "Trustworthy AI for industrial deployment",
    why: "Scope aligns with Horizon Europe's Cluster 4 — Digital, Industry & Space. Enterprise safety tooling and EU-wide deployment map directly onto the call's priorities.",
    highlight: "Cluster 4 — Digital, Industry & Space",
    budget: "€60M budget",
    deadline: "Deadline 2025-09-18",
    keywords: ["Trustworthy AI", "Industrial", "Deployment"],
  },
  {
    score: 87,
    callPrefix: "HORIZON-EIC-2025-ACCEL",
    title: "EIC Accelerator — deep-tech scaleups",
    why: "Fits growth-stage AI companies scaling safety tooling across EU member states, with a clear commercialisation path.",
    highlight: "growth-stage AI companies",
    budget: "€17.5M / company",
    deadline: "Deadline 2025-10-08",
    keywords: ["Deep tech", "Scale-up", "Commercialisation"],
  },
  {
    score: 81,
    callPrefix: "DIGITAL-ECCC-2025-AI",
    title: "Deploy trustworthy AI in the public sector",
    why: "Safety tooling maps directly onto deployment requirements for public-sector AI, emphasising oversight and auditability.",
    highlight: "Safety tooling",
    budget: "€45M budget",
    deadline: "Deadline 2025-11-04",
    keywords: ["Public sector", "Oversight", "Auditable"],
  },
];

export const Demo: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Typing: 0.3s .. 3.6s
  const typedChars = Math.min(
    TYPED.length,
    Math.floor(
      interpolate(frame, [fps * 0.3, fps * 3.6], [0, TYPED.length], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      }),
    ),
  );

  // Panel-scale entrance
  const enterScale = interpolate(frame, [0, fps * 0.6], [0.98, 1], {
    extrapolateRight: "clamp",
  });
  const enterOpacity = interpolate(frame, [0, fps * 0.5], [0, 1], {
    extrapolateRight: "clamp",
  });

  // After ~6s, camera pans down to results (the hero section is pushed out)
  const panStart = fps * 8;
  const panDuration = fps * 1.2;
  const pan = interpolate(
    frame,
    [panStart, panStart + panDuration],
    [0, -820],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  const submitting = frame >= fps * 5 && frame < fps * 8;

  // Results start revealing after the pan
  const resultsStart = panStart + fps * 0.6;

  return (
    <AbsoluteFill style={{ background: COLORS.bg }}>
      <AbsoluteFill
        style={{
          opacity: enterOpacity,
          transform: `scale(${enterScale})`,
          transformOrigin: "50% 20%",
        }}
      >
        <div style={{ transform: `translateY(${pan}px)` }}>
          <AppLayout>
            <Hero />

            {/* Workspace: two-column */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1.7fr 0.9fr",
                gap: 20,
                marginBottom: 28,
              }}
            >
              <InputPanel
                typedChars={typedChars}
                full={TYPED}
                submitting={submitting}
              />
              <StatusPanel grantCountTarget={247} />
            </div>

            {/* Results shell */}
            <section
              style={{
                background: COLORS.paper,
                border: `1px solid rgba(255, 255, 255, 0.6)`,
                boxShadow: COLORS.shadow,
                borderRadius: 28,
                padding: 28,
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "end",
                  justifyContent: "space-between",
                  marginBottom: 22,
                }}
              >
                <div>
                  <div
                    style={{
                      color: COLORS.accentStrong,
                      fontSize: 14,
                      fontWeight: 600,
                      letterSpacing: "0.14em",
                      textTransform: "uppercase",
                      marginBottom: 8,
                    }}
                  >
                    Ranked Results
                  </div>
                  <h2
                    style={{
                      margin: 0,
                      fontFamily: FONT_DISPLAY,
                      fontWeight: 700,
                      fontSize: 36,
                      letterSpacing: "-0.04em",
                      color: COLORS.ink,
                    }}
                  >
                    Best-fitting live programmes
                  </h2>
                </div>
                <div style={{ color: COLORS.muted, fontSize: 16 }}>
                  {frame >= resultsStart
                    ? `3 matches · ranked by fit`
                    : "Running match…"}
                </div>
              </div>

              {frame >= resultsStart
                ? RESULTS.map((r, i) => (
                    <ResultCard
                      key={r.callPrefix}
                      result={r}
                      startFrame={resultsStart + i * 10}
                    />
                  ))
                : null}
            </section>
          </AppLayout>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
