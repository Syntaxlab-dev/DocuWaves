---
order: 3
published: true
title: Offline reading and installing as an app
---

DocuWaves works as a Progressive Web App. A reader can keep a project's
documentation on their device and read it without internet, and can install
the site like an app. Nothing needs to be switched on for this.

## Reading offline

Every page a reader opens is kept in their browser. When the connection
drops, those pages stay readable and a banner at the top says that the
reader is offline.

To keep a whole project, open the project's start page and click
**Save for offline reading**. DocuWaves loads every page of the project in
the language and version being read, and shows the progress while it does.
Afterwards the start page shows when the copy was saved. Click
**Update the offline copy** to refresh it later.

Online, a reader always gets the current version of a page. The saved copy
is only used when the network is not available.

What is not available offline: search, the documentation chat, page
feedback and the PDF, EPUB and Markdown exports. They need the server.

## Installing as an app

Browsers that support it (Chrome, Edge, Safari on iOS and macOS, Android)
offer to install the site, for example with **Install app** in the address
bar or **Add to Home Screen** on a phone. The installed app opens in its own
window, with the name, icon and accent colour from
[Branding this instance](/p/docuwaves/pages/branding-this-instance).

## Privacy

Private projects are only saved for readers who are signed in and allowed to
read them. Signing out empties the saved pages from the browser, so nothing
of a private project stays on a shared computer.

## For administrators

The offline copy is a service worker (`/sw.js`) and the browser's cache
storage. There is nothing to configure on the server. The app manifest is
served at `/manifest.webmanifest` and is built from the instance's branding.
Offline reading and installing need HTTPS, which every production instance
has anyway; on `localhost` they also work without it.
