// tailwind.config.js (ESM)

export default {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#F0F7F2",
          100: "#E1EFE5",
          200: "#CDE5D4",
          300: "#ABCEB6",
          400: "#87B095",
          500: "#5D8D6E",
          600: "#427053",
          700: "#2A583C",
          800: "#19442B",
          900: "#09311C",
          950: "#00220F",
        },
        surface: "#fafaf9",
        ink: {
          900: "#0f172a",
          700: "#475569",
          500: "#64748b",
        },
        accent: {
          DEFAULT: "#86efac",
          hover: "#4ade80",
          active: "#22c55e",
        },
        border: "#e7e5e4",
        ring: "#34d399",
      },
    },
  },
  plugins: [],
};
