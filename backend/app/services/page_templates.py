"""The skeletons a new page can start from -- an API reference, a handbook
chapter, a set of release notes, a course module.

WHY THESE LIVE IN THE BACKEND rather than as four strings in the editor.
They are content, and content in this app has exactly one shape: Markdown
that the content repo will hold and that MarkdownView renders. Putting them
here means the MCP endpoint can offer the same four to an assistant later
without a second copy of them appearing in TypeScript, and it means a
translation of a template is next to the template it translates instead of
in a different language's UI dictionary.

WHY THEY ARE PLACEHOLDERS AND NOT ADVICE. Every line below is a heading, a
table header or an angle-bracketed slot. A template that shipped real
sentences would either be wrong for the page being written or be copied into
it unread -- and a documentation tool that fills pages with text nobody
wrote is worse than one that fills them with nothing. What a template is
FOR is the structure: which sections an API reference has and in what order,
that release notes separate "changed" from "fixed", that a how-to says what
to have ready before step 1. That part is genuinely reusable, so that part
is what is here.

LANGUAGE. A template exists per CONTENT language, because it becomes the
body of a page in that language -- an author writing `installation.de.md`
must not be handed English headings to translate. `en` is the fallback for a
language no translation of a template exists in yet, which is the honest
answer (English headings the author overwrites) rather than serving nothing
at all and leaving the picker empty on, say, a French instance.
"""

# The template ids, in the order the picker shows them. Ordered by how often
# a documentation instance actually needs one: most pages are how-tos, API
# references are the next biggest block, release notes are periodic, and
# course modules are their own kind of instance entirely.
TEMPLATE_IDS = ("handbook", "api-reference", "release-notes", "course-module")

FALLBACK_LANGUAGE = "en"

_NAMES = {
    "handbook": {"en": "How-to", "de": "Anleitung"},
    "api-reference": {"en": "API reference", "de": "API-Referenz"},
    "release-notes": {"en": "Release notes", "de": "Release Notes"},
    "course-module": {"en": "Course module", "de": "Kursmodul"},
}

_DESCRIPTIONS = {
    "handbook": {
        "en": "Prerequisites, numbered steps, and how to tell it worked.",
        "de": "Voraussetzungen, nummerierte Schritte, und woran man merkt, dass es geklappt hat.",
    },
    "api-reference": {
        "en": "One endpoint: parameters, an example call, the answer, the errors.",
        "de": "Ein Endpunkt: Parameter, Beispielaufruf, Antwort, Fehler.",
    },
    "release-notes": {
        "en": "What is new, what changed, what was fixed, and what an upgrade needs.",
        "de": "Was neu ist, was sich geändert hat, was behoben wurde, und was ein Update braucht.",
    },
    "course-module": {
        "en": "Learning goals, the material, an exercise, and questions to check it.",
        "de": "Lernziele, Inhalt, eine Übung, und Fragen zur Selbstkontrolle.",
    },
}

_HANDBOOK_EN = """# <What the reader will be able to do>

<One sentence: who this is for, and what it gets them.>

## Before you start

- <Something that has to be installed, running or configured already.>
- <A permission, an account, a key.>

## Steps

### 1. <First step>

<What to do, and what should happen.>

### 2. <Second step>

```bash
<the command, if there is one>
```

### 3. <Third step>

## Check that it worked

<How the reader confirms it, without having to ask anyone.>

## If something went wrong

| Symptom | Likely cause | What to do |
|---|---|---|
| <what they see> | <why> | <the fix> |

## Next

- [<The page that follows this one>](<slug>)
"""

_HANDBOOK_DE = """# <Was der Leser danach kann>

<Ein Satz: für wen das hier ist und was es bringt.>

## Vorbereitung

- <Was schon installiert, gestartet oder eingerichtet sein muss.>
- <Eine Berechtigung, ein Zugang, ein Schlüssel.>

## Schritte

### 1. <Erster Schritt>

<Was zu tun ist und was passieren sollte.>

### 2. <Zweiter Schritt>

```bash
<der Befehl, falls es einen gibt>
```

### 3. <Dritter Schritt>

## Prüfen, ob es geklappt hat

<Woran der Leser es selbst erkennt, ohne nachfragen zu müssen.>

## Wenn etwas schiefgeht

| Symptom | Wahrscheinliche Ursache | Was zu tun ist |
|---|---|---|
| <was zu sehen ist> | <warum> | <die Lösung> |

## Weiter

- [<Die Seite, die danach kommt>](<slug>)
"""

_API_EN = """# <Endpoint or function name>

<One sentence: what it does, and when you would reach for it.>

## At a glance

| | |
|---|---|
| Method and path | `GET /api/v1/<things>/{id}` |
| Authentication | <what the caller has to present> |
| Since | <version> |

## Parameters

| Name | In | Type | Required | Description |
|---|---|---|---|---|
| `id` | path | string | yes | <which one> |
| `<name>` | query | string | no | <what it changes> |

## Request

```bash
curl -H "Authorization: Bearer $TOKEN" \\
  "https://<host>/api/v1/<things>/42"
```

## Response

```json
{
  "id": "42",
  "<field>": "<value>"
}
```

| Field | Type | Description |
|---|---|---|
| `id` | string | <what it identifies> |
| `<field>` | <type> | <what it means> |

## Errors

| Status | When | What to do about it |
|---|---|---|
| `400` | <bad input> | <the fix> |
| `401` | <no or wrong credential> | <the fix> |
| `404` | <nothing there> | <the fix> |

## Notes

- <Rate limits, pagination, anything that surprises people.>
"""

