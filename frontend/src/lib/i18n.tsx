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
  "nav.contents": "Inhalt",
  "nav.language": "Sprache",
  "page.onThisPage": "Auf dieser Seite",
  "page.pageNav": "Seitennavigation",
  "page.previous": "Vorherige Seite",
  "page.next": "Nächste Seite",
  "page.headingAnchor": "Link zu diesem Abschnitt",
  "page.copyCode": "Code kopieren",
  "page.copied": "Kopiert",
  "page.copyFailed": "Kopieren fehlgeschlagen",
  "page.diagramRendering": "Diagramm wird gezeichnet…",
  "page.diagramFailed": "Dieses Diagramm konnte nicht gezeichnet werden — bitte die Mermaid-Syntax prüfen.",
  "page.notTranslatedPrefix": "Diese Seite ist noch nicht übersetzt — angezeigt wird die Fassung auf ",
  "page.notTranslatedSuffix": ".",
  "page.fallbackBadge": "Nur auf ",
  "page.fallbackBadgeSuffix": " verfügbar",
  "page.lastUpdated": "Zuletzt aktualisiert:",
  "notFound.title": "Seite nicht gefunden",
  "notFound.body":
    "Zu dieser Adresse gibt es keine veröffentlichte Seite. Möglicherweise wurde sie umbenannt, entfernt — oder sie ist noch ein Entwurf.",
  "notFound.home": "Zur Startseite",
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
  "search.language": "Sprache",
  "admin.projects": "Projekte",
  "admin.newProject": "Neues Projekt",
  "admin.projectName": "Name",
  "admin.projectIcon": "Icon (Emoji)",
  "admin.projectColor": "Farbe",
  "admin.projectDescription": "Beschreibung",
  "admin.save": "Speichern",
  "admin.cancel": "Abbrechen",
  "admin.edit": "Bearbeiten",
  "admin.delete": "Löschen",
  "admin.deleteConfirm": "Wirklich löschen? Das kann nicht rückgängig gemacht werden.",
    "admin.discardDraftConfirm": "Ungespeicherte Änderungen an dieser Sprache gehen verloren. Wechseln?",
  "admin.switchLanguageDraftKept":
    "Ungespeicherte Änderungen an dieser Sprache werden als Entwurf in diesem Browser behalten und beim Zurückwechseln wieder angeboten — im Content-Repo steht weiter die zuletzt gespeicherte Fassung. Jetzt wechseln?",
  "admin.cover": "Titelbild (optional)",
  "admin.coverNone": "Keins",
  "admin.coverUpload": "Titelbild hochladen",
  "admin.coverRemove": "Titelbild entfernen",
  "admin.coverSaveFirst": "Erst speichern — Bilder liegen im Ordner des Projekts, den es dann gibt.",
  "admin.categories": "Kategorien",
  "admin.newCategory": "Neue Kategorie",
  "admin.categoryName": "Name",
  "admin.categoryIcon": "Icon (Emoji)",
  "admin.pages": "Seiten",
  "admin.newPage": "Neue Seite",
  "admin.pageTitle": "Titel",
  "admin.pageLanguages": "Sprachen",
  "admin.translationMissing": "Noch nicht übersetzt",
  "admin.createTranslation": "Übersetzung anlegen",
  "admin.saveFirstForTranslations": "Seite zuerst speichern, dann können Übersetzungen angelegt werden.",
  "admin.published": "Veröffentlicht",
  "admin.draft": "Entwurf",
  "admin.editPage": "Seite bearbeiten",
  "admin.editorTab": "Markdown",
  "admin.previewTab": "Vorschau",
  "admin.images": "Bilder",
  "admin.insertImage": "Bild einfügen",
  "admin.uploadingImage": "Wird hochgeladen…",
  "admin.imageUploaded": "Bild hochgeladen und eingefügt.",
  "admin.imagesUploaded": "{count} Bilder hochgeladen und eingefügt.",
  "admin.imagesEmpty": "Noch keine Bilder in diesem Projekt.",
  "admin.imageInsert": "Einfügen",
  "admin.imageDeleteConfirm": "Bild wirklich löschen? Seiten, die es verwenden, zeigen es dann nicht mehr an.",
  "admin.imagePasteHint":
    "Screenshot einfügen (Strg+V) oder Bilddateien hierher ziehen — beides lädt sie ins Projekt hoch und setzt ![](…) an der Cursorposition ein.",
  "admin.imageDropHere": "Bilder hier ablegen",
  "admin.imageUploadProgress": "Bild {n} von {total} wird hochgeladen…",
  "admin.draftFoundTitle": "Ungespeicherter Entwurf gefunden",
  "admin.draftFoundBody":
    "Zuletzt bearbeitet am {when}, aber nie gespeichert. Der Entwurf liegt nur in diesem Browser; angezeigt wird gerade die Fassung aus dem Content-Repo.",
  "admin.draftStaleTitle": "Ungespeicherter Entwurf — aber die Seite hat sich geändert",
  "admin.draftStaleBody":
    "Der Entwurf ist vom {when}. Seitdem wurde diese Seite im Content-Repo geändert — von jemand anderem, oder von dir in einem anderen Browser. Der Entwurf ist also älter als das, was hier steht: Wiederherstellen ersetzt den neueren Text durch deinen älteren Entwurf.",
  "admin.draftRestore": "Entwurf wiederherstellen",
  "admin.draftRestoreAnyway": "Trotzdem wiederherstellen",
  "admin.draftDiscard": "Entwurf verwerfen",
  "admin.draftRestored": "Entwurf wiederhergestellt — noch nicht gespeichert.",
  "admin.draftDiscarded": "Entwurf verworfen.",
  "admin.branding": "Branding",
  "admin.brandingIntro":
    "Name, Logo, Farbe und Fußzeile dieser Instanz. Wird als _site.yml im Content-Repo gespeichert — also versioniert, per Pull Request änderbar und pro Instanz eigenständig.",
  "admin.brandingName": "Seitenname",
  "admin.brandingTagline": "Untertitel (Startseite)",
  "admin.brandingAccent": "Akzentfarbe",
  "admin.brandingAccentReset": "Standardfarbe",
  "admin.brandingLogo": "Logo",
  "admin.brandingLogoDark": "Logo (Dark Mode)",
  "admin.brandingFavicon": "Favicon",
  "admin.brandingUpload": "Hochladen",
  "admin.brandingRemoveImage": "Entfernen",
  "admin.brandingNoImage": "Keins",
  "admin.brandingFooterText": "Fußzeilen-Text",
  "admin.brandingFooterLinks": "Fußzeilen-Links",
  "admin.brandingLinkLabel": "Beschriftung",
  "admin.brandingLinkUrl": "URL (https://…, mailto: oder /pfad)",
  "admin.brandingAddLink": "Link hinzufügen",
  "admin.brandingPreview": "Vorschau",
  "admin.brandingSaved": "Branding gespeichert.",
  "admin.brandingLanguages": "Inhaltssprachen",
  "admin.brandingLanguagesHint":
    "Wird über languages: in _site.yml im Content-Repo festgelegt — die erste Sprache ist die Standardsprache.",
  "admin.brandingLanguagesNone": "Nur eine Sprache (kein languages: in _site.yml)",
  "admin.moveUp": "Nach oben",
  "admin.moveDown": "Nach unten",
  "admin.selectProject": "Wähle links ein Projekt.",
  "admin.selectCategory": "Wähle eine Kategorie, um ihre Seiten zu sehen.",
  "admin.account": "Konto",
  "admin.currentPassword": "Aktuelles Passwort",
  "admin.newPassword": "Neues Passwort",
  "admin.changePassword": "Passwort ändern",
  "admin.passwordChanged": "Passwort geändert.",
  "admin.repoConnected": "Content-Repo verbunden",
  "admin.repoDisconnected": "Content-Repo nicht erreichbar",
  "admin.repoSyncNow": "Jetzt synchronisieren",
  "admin.repoSyncDone": "Synchronisiert.",
  "admin.repoSyncFailed": "Synchronisierung fehlgeschlagen.",
  "admin.repoNotConfiguredTitle": "Kein Content-Repo verbunden",
  "admin.repoNotConfiguredBody":
    "DocuWaves speichert alle Inhalte als Markdown-Dateien in einem separaten Git-Repository. Trage CONTENT_REPO_URL (und CONTENT_REPO_TOKEN oder CONTENT_REPO_SSH_KEY) in der .env-Datei ein und starte den Container neu — siehe README für die genaue Anleitung.",
  "search.scopePrefix": "Nur in: ",
  "version.switcher": "Version",
  "version.oldPrefix": "Du liest die Dokumentation für ",
  "version.oldMiddle": ". Die aktuelle Version ist ",
  "version.oldSuffix": ".",
  "admin.versions": "Versionen",
  "admin.versionsIntro":
    "Eine eingefrorene Version ist eine Momentaufnahme dieser Doku zum Release-Zeitpunkt — ein eigener Ordner im Content-Repo, der sich nie wieder ändert. Sie ist hier bewusst schreibgeschützt: Korrekturen an einer alten Version macht man als Datei-Änderung im Content-Repo (z. B. per Pull Request).",
  "admin.versionCurrent": "Aktuell (wird bearbeitet)",
  "admin.versionFreeze": "Version einfrieren",
  "admin.versionId": "Versions-ID (Ordnername, z. B. v2.0)",
  "admin.versionLabel": "Beschriftung (z. B. 2.0)",
  "admin.versionFreezeConfirmTitle": "Das passiert beim Einfrieren:",
  "admin.versionFreezeStepCopy": "current/ wird Byte für Byte nach {id}/ kopiert und in _versions.yml eingetragen.",
  "admin.versionFreezeStepMove":
    "Erste Version dieses Projekts: die folgenden Ordner/Dateien werden zuerst nach current/ verschoben —",
  "admin.versionFreezeStepAssets":
    "assets/ zieht mit um, weil ein Screenshot zur Version gehört, die er zeigt. Kein Seiten-Markdown wird dabei geändert: ../assets/… stimmt weiterhin.",
  "admin.versionFreezeStepCommit": "Alles zusammen als EIN Commit im Content-Repo.",
  "admin.versionFreezeGo": "Jetzt einfrieren",
  "admin.versionFrozen": "Version eingefroren.",
  "admin.versionReadOnly":
    "Diese Version ist eingefroren und hier schreibgeschützt. Zum Korrigieren die Datei unter content/{project}/{version}/ im Content-Repo bearbeiten.",
  "admin.versionDeleteConfirm":
    "Version {label} wirklich löschen? Damit wird content/{project}/{id}/ mit allen Seiten und Bildern dieser Version aus dem Content-Repo entfernt. Das kann nicht rückgängig gemacht werden (steht aber weiter in der Git-Historie).",
  "admin.versionDeleted": "Version gelöscht.",
  "admin.versionReleased": "Eingefroren am",
  "admin.versionNone": "Noch keine Version eingefroren — dieses Projekt hat keine Versionsebene.",
  "admin.versionViewing": "Angezeigte Version",
  "admin.historyTab": "Verlauf",
  "admin.historyIntro":
    "Jede Seite ist eine Datei im Content-Repo, jedes Speichern ein Commit — das hier ist die echte Git-Historie dieser Datei. Sie gilt nur für die gerade geöffnete Sprachfassung; Übersetzungen sind eigene Dateien mit eigener Historie.",
  "admin.historyEmpty": "Für diese Datei gibt es im Content-Repo noch keine Commits.",
  "admin.historyCreated": "Angelegt",
  "admin.historyRenamedFrom": "Umbenannt von",
  "admin.historyDiff": "Änderung an dieser Datei",
  "admin.historyDiffNone": "Git meldet für diesen Commit keine Änderung an dieser Datei.",
  "admin.historyFirstVersion":
    "Das ist die erste Fassung dieser Datei — es gibt keinen Vorgänger zum Vergleichen, deshalb steht hier die ganze Datei als hinzugefügt.",
  "admin.historyContent": "Markdown dieser Fassung",
  "admin.historyRestore": "Diese Fassung wiederherstellen",
  "admin.historyRestoreConfirm":
    "Fassung {sha} wiederherstellen?\n\nTitel und Markdown-Text dieser Fassung werden als NEUE Version gespeichert — ein zusätzlicher Commit im Content-Repo. Es wird nichts gelöscht und nichts zurückgedreht: die jetzige Fassung und alle älteren bleiben in der Historie stehen, und du kannst genauso wieder zurück.\n\nUnverändert bleiben: die Position der Seite, ob sie veröffentlicht ist, und ihre Adresse (der Slug) — Links auf diese Seite funktionieren also weiter.",
  "admin.historyRestored": "Wiederhergestellt — als neuer Commit im Content-Repo.",
  "admin.historyRestoreFrozen":
    "Diese Version ist eingefroren — hier lässt sich nichts wiederherstellen. Die Historie ist trotzdem vollständig lesbar.",
  "admin.historyNotSavedYet": "Verlauf gibt es, sobald diese Sprachfassung einmal gespeichert wurde.",
  "admin.tokens": "API-Tokens",
  "admin.tokensIntro":
    "Ein API-Token gibt einem KI-Assistenten (z. B. Claude) Zugriff auf diese Doku über den MCP-Endpunkt. Du erstellst das Token hier und gibst es dem Assistenten — es ersetzt keine Anmeldung im Admin-Bereich und kann nichts löschen.",
  "admin.tokensCost":
    "Kosten: DocuWaves ruft selbst kein Sprachmodell auf — die Schnittstelle stellt deine Doku nur bereit und verursacht keine KI-Kosten. Was dein Assistent kostet, richtet sich nach deinem eigenen Zugang: mit einem Abo bleibt es im Rahmen des Abos, über die API rechnet der Anbieter nach Verbrauch ab.",
  "admin.tokensEmpty": "Noch keine API-Tokens angelegt.",
  "admin.tokenName": "Name (z. B. notes-bot)",
  "admin.tokenScope": "Berechtigung",
  "admin.tokenScopeRead": "Nur lesen",
  "admin.tokenScopeWrite": "Lesen und schreiben",
  "admin.tokenScopeReadHint": "Kann die Doku lesen und durchsuchen — auch unveröffentlichte Entwürfe.",
  "admin.tokenScopeWriteHint":
    "ACHTUNG: Wer dieses Token hat, kann die Dokumentation verändern — Seiten anlegen, Texte überschreiben und veröffentlichen. Jede Änderung ist ein Git-Commit im Content-Repo und läuft unter dem Namen dieses Tokens, ist also nachvollziehbar und rückgängig zu machen. Gib es nur weiter, wenn du genau das willst.",
  "admin.tokenExpires": "Läuft ab am (optional)",
  "admin.tokenExpiresHint": "Leer lassen für ein Token ohne Ablaufdatum. Es gilt noch den ganzen angegebenen Tag.",
  "admin.tokenCreate": "Token erstellen",
  "admin.tokenCreated": "Token erstellt.",
  "admin.tokenRevealTitle": "Das ist dein Token — es wird nur dieses eine Mal angezeigt.",
  "admin.tokenRevealBody":
    "Gespeichert wird nur ein Hash, der Wert selbst nirgends. Wenn du ihn verlierst, kannst du ihn nicht nachschlagen, sondern nur ein neues Token anlegen.",
  "admin.tokenCopy": "Kopieren",
  "admin.tokenCopied": "Token kopiert.",
  "admin.tokenCopyFailed": "Kopieren fehlgeschlagen — Wert bitte von Hand markieren.",
  "admin.tokenRevealDone": "Verstanden, ausblenden",
  "admin.tokenLastUsed": "Zuletzt genutzt",
  "admin.tokenNeverUsed": "noch nie genutzt",
  "admin.tokenNoExpiry": "kein Ablaufdatum",
  "admin.tokenExpired": "abgelaufen",
  "admin.tokenExpiresOn": "läuft ab",
  "admin.tokenCreatedOn": "erstellt",
  "admin.tokenRevoke": "Widerrufen",
  "admin.tokenRevokeConfirm":
    "Token „{name}“ wirklich widerrufen? Es funktioniert ab der nächsten Anfrage nicht mehr. Das kann nicht rückgängig gemacht werden.",
  "admin.tokenRevoked": "Token widerrufen.",
  "admin.tokenEndpointTitle": "So verbindest du einen Assistenten",
  "admin.tokenEndpointBody": "URL und Header, die der Assistent braucht:",
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
  "nav.contents": "Contents",
  "nav.language": "Language",
  "page.onThisPage": "On this page",
  "page.pageNav": "Page navigation",
  "page.previous": "Previous",
  "page.next": "Next",
  "page.headingAnchor": "Link to this section",
  "page.copyCode": "Copy code",
  "page.copied": "Copied",
  "page.copyFailed": "Copy failed",
  "page.diagramRendering": "Drawing diagram…",
  "page.diagramFailed": "This diagram could not be drawn -- check the Mermaid syntax.",
  "page.notTranslatedPrefix": "This page has not been translated yet — showing the ",
  "page.notTranslatedSuffix": " version.",
  "page.fallbackBadge": "Only in ",
  "page.fallbackBadgeSuffix": "",
  "page.lastUpdated": "Last updated:",
  "notFound.title": "Page not found",
  "notFound.body":
    "There's no published page at this address. It may have been renamed, removed -- or it's still a draft.",
  "notFound.home": "Back to the homepage",
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
  "search.language": "Language",
  "admin.projects": "Projects",
  "admin.newProject": "New project",
  "admin.projectName": "Name",
  "admin.projectIcon": "Icon (emoji)",
  "admin.projectColor": "Color",
  "admin.projectDescription": "Description",
  "admin.save": "Save",
  "admin.cancel": "Cancel",
  "admin.edit": "Edit",
  "admin.delete": "Delete",
  "admin.deleteConfirm": "Really delete this? This can't be undone.",
    "admin.discardDraftConfirm": "Unsaved changes to this language will be lost. Switch anyway?",
  "admin.switchLanguageDraftKept":
    "Unsaved changes to this language are kept as a draft in this browser and offered again when you come back to it -- the content repo still holds the last saved version. Switch now?",
  "admin.cover": "Cover image (optional)",
  "admin.coverNone": "None",
  "admin.coverUpload": "Upload a cover",
  "admin.coverRemove": "Remove the cover",
  "admin.coverSaveFirst": "Save first -- images live in the project's own folder, which exists from then on.",
  "admin.categories": "Categories",
  "admin.newCategory": "New category",
  "admin.categoryName": "Name",
  "admin.categoryIcon": "Icon (emoji)",
  "admin.pages": "Pages",
  "admin.newPage": "New page",
  "admin.pageTitle": "Title",
  "admin.pageLanguages": "Languages",
  "admin.translationMissing": "Not translated yet",
  "admin.createTranslation": "Create translation",
  "admin.saveFirstForTranslations": "Save the page first, then its translations can be created.",
  "admin.published": "Published",
  "admin.draft": "Draft",
  "admin.editPage": "Edit page",
  "admin.editorTab": "Markdown",
  "admin.previewTab": "Preview",
  "admin.images": "Images",
  "admin.insertImage": "Insert image",
  "admin.uploadingImage": "Uploading…",
  "admin.imageUploaded": "Image uploaded and inserted.",
  "admin.imagesUploaded": "{count} images uploaded and inserted.",
  "admin.imagesEmpty": "No images in this project yet.",
  "admin.imageInsert": "Insert",
  "admin.imageDeleteConfirm": "Really delete this image? Pages using it will stop showing it.",
  "admin.imagePasteHint":
    "Paste a screenshot (Ctrl+V) or drag image files in here -- either uploads them into the project and inserts ![](…) at the cursor.",
  "admin.imageDropHere": "Drop images here",
  "admin.imageUploadProgress": "Uploading image {n} of {total}…",
  "admin.draftFoundTitle": "Unsaved draft found",
  "admin.draftFoundBody":
    "Last edited {when} and never saved. The draft is only in this browser; what you are looking at is the version from the content repo.",
  "admin.draftStaleTitle": "Unsaved draft -- but the page has changed since",
  "admin.draftStaleBody":
    "This draft is from {when}. The page has been changed in the content repo since then -- by someone else, or by you in another browser. So the draft is OLDER than what is shown here: restoring replaces the newer text with your older draft.",
  "admin.draftRestore": "Restore the draft",
  "admin.draftRestoreAnyway": "Restore it anyway",
  "admin.draftDiscard": "Discard the draft",
  "admin.draftRestored": "Draft restored -- not saved yet.",
  "admin.draftDiscarded": "Draft discarded.",
  "admin.branding": "Branding",
  "admin.brandingIntro":
    "This instance's name, logo, colour and footer. Stored as _site.yml in the content repo -- versioned, changeable by pull request, and its own per instance.",
  "admin.brandingName": "Site name",
  "admin.brandingTagline": "Tagline (home page)",
  "admin.brandingAccent": "Accent colour",
  "admin.brandingAccentReset": "Default colour",
  "admin.brandingLogo": "Logo",
  "admin.brandingLogoDark": "Logo (dark mode)",
  "admin.brandingFavicon": "Favicon",
  "admin.brandingUpload": "Upload",
  "admin.brandingRemoveImage": "Remove",
  "admin.brandingNoImage": "None",
  "admin.brandingFooterText": "Footer text",
  "admin.brandingFooterLinks": "Footer links",
  "admin.brandingLinkLabel": "Label",
  "admin.brandingLinkUrl": "URL (https://…, mailto: or /path)",
  "admin.brandingAddLink": "Add link",
  "admin.brandingPreview": "Preview",
  "admin.brandingSaved": "Branding saved.",
  "admin.brandingLanguages": "Content languages",
  "admin.brandingLanguagesHint":
    "Set with languages: in _site.yml in the content repo -- the first one is the default language.",
  "admin.brandingLanguagesNone": "Single language (no languages: in _site.yml)",
  "admin.moveUp": "Move up",
  "admin.moveDown": "Move down",
  "admin.selectProject": "Select a project on the left.",
  "admin.selectCategory": "Select a category to see its pages.",
  "admin.account": "Account",
  "admin.currentPassword": "Current password",
  "admin.newPassword": "New password",
  "admin.changePassword": "Change password",
  "admin.passwordChanged": "Password changed.",
  "admin.repoConnected": "Content repo connected",
  "admin.repoDisconnected": "Content repo unreachable",
  "admin.repoSyncNow": "Sync now",
  "admin.repoSyncDone": "Synced.",
  "admin.repoSyncFailed": "Sync failed.",
  "admin.repoNotConfiguredTitle": "No content repo connected",
  "admin.repoNotConfiguredBody":
    "DocuWaves stores all content as Markdown files in a separate Git repository. Set CONTENT_REPO_URL (and CONTENT_REPO_TOKEN or CONTENT_REPO_SSH_KEY) in your .env file and restart the container -- see the README for the full walkthrough.",
  "search.scopePrefix": "Only in: ",
  "version.switcher": "Version",
  "version.oldPrefix": "You are reading the documentation for ",
  "version.oldMiddle": ". The current version is ",
  "version.oldSuffix": ".",
  "admin.versions": "Versions",
  "admin.versionsIntro":
    "A frozen version is a snapshot of these docs as they stood at that release -- its own directory in the content repo, which never changes again. It is deliberately read-only here: correcting an old version is a file edit in the content repo (a pull request, say).",
  "admin.versionCurrent": "Current (being edited)",
  "admin.versionFreeze": "Freeze a version",
  "admin.versionId": "Version id (directory name, e.g. v2.0)",
  "admin.versionLabel": "Label (e.g. 2.0)",
  "admin.versionFreezeConfirmTitle": "Here is what freezing will do:",
  "admin.versionFreezeStepCopy": "Copy current/ byte for byte to {id}/ and record it in _versions.yml.",
  "admin.versionFreezeStepMove":
    "This project's first version: these will be moved into current/ first --",
  "admin.versionFreezeStepAssets":
    "assets/ moves with it, because a screenshot belongs to the version it documents. No page's Markdown is rewritten: ../assets/… still resolves.",
  "admin.versionFreezeStepCommit": "All of it as ONE commit in the content repo.",
  "admin.versionFreezeGo": "Freeze now",
  "admin.versionFrozen": "Version frozen.",
  "admin.versionReadOnly":
    "This version is frozen and read-only here. To correct it, edit the file under content/{project}/{version}/ in the content repo.",
  "admin.versionDeleteConfirm":
    "Really delete version {label}? This removes content/{project}/{id}/ from the content repo, with every page and image in that version. It can't be undone (it does stay in the Git history).",
  "admin.versionDeleted": "Version deleted.",
  "admin.versionReleased": "Frozen on",
  "admin.versionNone": "No version frozen yet -- this project has no version level.",
  "admin.versionViewing": "Viewing version",
  "admin.historyTab": "History",
  "admin.historyIntro":
    "Every page is a file in the content repo and every save is a commit -- this is that file's real git history. It is the history of the language currently open here; a translation is its own file with its own history.",
  "admin.historyEmpty": "No commits for this file in the content repo yet.",
  "admin.historyCreated": "Created",
  "admin.historyRenamedFrom": "Renamed from",
  "admin.historyDiff": "What this commit changed in this file",
  "admin.historyDiffNone": "Git reports no change to this file in that commit.",
  "admin.historyFirstVersion":
    "This is the first version of the file -- there is no predecessor to compare it against, so the whole file shows as added.",
  "admin.historyContent": "Markdown of this version",
  "admin.historyRestore": "Restore this version",
  "admin.historyRestoreConfirm":
    "Restore version {sha}?\n\nThis version's title and Markdown are saved as a NEW version -- one more commit in the content repo. Nothing is deleted and nothing is rolled back: the current version and every older one stay in the history, and you can come back the same way.\n\nLeft unchanged: the page's position, whether it is published, and its address (the slug) -- so links to this page keep working.",
  "admin.historyRestored": "Restored -- as a new commit in the content repo.",
  "admin.historyRestoreFrozen":
    "This documentation version is frozen, so there is nothing to restore into here. The history is still fully readable.",
  "admin.historyNotSavedYet": "There is a history once this language has been saved at least once.",
  "admin.tokens": "API tokens",
  "admin.tokensIntro":
    "An API token gives an AI assistant (Claude, say) access to these docs through the MCP endpoint. You create the token here and hand it to the assistant -- it is not a replacement for an admin login, and it can't delete anything.",
  "admin.tokensCost":
    "Cost: DocuWaves never calls a language model itself -- the endpoint only serves your documentation, and adds nothing to any AI bill. What your assistant costs depends on your own access: on a subscription it stays within that subscription, through an API the provider bills by usage.",
  "admin.tokensEmpty": "No API tokens yet.",
  "admin.tokenName": "Name (e.g. notes-bot)",
  "admin.tokenScope": "Scope",
  "admin.tokenScopeRead": "Read only",
  "admin.tokenScopeWrite": "Read and write",
  "admin.tokenScopeReadHint": "Can read and search the docs -- including unpublished drafts.",
  "admin.tokenScopeWriteHint":
    "WARNING: whoever holds this token can change the documentation -- create pages, overwrite text and publish it. Every change is a git commit in the content repo under this token's name, so it is traceable and revertable. Only hand it out if that is exactly what you want.",
  "admin.tokenExpires": "Expires on (optional)",
  "admin.tokenExpiresHint": "Leave empty for a token that never expires. It still works for all of the day you pick.",
  "admin.tokenCreate": "Create token",
  "admin.tokenCreated": "Token created.",
  "admin.tokenRevealTitle": "Here is your token -- it is shown this one time only.",
  "admin.tokenRevealBody":
    "Only a hash is stored, never the value itself. If you lose it you can't look it up, you can only create a new token.",
  "admin.tokenCopy": "Copy",
  "admin.tokenCopied": "Token copied.",
  "admin.tokenCopyFailed": "Copy failed -- select the value by hand.",
  "admin.tokenRevealDone": "Got it, hide this",
  "admin.tokenLastUsed": "Last used",
  "admin.tokenNeverUsed": "never used",
  "admin.tokenNoExpiry": "no expiry",
  "admin.tokenExpired": "expired",
  "admin.tokenExpiresOn": "expires",
  "admin.tokenCreatedOn": "created",
  "admin.tokenRevoke": "Revoke",
  "admin.tokenRevokeConfirm":
    "Really revoke the token “{name}”? It stops working on the very next request. This can't be undone.",
  "admin.tokenRevoked": "Token revoked.",
  "admin.tokenEndpointTitle": "Connecting an assistant",
  "admin.tokenEndpointBody": "The URL and header the assistant needs:",
  "common.loading": "Loading…",
  "common.error": "Something went wrong.",
  "common.back": "Back",
};

