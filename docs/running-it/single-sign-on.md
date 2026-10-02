---
order: 2
published: true
title: Single sign-on
---

DocuWaves speaks standard OpenID Connect, so it works with Authentik, Keycloak, Authelia, Zitadel, or anything else that implements the spec. Nothing is hardcoded to a particular provider.

SSO is **additive**. The password form stays available whatever you configure.

## In your identity provider

Create an OAuth2 / OpenID Connect application with:

- **Redirect URI:** `https://<your-docuwaves-domain>/api/auth/oidc/callback` — the path is fixed; only the domain changes.
- **A real signing key.** Without one, most providers' JWKS endpoint returns no signing keys at all, and DocuWaves refuses to trust a token it cannot verify. The error says so in those words rather than failing vaguely — or, worse, accepting an unsigned token.

DocuWaves requests the `openid profile email` scopes.

## In `.env`

```bash
OIDC_ISSUER_URL=https://auth.example.com/application/o/docuwaves/
OIDC_CLIENT_ID=<client id from your provider>
OIDC_CLIENT_SECRET=<client secret from your provider>
OIDC_PROVIDER_NAME=authentik
```

`OIDC_ISSUER_URL` is the base URL DocuWaves fetches `{OIDC_ISSUER_URL}/.well-known/openid-configuration` from, to find the authorization, token and JWKS endpoints itself. You do not need to look those up individually.

`OIDC_PROVIDER_NAME` only sets the login button's label — "Sign in with authentik". It is optional and defaults to `authentik`.

Leave all of them blank to keep SSO off. Then:

```bash
docker compose up -d
```

A login button appears next to the password form.

## SSO signs accounts in; it does not create them

- **On a brand-new instance with no account yet**, the first successful SSO login **creates** the first administrator from your SSO username, and skips the setup screen entirely. Same trust model as the setup screen itself: whoever gets there first.
- **On an already-configured instance**, the SSO username must match an [account](/p/docuwaves/pages/accounts-and-roles) that already exists here, **exactly**, or the login is rejected with "No matching account for this SSO identity."

That second rule is the important one. Being able to authenticate against your identity provider does not make you anything here: accounts are created deliberately, by an administrator, and the **role** is decided in DocuWaves rather than by whoever the provider lets in. There is no group mapping and no claim that grants a role.

So to give a colleague SSO access: create an account whose username is exactly the username their provider will send, with the role they should have. They then sign in with the button and never set a password.

The username is taken from `preferred_username`, falling back to `email`, then `sub`.

An account created by SSO — the first one, or one an administrator makes for somebody who will only ever use the button — is SSO-only until a real password is set from the **Account** panel. Worth doing: it is your way back in if the identity provider is unavailable.

## Get the address right first

The `redirect_uri` DocuWaves sends is built from the request's own base URL. Behind a proxy that does not forward `X-Forwarded-Proto`, that comes out as `http://` — and a strict provider rejects the mismatch outright.

So configure the proxy before you configure SSO. See [Behind a reverse proxy](/p/docuwaves/pages/behind-a-reverse-proxy).

## What the flow does

Authorization code with **PKCE** (`S256`), plus `state` and `nonce`, all three generated per login and checked on the way back. The ID token is validated as `RS256` against the provider's published JWKS.

A failure at any of those points returns you to the site with `?oidc_login=failed`, and the login page says the attempt failed. It does not say which check failed — that detail is for your provider's logs, not for whoever is at the keyboard.
