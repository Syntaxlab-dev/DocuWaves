"""Pages due for a review: the other half of review notes.

A review note says "this text was checked, by this person, on this day"
(see the review-notes docs). On its own it only ever gets older. A project
can say how old is too old:

    # content/<project>/_project.yml
    review_every: 180

and from then on every PUBLISHED page of its working version whose note is
older than that many days -- or that has never had one -- is due. Editing
the text already drops the note (pages_store), so a page that was changed
since it was last checked is due straight away, which is the point.

Only the working version: a frozen version is a release's documentation as
it shipped, and nobody can edit or re-review it anyway. Drafts are not
listed: nobody reads them yet.

Computed on request, never stored. The answer depends on today's date, and
a stored "due" flag would be wrong by tomorrow.
"""

from datetime import date, timedelta

from app.services import categories_store, content_versions, db, projects_store


def _parse(day: str) -> date | None:
    try:
        return date.fromisoformat((day or "")[:10])
    except ValueError:
        return None


def due_pages(today: date | None = None) -> list[dict]:
    """Every due page of every project that asks for reviews, most overdue
    first: never-reviewed pages (no date at all) ahead of the oldest note."""
    today = today or date.today()
    placeholder = "%s" if db.is_postgres() else "?"
    published = "TRUE" if db.is_postgres() else "1"
    due: list[dict] = []
    for project in projects_store.list_projects():
        every = project.get("review_every_days") or 0
        if every <= 0:
            continue
        version = content_versions.writable_version(project["slug"])
        with db.get_connection() as conn:
            rows = conn.execute(
                f"SELECT id, title, slug, language, reviewed_by, reviewed_at, category_id FROM pages "
                f"WHERE project_id = {placeholder} AND version = {placeholder} AND published = {published}",
                (project["id"], version),
            ).fetchall()
        categories: dict[int, dict | None] = {}
        for row in rows:
            reviewed = _parse(row[5])
            if reviewed is not None and reviewed + timedelta(days=every) > today:
                continue
            if row[6] not in categories:
                categories[row[6]] = categories_store.get_category(row[6])
            category = categories[row[6]]
            due.append({
                "page_id": row[0],
                "title": row[1],
                "slug": row[2],
                "language": row[3],
                "reviewed_by": row[4],
                "reviewed_at": row[5],
                "days_overdue": None if reviewed is None else (today - reviewed).days - every,
                "project_slug": project["slug"],
                "project_name": project["name"],
                "category_name": category["name"] if category else "",
                "review_every_days": every,
            })
    # Never reviewed first, then the longest overdue.
    due.sort(key=lambda p: (p["days_overdue"] is not None, -(p["days_overdue"] or 0), p["project_slug"], p["title"]))
    return due