const dictionaries: Record<string, Dict> = { de, en };

type Lang = "de" | "en";

/** Whether a CONTENT language code is one the interface has words for --
 *  what lets the UI follow a reader's content-language choice on a
 *  multilingual instance (see lib/lang.tsx). A content language with no
 *  dictionary here simply leaves the interface as it is; the docs
 *  themselves are what that reader came for. */
export function isUiLang(code: string): code is Lang {
  return code === "de" || code === "en";
}

const I18nContext = createContext<{ lang: Lang; setLang: (l: Lang) => void; t: (key: keyof Dict) => string }>({
  lang: "en",
  setLang: () => {},
  t: (key) => key,
});

/** Remembering the interface language is a convenience, and every access to
 *  browser storage has to be able to fail: the property access itself throws
 *  in a browser configured to block site data, and setItem throws on a full
 *  quota. Unguarded, the read below happens inside a useState initializer and
 *  would take the whole app down over a preference. */
function detectDefaultLang(): Lang {
  let stored: string | null = null;
  try {
    stored = window.localStorage.getItem("docuwaves-lang");
  } catch {
    stored = null;
  }
  if (stored === "de" || stored === "en") return stored;
  return navigator.language.startsWith("de") ? "de" : "en";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(detectDefaultLang());

  function setLang(l: Lang) {
    // The switch itself always happens; only remembering it for next time
    // is allowed to fail.
    setLangState(l);
    try {
      window.localStorage.setItem("docuwaves-lang", l);
    } catch {
      // Not remembered for the next visit; the language is still switched.
    }
  }

  function t(key: keyof Dict): string {
    return dictionaries[lang][key] ?? dictionaries.en[key] ?? key;
  }

  return <I18nContext.Provider value={{ lang, setLang, t }}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  return useContext(I18nContext);
}
