/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        dark: {
          950: "#050609",
          900: "#0c0e17",
          800: "#171a2e",
          700: "#222644",
          600: "#2e335b",
          500: "#434b84",
        },
        primary: {
          400: "#818cf8",
          500: "#6366f1",
          600: "#4f46e5",
          700: "#4338ca",
        },
        accent: {
          cyan: "#22d3ee",
          purple: "#c084fc",
          pink: "#f472b6",
        }
      }
    },
  },
  plugins: [],
}
