"""Notion "Markdown & CSV" exports through the importer: ids gone, the page
tree as categories, databases as tables, callouts by emoji, and the ZIP of
ZIPs Notion actually hands out (services/import_notion.py)."""
from app.services import importer, pages_store, projects_store

from tests.test_importer import make_zip, png, world  # noqa: F401 -- the fixture

H = "0123456789abcdef0123456789abcdef"
H2 = "fedcba9876543210fedcba9876543210"
H3 = "aaaabbbbccccddddeeeeffff00001111"
H4 = "1111222233334444555566667777aaaa"
H5 = "9999888877776666555544443333bbbb"

EXPORT = {
    f"Wiki {H}.md": f"# Wiki\n\nStart. Siehe [Server](Wiki%20{H}/Server%20{H2}.md) und [Aufgaben](Wiki%20{H}/Aufgaben%20{H3}.csv).\n\n"
                    "<aside>\n💡 Lies das zuerst.\n</aside>\n\n<aside>\n🧭 Nur Deko-Emoji.\n</aside>\n",
    f"Wiki {H}/Server {H2}.md": f"# Server\n\n![Schema](Server%20{H2}/schema.png)\n\n<aside>\n⚠️ Vorsicht beim Neustart.\n</aside>\n",
    f"Wiki {H}/Server {H2}/Backup {H4}.md": "# Backup\n\nTäglich.\n",
    f"Wiki {H}/Server {H2}/schema.png": png(),
    f"Wiki {H}/Aufgaben {H3}.csv": "Name,Status,Wer\nUpdate einspielen,Erledigt,Max\nBackup | prüfen,Offen,Eva\n",
    f"Wiki {H}/Aufgaben {H3}_all.csv": "Name,Status,Wer\nUpdate einspielen,Erledigt,Max\nBackup | prüfen,Offen,Eva\n",
    f"Wiki {H}/Aufgaben {H3}/Update einspielen {H5}.md": "# Update einspielen\n\nStatus: Erledigt\n\nNotizen.\n",
    f"Wiki {H}/FAQ {H4[::-1]}.md": "# FAQ\n\nFragen.\n",
}


def notion_zip() -> bytes:
    """What Notion really sends: a ZIP holding the export as a ZIP."""
    return make_zip({f"Export-{H}-Part-1.zip": make_zip(EXPORT)})


def body(slug: str) -> str:
    project = projects_store.get_project_by_slug("notion")
    return pages_store.get_page_by_slug(project["id"], slug)["markdown_content"]


def test_ids_gone_tree_as_categories(world):
    result = importer.plan(notion_zip(), new_project_name="Notion").summary()
    assert result["tool"] == "notion"
    assert [(c["name"], [p["title"] for p in c["pages"]]) for c in result["categories"]] == [
        ("Allgemein", ["Wiki", "FAQ"]),
        ("Aufgaben", ["Aufgaben", "Update einspielen"]),
        ("Server", ["Server", "Backup"]),
    ]
    assert result["assets"] == 1
    assert H not in str(result)


def test_links_images_callouts_and_the_database(world):
    importer.apply(notion_zip(), "chef", new_project_name="Notion")
    wiki = body("wiki")
    assert not wiki.lstrip().startswith("# Wiki")
    assert "[Server](/p/notion/pages/server)" in wiki and "[Aufgaben](/p/notion/pages/aufgaben)" in wiki
    assert "> [!TIP]\n> Lies das zuerst." in wiki
    assert "> [!NOTE]\n> Nur Deko-Emoji." in wiki

    server = body("server")
    assert "![Schema](../assets/imported/wiki/server/schema.png)" in server
    assert "> [!WARNING]\n> Vorsicht beim Neustart." in server

    table = body("aufgaben")
    assert "| Name | Status | Wer |" in table
    assert "| [Update einspielen](/p/notion/pages/update-einspielen) | Erledigt | Max |" in table
    assert "| Backup \\| prüfen | Offen | Eva |" in table


def test_a_plain_export_without_the_outer_zip_works_too(world):
    assert importer.plan(make_zip(EXPORT), new_project_name="Notion").tool == "notion"


def test_a_zip_next_to_documentation_is_not_opened(world):
    result = importer.plan(make_zip({"a.md": "# A\n", "anhang.zip": make_zip({"b.md": "# B\n"})}), new_project_name="X")
    assert [p.title for c in result.categories for p in c.pages] == ["A"]
    assert any(s["path"] == "anhang.zip" for s in result.skipped)


def test_csv_outside_notion_is_not_imported(world):
    result = importer.plan(make_zip({"a.md": "# A\n", "daten.csv": "a,b\n1,2\n"}), new_project_name="X").summary()
    assert result["tool"] == "markdown" and any(s["path"] == "daten.csv" for s in result["skipped"])
