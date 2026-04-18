import { AbsoluteFill } from "remotion";

export const Ambient: React.FC = () => {
  return (
    <AbsoluteFill style={{ pointerEvents: "none", overflow: "hidden" }}>
      {/* warm orange orb, top-left */}
      <div
        style={{
          position: "absolute",
          top: -180,
          left: -220,
          width: 720,
          height: 720,
          borderRadius: "50%",
          background: "rgba(201, 106, 43, 0.28)",
          filter: "blur(70px)",
          opacity: 0.6,
        }}
      />
      {/* green orb, top-right */}
      <div
        style={{
          position: "absolute",
          top: 120,
          right: -260,
          width: 780,
          height: 780,
          borderRadius: "50%",
          background: "rgba(0, 109, 91, 0.28)",
          filter: "blur(70px)",
          opacity: 0.55,
        }}
      />
    </AbsoluteFill>
  );
};
