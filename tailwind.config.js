// tailwind 3.4 config for web/static/app.css; rebuild with the standalone cli (see README, "Changing the styles")
module.exports = {
  // class names in the page's markup and in its script (the language switch toggles some at runtime)
  content: ["./web/static/index.html"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Segoe UI Variable"', '"Segoe UI"', "-apple-system", "BlinkMacSystemFont", "Roboto", "sans-serif"],
        mono: ['"Cascadia Mono"', "Consolas", "ui-monospace", "monospace"],
      },
      colors: {
        apple: {
          subtle: "rgba(255, 255, 255, 0.45)",
          card: "rgba(255, 255, 255, 0.65)",
          darkCard: "rgba(15, 23, 42, 0.6)",
          accent: "#0071E3",
          accentHover: "#0077ED",
        },
      },
      boxShadow: {
        "apple-glass": "0 20px 50px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(255, 255, 255, 0.8) inset",
        "bubble-user": "0 8px 20px -4px rgba(0, 113, 227, 0.35)",
        "bubble-ai": "0 4px 20px -2px rgba(0, 0, 0, 0.04), 0 1px 1px rgba(255, 255, 255, 0.9) inset",
      },
    },
  },
};