_API_DE = """# <Endpunkt oder Funktionsname>

<Ein Satz: was er tut und wann man ihn benutzt.>

## Auf einen Blick

| | |
|---|---|
| Methode und Pfad | `GET /api/v1/<dinge>/{id}` |
| Authentifizierung | <was der Aufrufer mitschicken muss> |
| Seit | <Version> |

## Parameter

| Name | Wo | Typ | Pflicht | Beschreibung |
|---|---|---|---|---|
| `id` | Pfad | string | ja | <welches Objekt> |
| `<name>` | Query | string | nein | <was sich damit ändert> |

## Aufruf

```bash
curl -H "Authorization: Bearer $TOKEN" \\
  "https://<host>/api/v1/<dinge>/42"
```

## Antwort

```json
{
  "id": "42",
  "<feld>": "<wert>"
}
```

| Feld | Typ | Beschreibung |
|---|---|---|
| `id` | string | <was es identifiziert> |
| `<feld>` | <Typ> | <was es bedeutet> |

## Fehler

| Status | Wann | Was zu tun ist |
|---|---|---|
| `400` | <fehlerhafte Eingabe> | <die Lösung> |
| `401` | <kein oder falscher Zugang> | <die Lösung> |
| `404` | <nichts gefunden> | <die Lösung> |

## Hinweise

- <Rate-Limits, Paginierung, alles was überrascht.>
"""

_RELEASE_EN = """# <Version> — <YYYY-MM-DD>

<One paragraph: the one thing this release is about. Someone deciding
whether to update reads this and nothing else.>

## New

- <A capability that did not exist before.>

## Changed

- <Behaviour that is different now, and what it was before.>

## Fixed

- <The symptom that is gone, not the commit that removed it.>

## Upgrading

<What an existing installation has to do by hand: a setting to add, a
migration to run, a step whose order matters. "Nothing" is a perfectly good
answer, and worth writing down.>

## Known issues

- <What is still broken, so nobody has to find out for themselves.>
"""

_RELEASE_DE = """# <Version> — <JJJJ-MM-TT>

<Ein Absatz: worum es in dieser Version geht. Wer entscheidet, ob er
aktualisiert, liest das hier und sonst nichts.>

## Neu

- <Was es vorher nicht gab.>

## Geändert

- <Was sich anders verhält als vorher — und wie es vorher war.>

## Behoben

- <Das Symptom, das weg ist. Nicht der Commit, der es entfernt hat.>

## Umstieg

<Was eine bestehende Installation von Hand tun muss: eine Einstellung
ergänzen, eine Migration ausführen, eine Reihenfolge einhalten. „Nichts" ist
eine völlig gute Antwort und gehört trotzdem hierhin.>

## Bekannte Probleme

- <Was noch nicht funktioniert, damit es niemand selbst herausfinden muss.>
"""

_COURSE_EN = """# Module <n>: <Title>

**Takes:** <~45 minutes> · **Assumes:** <the module before this one, or
nothing>

## Learning goals

After this module you can:

- <Something the learner can DO, not something they will have read.>
- <…>

## <First section>

<The material. Keep one idea per section, and give each section a heading --
the page's contents list is built from them.>

## <Second section>

## Exercise

<A task with a checkable result. Say what "done" looks like.>

## Check yourself

1. <A question the material answers.>
2. <…>

## Going further

- [<A page here that goes deeper>](<slug>)
"""

_COURSE_DE = """# Modul <n>: <Titel>

**Dauer:** <ca. 45 Minuten> · **Setzt voraus:** <das Modul davor, oder
nichts>

## Lernziele

Nach diesem Modul kannst du:

- <Etwas, das der Lernende TUN kann — nicht etwas, das er gelesen haben
  wird.>
- <…>

## <Erster Abschnitt>

<Der Inhalt. Ein Gedanke pro Abschnitt, und jeder Abschnitt bekommt eine
Überschrift — daraus baut sich das Inhaltsverzeichnis der Seite.>

## <Zweiter Abschnitt>

## Übung

<Eine Aufgabe mit überprüfbarem Ergebnis. Schreib dazu, woran man merkt,
dass sie gelöst ist.>

## Selbstkontrolle

1. <Eine Frage, die der Inhalt beantwortet.>
2. <…>

## Weiterführend

- [<Eine Seite hier, die tiefer geht>](<slug>)
"""

_BODIES = {
    "handbook": {"en": _HANDBOOK_EN, "de": _HANDBOOK_DE},
    "api-reference": {"en": _API_EN, "de": _API_DE},
    "release-notes": {"en": _RELEASE_EN, "de": _RELEASE_DE},
    "course-module": {"en": _COURSE_EN, "de": _COURSE_DE},
}


def _pick(by_language: dict[str, str], language: str) -> str:
    """The requested language's text, English otherwise. `language` is ''
    on a single-language instance that never configured `languages:`, which
    lands on the fallback like any other unknown code."""
    return by_language.get(language) or by_language[FALLBACK_LANGUAGE]


def get_template(template_id: str, language: str = "") -> str | None:
    """One template's Markdown body, or None for an id that isn't one --
    which is a caller sending something the picker never offered, so it is
    a 404 rather than an empty page."""
    body = _BODIES.get(template_id)
    return None if body is None else _pick(body, language)


def list_templates(language: str = "") -> list[dict]:
    """Every template, in TEMPLATE_IDS order, with its Markdown included.

    The body travels with the list on purpose: there are four of them, they
    are a couple of kilobytes together, and the alternative is a second
    round trip at exactly the moment an author has decided to start writing.
    """
    return [
        {
            "id": template_id,
            "name": _pick(_NAMES[template_id], language),
            "description": _pick(_DESCRIPTIONS[template_id], language),
            "markdown": _pick(_BODIES[template_id], language),
        }
        for template_id in TEMPLATE_IDS
    ]
