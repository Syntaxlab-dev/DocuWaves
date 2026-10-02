---
order: 1
published: true
title: After the freeze
---

## The version is in the URL, and the default one is not

```
/p/cachepanel/pages/installation          <- the default version
/p/cachepanel/v2.0/pages/installation     <- the frozen 2.0
```

Every link ever shared before the project was versioned still points at exactly the same page. Which version an unprefixed URL shows is `default:` in `_versions.yml`, normally `current`.

A version switcher sits next to the language switcher. Switching keeps the reader on the page they are on when the target version has it, and lands on that version's home when it does not — never a dead end.

Reading a frozen version shows an unobtrusive line above the page:

> You are reading the documentation for 2.0. The current version is Current.

with a link across. It is not dismissible, because which version you are reading is a permanent property of the page, not a notification.

**Search covers only the version being read.** From inside `v2.0` you search `v2.0`; from the home page or the search page you search each project's default version, so one page never comes back once per release.

## Frozen versions are read-only

You can select a frozen version in the admin area and read it — pages, history, diffs, everything. Every control that would change it is gone, with the reason said out loud.

The UI hiding the buttons is not the enforcement. Every write path in the application goes through one guard, so a frozen version is refused through **any** route — the admin API, the [assistant endpoint](/p/docuwaves/pages/the-mcp-endpoint), a restore from history, an image upload. The answer is a `403` with the same sentence:

> Version 2.0 (v2.0) is frozen and can't be edited here. A frozen version is a snapshot of what the docs said at that release — to correct a page in it, edit the file under `content/cachepanel/v2.0/` in the content repo.

`403` rather than `409`, because nothing conflicted: this version is simply read-only.

So someone who genuinely must correct an old page edits the file in the content repository, where the change is reviewable like any other contribution. That is the intended path, not a workaround.

An assistant naming a frozen version in a write is refused rather than silently redirected into `current` — otherwise it would believe it had corrected a released version's documentation when it had changed a different one.

## Old versions do not compete with the current one in search results

A frozen version's page is a near-duplicate of the current one: same title, same topic, mostly the same words. Left alone they compete, and the winner is decided by age and inbound links — which is how somebody searching for your install guide ends up reading the one for a release from two years ago.

- A page in a frozen version whose **current version has the same page** points its canonical there. One address, and every signal the old URL earned is credited to the page a reader actually wants.
- A page in a frozen version with **no equivalent** in the current one — a section that no longer exists — has nothing to point at, so it is marked `noindex, follow` instead: out of the index, still crawled, its links still followed.
- **Never both.** A canonical pointing elsewhere *and* a `noindex` is the one combination that misfires, because the `noindex` can be read as applying to the page the canonical names, which would drop the current page from search.

The same rule applies one level up, to a frozen version's category and project pages. And `/sitemap.xml` lists each project's **default version only** — every other version has just been told not to compete, so listing it would invite exactly what the canonical prevents.

None of this makes the old docs less usable. They stay completely readable, linkable and reachable from the switcher. They are just not what a search result should be.

## Deleting a version

Under **Versions**, next to each frozen one. It removes that directory and its `_versions.yml` entry in a single commit, and the confirmation names the directory that will go.

- **`current` can never be deleted.** It is not a snapshot; it is the project's content.
- **Deleting the last frozen version** leaves the project with just `current/`. That reads exactly like an unversioned project — no switcher, no prefix — without moving every file back up a level and breaking every link a second time.
- If the version being deleted was the `default`, the default falls back to `current`.

As always, the commit that removed it leaves it in the history.

## Versions and languages compose

A frozen version keeps whatever translations existed at the moment it was frozen, with the language prefix in front of the project segment and the version after it:

```
/en/p/cachepanel/v2.0/pages/installation
```
