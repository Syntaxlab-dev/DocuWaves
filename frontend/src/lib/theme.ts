export function getPreferredTheme(): "light" | "dark" {
  const stored = localStorage.getItem("claritydocs-theme");
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(theme: "light" | "dark") {
  document.documentElement.classList.toggle("dark", theme === "dark");
  localStorage.setItem("claritydocs-theme", theme);
}
