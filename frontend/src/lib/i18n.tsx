import { createContext, useContext, useState, type ReactNode } from "react";

const de = {
  "app.title": "DocuWaves",
  "app.tagline": "Selbst-gehostete Dokumentation für all eure Projekte",
  "setup.title": "Ersteinrichtung",
  "setup.subtitle": "Lege den ersten Admin-Zugang an.",
  "setup.username": "Benutzername",
  "setup.password": "Passwort",
  "setup.submit": "Einrichten",
  "login.title": "Anmelden",
  "login.username": "Benutzername",
  "login.password": "Passwort",
  "login.submit": "Anmelden",
  "login.orDivider": "oder",
  "login.oidcPrefix": "Mit ",
  "login.oidcSuffix": " anmelden",
  "login.failed": "Benutzername oder Passwort falsch.",
  "login.oidcFailed": "SSO-Anmeldung fehlgeschlagen.",
  "login.oidcNoAccount": "Kein passendes Konto für diese SSO-Identität gefunden.",
  "nav.admin": "Verwaltung",
  "nav.logout": "Abmelden",
  "nav.search": "Suchen…",
  "nav.public": "Zur Website",
  "home.title": "Dokumentation",
  "home.subtitle": "Wähle ein Projekt, um seine Doku zu öffnen.",
  "home.empty": "Noch keine Projekte veröffentlicht.",
  "project.categories": "Kategorien",
  "project.empty": "Für dieses Projekt gibt es noch keine veröffentlichten Inhalte.",
  "category.pages": "Seiten",
  "search.title": "Suchergebnisse",
  "search.placeholder": "Doku durchsuchen…",
  "search.empty": "Keine Treffer.",
  "search.resultsFor": "Ergebnisse für",
  "admin.projects": "Projekte",
  "admin.newProject": "Neues Projekt",
  "admin.projectName": "Name",
  "admin.projectIcon": "Icon (Emoji)",
  "admin.projectColor": "Farbe",
  "admin.projectDescription": "Beschreibung",
  "admin.save": "Speichern",
  "admin.cancel": "Abbrechen",
  "admin.delete": "Löschen",
  "admin.deleteConfirm": "Wirklich löschen? Das kann nicht rückgängig gemacht werden.",
  "admin.categories": "Kategorien",
  "admin.newCategory": "Neue Kategorie",
  "admin.categoryName": "Name",
  "admin.categoryIcon": "Icon (Emoji)",
  "admin.pages": "Seiten",
  "admin.newPage": "Neue Seite",
  "admin.pageTitle": "Titel",
  "admin.published": "Veröffentlicht",
  "admin.draft": "Entwurf",
  "admin.editPage": "Seite bearbeiten",
  "admin.editorTab": "Markdown",
  "admin.previewTab": "Vorschau",
  "admin.moveUp": "Nach oben",
  "admin.moveDown": "Nach unten",
  "admin.selectProject": "Wähle links ein Projekt.",
  "admin.selectCategory": "Wähle eine Kategorie, um ihre Seiten zu sehen.",
  "admin.account": "Konto",
  "admin.currentPassword": "Aktuelles Passwort",
  "admin.newPassword": "Neues Passwort",
  "admin.changePassword": "Passwort ändern",
  "admin.passwordChanged": "Passwort geändert.",
  "common.loading": "Lädt…",
  "common.error": "Etwas ist schiefgelaufen.",
  "common.back": "Zurück",
};

type Dict = typeof de;

const en: Dict = {
  "app.title": "DocuWaves",
  "app.tagline": "Self-hosted documentation for all your projects",
  "setup.title": "First-run setup",
  "setup.subtitle": "Create the first admin account.",
  "setup.username": "Username",
  "setup.password": "Password",
  "setup.submit": "Set up",
  "login.title": "Sign in",
  "login.username": "Username",
  "login.password": "Password",
  "login.submit": "Sign in",
  "login.orDivider": "or",
  "login.oidcPrefix": "Sign in with ",
  "login.oidcSuffix": "",
  "login.failed": "Incorrect username or password.",
  "login.oidcFailed": "SSO login failed.",
  "login.oidcNoAccount": "No matching account for this SSO identity.",
  "nav.admin": "Admin",
  "nav.logout": "Log out",
  "nav.search": "Search…",
  "nav.public": "View site",
  "home.title": "Documentation",
  "home.subtitle": "Choose a project to open its docs.",
  "home.empty": "No projects published yet.",
  "project.categories": "Categories",
  "project.empty": "This project has no published content yet.",
  "category.pages": "Pages",
  "search.title": "Search results",
  "search.placeholder": "Search the docs…",
  "search.empty": "No matches.",
  "search.resultsFor": "Results for",
  "admin.projects": "Projects",
  "admin.newProject": "New project",
  "admin.projectName": "Name",
  "admin.projectIcon": "Icon (emoji)",
  "admin.projectColor": "Color",
  "admin.projectDescription": "Description",
  "admin.save": "Save",
  "admin.cancel": "Cancel",
  "admin.delete": "Delete",
  "admin.deleteConfirm": "Really delete this? This can't be undone.",
  "admin.categories": "Categories",
  "admin.newCategory": "New category",
  "admin.categoryName": "Name",
  "admin.categoryIcon": "Icon (emoji)",
  "admin.pages": "Pages",
  "admin.newPage": "New page",
  "admin.pageTitle": "Title",
  "admin.published": "Published",
  "admin.draft": "Draft",
  "admin.editPage": "Edit page",
  "admin.editorTab": "Markdown",
  "admin.previewTab": "Preview",
  "admin.moveUp": "Move up",
  "admin.moveDown": "Move down",
  "admin.selectProject": "Select a project on the left.",
  "admin.selectCategory": "Select a category to see its pages.",
  "admin.account": "Account",
  "admin.currentPassword": "Current password",
  "admin.newPassword": "New password",
  "admin.changePassword": "Change password",
  "admin.passwordChanged": "Password changed.",
  "common.loading": "Loading…",
  "common.error": "Something went wrong.",
  "common.back": "Back",
};

const dictionaries: Record<string, Dict> = { de, en };

type Lang = "de" | "en";

const I18nContext = createContext<{ lang: Lang; setLang: (l: Lang) => void; t: (key: keyof Dict) => string }>({
  lang: "en",
  setLang: () => {},
  t: (key) => key,
});

function detectDefaultLang(): Lang {
  const stored = localStorage.getItem("docuwaves-lang");
  if (stored === "de" || stored === "en") return stored;
  return navigator.language.startsWith("de") ? "de" : "en";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(detectDefaultLang());

  function setLang(l: Lang) {
    setLangState(l);
    localStorage.setItem("docuwaves-lang", l);
  }

  function t(key: keyof Dict): string {
    return dictionaries[lang][key] ?? dictionaries.en[key] ?? key;
  }

  return <I18nContext.Provider value={{ lang, setLang, t }}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  return useContext(I18nContext);
}
