---
order: 7
published: true
title: E-mail notifications
---

DocuWaves can send an e-mail when something happens that a person working
on the documentation cares about. Each account decides for itself under
**Account**, and nobody is signed up for anything by default.

## What you can be told about

| Choice | Who gets it |
|---|---|
| **A page waits for approval** | Every account that can open the admin area, except the person who submitted it |
| **A page I submitted was approved or sent back** | The person who submitted it, with the reviewer's comment |
| **A page was published, changed or unpublished** | Everyone who chose it, except the person who made the change |

A message names the page, its project, what happened and who did it, and
links to the page (once it is live and `PUBLIC_BASE_URL` is set) or to the
admin area. It never contains the page's text: a mailbox is a copy nobody
can take back, and a draft waiting for approval is exactly what should not
have one. Reader accounts get nothing, because they never see the admin
area. Private projects are included, because every recipient is an account
that may read them.

## Setting up the mail server

E-mail is off until the instance has an SMTP server. Until then the
**Account** panel does not show the setting at all. In `.env`:

```
SMTP_HOST=smtp.example.com
SMTP_USERNAME=docs@example.com
SMTP_PASSWORD=...
SMTP_FROM=DocuWaves <docs@example.com>
```

`SMTP_SECURITY` is `starttls` (the default, port 587), `ssl` (port 465) or
`none` (a relay on the same machine or network, port 25). `SMTP_PORT`
overrides the port. `SMTP_FROM` may be left out when `SMTP_USERNAME` is an
address. These are environment variables rather than an admin setting
because the password is a credential, and the admin settings are written to
a repository built to be cloned.

### A mail server on the same machine

When DocuWaves runs in a container and the mail server on the host, the
container may not reach it by its public name. Rootless Podman with its
default network (pasta) gives the container the host's own public address,
so a connection to that address stays inside the container and is refused.
Use the host's address as seen from the container (`169.254.1.2`, or
`host.containers.internal`), and tell DocuWaves which name the certificate
is for:

```env
SMTP_HOST=169.254.1.2
SMTP_TLS_SERVER_NAME=mail.example.com
```

The certificate is still checked, against `SMTP_TLS_SERVER_NAME` instead of
the address. Alternatively, map the name in the container:
`--add-host mail.example.com:169.254.1.2`.

After a restart, open **Account**, enter your address and press **Send a
test e-mail**. It waits for the mail server's answer, so a wrong setting
shows up there, by the kind of error, rather than as notifications that
never arrive.

## When the mail server is down

A notification never slows a save down or makes it fail. Messages are sent
in the background; one that cannot be delivered is a line in the server log
naming the SMTP host, never the address or the password. Nothing is queued
across a restart.

For a team channel rather than personal mail, use
[webhooks](/p/docuwaves/pages/webhooks): the same events, sent to Discord,
Slack, Microsoft Teams, Matrix or any JSON endpoint.
