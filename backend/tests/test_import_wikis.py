"""BookStack, Wiki.js and MediaWiki exports through the importer
(services/import_bookstack.py, import_wikijs.py, import_mediawiki.py)."""
import json

import pytest

from app.services import import_mediawiki, importer, pages_store, projects_store

from tests.test_importer import make_zip, png, world  # noqa: F401 -- the fixture


def body(project: str, slug: str) -> str:
    found = projects_store.get_project_by_slug(project)
    return pages_store.get_page_by_slug(found["id"], slug)["markdown_content"]


def tree(result: dict) -> list:
    return [(c["name"], [p["title"] for p in c["pages"]]) for c in result["categories"]]


# ---- BookStack ----

BOOK = {
    "instance": {"id": "x", "version": "v25.02"},
    "exported_at": "2026-11-24T10:00:00Z",
    "book": {
        "id": 1,
        "name": "Handbuch",
        "pages": [
            {"id": 10, "name": "Willkommen", "priority": 0, "markdown": "Start. Weiter mit [Backup]([[bsexport:page:12]]).\n",
             "html": "", "images": [], "attachments": [], "tags": []},
        ],
        "chapters": [
            {
                "id": 2, "name": "Betrieb", "priority": 1, "tags": [],
                "pages": [
                    {"id": 12, "name": "Backup", "priority": 1, "markdown": "",
                     "html": '<h2>Täglich</h2><p>Siehe <img src="[[bsexport:image:5]]" alt="Plan"></p>'
                             '<p><a href="[[bsexport:chapter:2]]">Kapitel</a></p>',
                     "images": [{"id": 5, "name": "plan.png", "file": "plan.png", "type": "gallery"}],
                     "attachments": [
                         {"id": 7, "name": "Checkliste", "file": "checkliste.pdf"},
                         {"id": 9, "name": "Ansage", "file": "ansage.mp3"},
                         {"id": 8, "name": "Hersteller", "link": "https://example.org/doku"},
                     ],
                     "tags": []},
                    {"id": 11, "name": "Update", "priority": 0, "markdown": "Erst [Backup]([[bsexport:page:12]]), "
                     "dann [[bsexport:page:999]].\n", "html": "", "images": [], "attachments": [], "tags": []},
                ],
            },
        ],
    },
}


def bookstack_zip(data=BOOK) -> bytes:
    return make_zip({
        "data.json": json.dumps(data),
        "files/plan.png": png(),
        "files/checkliste.pdf": b"%PDF-1.4\n%%EOF\n",
        "files/ansage.mp3": b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 64,
    })


def test_bookstack_book_as_categories(world):
    result = importer.plan(bookstack_zip(), new_project_name="Handbuch").summary()
    assert result["tool"] == "bookstack"
    assert tree(result) == [("Allgemein", ["Willkommen"]), ("Betrieb", ["Update", "Backup"])]
    assert result["assets"] == 2
    assert any("not in the export" in w["message"] for w in result["warnings"])
    assert any("'Checkliste' not taken over" in w["message"] for w in result["warnings"])


def test_bookstack_references_images_attachments(world):
    importer.apply(bookstack_zip(), "chef", new_project_name="Handbuch")
    assert "[Backup](/p/handbuch/pages/backup)" in body("handbuch", "willkommen")
    backup = body("handbuch", "backup")
    assert "## Täglich" in backup
    assert "![Plan](../assets/imported/files/plan.png)" in backup
    assert "[Kapitel](/p/handbuch/pages/update)" in backup  # a chapter link: its first page
    assert "## Anhänge" in backup
    assert "- Checkliste\n" in backup
    assert "- [Ansage](../assets/imported/files/ansage.mp3)" in backup
    assert "- [Hersteller](https://example.org/doku)" in backup
    assert "bsexport" not in body("handbuch", "update")


def test_bookstack_single_page_export(world):
    data = {"page": {"id": 3, "name": "Allein", "markdown": "Text.\n", "images": [], "attachments": []}}
    result = importer.plan(make_zip({"data.json": json.dumps(data)}), new_project_name="X").summary()
    assert result["tool"] == "bookstack" and tree(result) == [("Allgemein", ["Allein"])]


def test_json_outside_bookstack_is_not_imported(world):
    result = importer.plan(make_zip({"a.md": "# A\n", "data.json": "{}"}), new_project_name="X").summary()
    assert result["tool"] == "markdown" and any(s["path"] == "data.json" for s in result["skipped"])


# ---- Wiki.js ----

def wikijs_page(title: str, text: str, published: str = "true") -> str:
    return (
        f"<!--\ntitle: {title}\ndescription: \npublished: {published}\ndate: 2026-01-01T00:00:00.000Z\n"
        f"tags: a, b\neditor: markdown\ndateCreated: 2026-01-01T00:00:00.000Z\n-->\n\n{text}"
    )


WIKIJS = {
    "en/home.md": wikijs_page("Home", "# Welcome\n\nSee [install](/en/guide/install) and ![logo](/en/uploads/logo.png).\n"),
    "en/guide/install.md": wikijs_page("Installation", "Steps.\n\n> Back up first.\n{.is-warning}\n\n> Done.\n{.is-success}\n"),
    "en/guide/visual.html": wikijs_page("Visual page", "<h2>Hello</h2><p>From the <strong>visual</strong> editor.</p>"),
    "en/uploads/logo.png": png(),
    "de/home.md": wikijs_page("Start", "Hallo.\n"),
}


def test_wikijs_front_matter_locale_and_folders(world):
    result = importer.plan(make_zip(WIKIJS), new_project_name="Wiki").summary()
    assert result["tool"] == "wikijs"
    assert tree(result) == [("Allgemein", ["Home"]), ("Guide", ["Installation", "Visual page"])]
    assert any("'de' not imported" in w["message"] for w in result["warnings"])


