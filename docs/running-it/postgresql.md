---
order: 5
published: true
title: PostgreSQL
---

SQLite is the default and needs no configuration: a single file at `/data/docuwaves.db`. PostgreSQL is available if you would rather not have one — for instance because you already run Postgres for other services and want everything backed up the same way.

Before you decide, remember what this database is: a **rebuildable search and browse index** over the content repository. It holds no documentation of its own. Moving it to Postgres is an operational preference, not a durability upgrade for your content.

## Switching to it

1. In `.env`, set the connection string and the password the container will use:

   ```bash
   DATABASE_URL=postgresql://docuwaves:a-real-password@postgres:5432/docuwaves
   POSTGRES_PASSWORD=a-real-password
   ```

   The two passwords must match. `postgres` is the compose service's hostname.

2. Start with the profile:

   ```bash
   docker compose --profile postgres up -d --build
   ```

**Every future `docker compose` command that should also start Postgres needs the same `--profile postgres` flag.** Without it, `docker compose up -d` brings up DocuWaves alone — which is exactly the behaviour someone who never wanted Postgres should get, and exactly the confusing one if you did.

The shipped service is `postgres:16-alpine`, named `docuwaves-postgres`, with its data in `./pgdata` next to `./data`.

`DATABASE_URL` is the whole switch. Blank means SQLite; filled in means Postgres, and `SQLITE_PATH` is then unused.

## What switching does not carry over

The index rebuilds itself from the content repository, so **no documentation is lost**. But three things live only in the database and do not travel between backends:

- the admin account,
- active sessions,
- [API tokens](/p/docuwaves/pages/api-tokens-and-scopes).

So switching means going through first-run setup again and issuing new tokens. Plan for that rather than discovering it. The same is true switching back.

## Search behaves the same, but is implemented twice

The two backends have unrelated full-text mechanisms, so search is genuinely two queries rather than one shared one:

- **SQLite** uses the FTS5 virtual table, with each search term quoted as its own FTS5 string literal so punctuation inside a term cannot break FTS5's query parser. Terms are OR'd, ranked by `bm25()`.
- **PostgreSQL** computes `to_tsvector('simple', title || ' ' || content)` in the query and matches it against `plainto_tsquery('simple', …)`, ranked by `ts_rank`. Passing the user's input as a parameter is what makes arbitrary text safe here, unlike hand-building a match string.

The `'simple'` configuration on the Postgres side deliberately skips English stemming, which matches FTS5's own non-stemming default. That keeps results close to identical between the two rather than having one instance find "installing" when you search "install" and the other not.

There is no materialised tsvector column and no trigger to maintain — simpler, and fast enough at the row counts a self-hosted documentation tool actually holds.

## Which one to pick

Stay on SQLite unless you have a reason. One file, no second container, no password to rotate, and it is rebuilt from your files if it ever breaks.

Choose Postgres if you already operate one and want this instance inside the same backup and monitoring story.
