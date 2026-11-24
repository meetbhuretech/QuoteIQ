/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: "#0B1F3A",
        ink: "#122033",
        mist: "#5C6B7A",
        line: "#E2E8F0",
        paper: "#F3F5F8",
        accent: "#1F4E79",
      },
      fontFamily: { sans: ["var(--font-sans)", "ui-sans-serif", "system-ui"] },
    },
  },
  plugins: [],
};