def test_wikijs_links_callouts_and_html(world):
    importer.apply(make_zip(WIKIJS), "chef", new_project_name="Wiki")
    home = body("wiki", "home")
    assert "[install](/p/wiki/pages/installation)" in home
    assert "![logo](../assets/imported/uploads/logo.png)" in home
    install = body("wiki", "installation")
    assert "> [!WARNING]\n> Back up first." in install
    assert "> [!TIP]\n> Done." in install
    assert "{.is-" not in install
    visual = body("wiki", "visual-page")
    assert "## Hello" in visual and "**visual**" in visual


def test_wikijs_without_locales(world):
    files = {"home.md": wikijs_page("Home", "Hi [x](/docs/a)\n"), "docs/a.md": wikijs_page("A", "Text\n")}
    result = importer.plan(make_zip(files), new_project_name="W").summary()
    assert tree(result) == [("Allgemein", ["Home"]), ("Docs", ["A"])]
    assert not result["warnings"]


# ---- MediaWiki ----

def mediawiki_dump(*pages: tuple[str, str, int]) -> bytes:
    xml = ['<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/" version="0.11" xml:lang="de">',
           "<siteinfo><sitename>Wiki</sitename></siteinfo>"]
    for title, text, ns in pages:
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        xml.append(
            f"<page><title>{title}</title><ns>{ns}</ns><id>1</id>"
            f"<revision><id>1</id><text>alt</text></revision>"
            f"<revision><id>2</id><text xml:space=\"preserve\">{escaped}</text></revision></page>"
        )
    xml.append("</mediawiki>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' + "\n".join(xml)).encode()


SERVER = """Der '''Server''' läuft ''immer''.{{Infobox|name=x|{{nested}}}}
__TOC__
== Einrichtung ==
* Punkt eins mit [[Backup|Sicherung]]
** Unterpunkt
# erstens
# zweitens
; Begriff : Erklärung
Siehe [https://example.org Beispiel] und [https://example.com].
[[Datei:Diagramm.png|mini|Das Diagramm]]
[[Fehlende Seite]] und [[Backup#Ablauf|Ablauf]]s.
Belegt.<ref>Quelle A</ref>

<syntaxhighlight lang="bash">
echo '''nicht fett'''
</syntaxhighlight>

 eingerückt
 als Code

{| class="wikitable"
|+ Ports
! Dienst !! Port
|-
| Web || 443
|-
| style="color:red" | SSH || 22
|}
----
<nowiki>[[kein Link]]</nowiki>
[[Kategorie:Betrieb]]
"""


def test_mediawiki_pages_categories_and_namespaces(world):
    dump = mediawiki_dump(
        ("Server", SERVER, 0),
        ("Backup", "== Ablauf ==\nTäglich.\n[[Category:Betrieb]]", 0),
        ("Hauptseite", "Willkommen im [[Server]].", 0),
        ("Alt", "#WEITERLEITUNG [[Server]]\n#REDIRECT [[Server]]", 0),
        ("Vorlage:Infobox", "{{{name}}}", 10),
    )
    result = importer.plan(make_zip({"export.xml": dump, "bilder/Diagramm.png": png()}), new_project_name="MW").summary()
    assert result["tool"] == "mediawiki"
    assert tree(result) == [("Allgemein", ["Hauptseite"]), ("Betrieb", ["Backup", "Server"])]
    messages = " ".join(w["message"] for w in result["warnings"])
    assert "Infobox" in messages and "Fehlende Seite" in messages


def test_mediawiki_wikitext(world):
    dump = mediawiki_dump(("Server", SERVER, 0), ("Backup", "== Ablauf ==\nTäglich.", 0))
    importer.apply(make_zip({"export.xml": dump, "bilder/Diagramm.png": png()}), "chef", new_project_name="MW")
    text = body("mw", "server")
    assert "Der **Server** läuft *immer*." in text
    assert "{{" not in text and "__TOC__" not in text
    assert "## Einrichtung" in text
    assert "- Punkt eins mit [Sicherung](/p/mw/pages/backup)" in text
    assert "  - Unterpunkt" in text
    assert "1. erstens\n1. zweitens" in text
    assert "**Begriff**: Erklärung" in text
    assert "[Beispiel](https://example.org)" in text and "<https://example.com>" in text
    assert "![Das Diagramm](../assets/imported/bilder/diagramm.png)" in text
    assert "Fehlende Seite und [Ablaufs](/p/mw/pages/backup#ablauf)." in text
    assert "Belegt.[^1]" in text and "[^1]: Quelle A" in text
    assert "```bash\necho '''nicht fett'''\n```" in text
    assert "```\neingerückt\nals Code\n```" in text
    assert "**Ports**" in text
    assert "| Dienst | Port |" in text and "| Web | 443 |" in text and "| SSH | 22 |" in text
    assert "\n---\n" in text
    assert "\\[\\[kein Link\\]\\]" in text
    assert "Kategorie" not in text


def test_a_bare_xml_upload_is_read_as_a_dump(world):
    result = importer.plan(mediawiki_dump(("Eine Seite", "Text", 0)), new_project_name="MW").summary()
    assert result["tool"] == "mediawiki" and tree(result) == [("Allgemein", ["Eine Seite"])]


def test_a_doctype_is_refused():
    with pytest.raises(ValueError):
        import_mediawiki._pages(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><mediawiki></mediawiki>')


def test_xml_outside_mediawiki_is_not_imported(world):
    result = importer.plan(make_zip({"a.md": "# A\n", "pom.xml": "<project/>"}), new_project_name="X").summary()
    assert result["tool"] == "markdown" and any(s["path"] == "pom.xml" for s in result["skipped"])
