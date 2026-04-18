import { COLORS, FONT_DISPLAY } from "../constants";

export const Panel: React.FC<{
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ children, style }) => {
  return (
    <div
      style={{
        background: COLORS.paper,
        border: `1px solid rgba(255, 255, 255, 0.6)`,
        boxShadow: COLORS.shadow,
        borderRadius: 28,
        padding: 28,
        ...style,
      }}
    >
      {children}
    </div>
  );
};

export const PanelHead: React.FC<{
  title: string;
  subtitle?: string;
}> = ({ title, subtitle }) => {
  return (
    <div style={{ marginBottom: 18 }}>
      <h2
        style={{
          margin: 0,
          fontFamily: FONT_DISPLAY,
          fontWeight: 700,
          fontSize: 30,
          letterSpacing: "-0.04em",
          color: COLORS.ink,
        }}
      >
        {title}
      </h2>
      {subtitle ? (
        <p
          style={{
            margin: "6px 0 0",
            color: COLORS.muted,
            fontSize: 18,
            lineHeight: 1.55,
          }}
        >
          {subtitle}
        </p>
      ) : null}
    </div>
  );
};
