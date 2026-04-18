import { Ambient } from "../components/Ambient";
import { COLORS, FONT_BODY, FONT_DISPLAY } from "../constants";

/**
 * A 1920x1080 replica of the real app's layout — no browser chrome.
 * Matches the classes in frontend/styles.css: .page-shell .layout .hero .workspace .results-shell
 */
export const AppLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <div
      style={{
        width: 1920,
        minHeight: 1080,
        background: `
          radial-gradient(circle at top left, rgba(201, 106, 43, 0.18), transparent 34%),
          radial-gradient(circle at top right, rgba(0, 109, 91, 0.18), transparent 32%),
          linear-gradient(180deg, ${COLORS.bgSoft} 0%, ${COLORS.bg} 100%)
        `,
        position: "relative",
        fontFamily: FONT_BODY,
        color: COLORS.ink,
      }}
    >
      <Ambient />
      <div
        style={{
          position: "relative",
          zIndex: 1,
          width: 1460,
          margin: "0 auto",
          padding: "56px 0 40px",
        }}
      >
        {children}
      </div>
    </div>
  );
};

export const Hero: React.FC = () => {
  return (
    <section style={{ maxWidth: 900, marginBottom: 36 }}>
      <div
        style={{
          color: COLORS.accentStrong,
          fontSize: 16,
          fontWeight: 600,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          marginBottom: 14,
        }}
      >
        Open Source Project
      </div>
      <h1
        style={{
          margin: 0,
          fontFamily: FONT_DISPLAY,
          fontWeight: 700,
          fontSize: 96,
          lineHeight: 0.94,
          letterSpacing: "-0.04em",
          color: COLORS.ink,
          maxWidth: 11.5 + "ch",
        }}
      >
        Find EU funding for your company in 30 seconds.
      </h1>
    </section>
  );
};
