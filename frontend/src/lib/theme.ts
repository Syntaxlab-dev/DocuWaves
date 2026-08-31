export function getPreferredTheme(): "light" | "dark" {
  const stored = localStorage.getItem("docuwaves-theme");
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(theme: "light" | "dark") {
  document.documentElement.classList.toggle("dark", theme === "dark");
  localStorage.setItem("docuwaves-theme", theme);
}
