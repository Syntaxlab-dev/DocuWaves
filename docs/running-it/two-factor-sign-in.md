---
order: 2
published: true
title: Two-factor sign-in
---

Each account can protect its password with a second factor. Once it has one,
a correct password is no longer enough to sign in: DocuWaves asks for the
second factor before it starts a session.

## The three kinds

**Security keys and passkeys.** A YubiKey or any other FIDO2 key, and the
passkeys built into phones and laptops: Touch ID, Face ID, Windows Hello,
Android. This is the strongest of the three, because a key only ever answers
the site it was registered on, so a look-alike phishing page gets nothing it
can use. An account can have as many keys as it likes, each with a name.
Register two and keep one as a spare, so that losing a key is not losing the
account.

**An authenticator app.** The six-digit codes from 2FAS, Aegis, Google
Authenticator, Microsoft Authenticator, 1Password or any other app that does
TOTP. One per account.

**Recovery codes.** Ten single-use codes, created the moment you add your
first key or app and shown exactly once. They are the way back in when the
key is lost and the phone is dead. Print them, or keep them in a password
manager. Only hashes are stored, so nobody can show them to you again; you
can create a new set at any time, and the old set stops working when you do.

## Turning it on

Open **Account** in the admin area. Under *Two-factor sign-in*:

- **Add key**, optionally with a name such as "YubiKey 5C". The browser asks
  you to touch the key or confirm with your fingerprint.
- **Set up** next to *Authenticator app*. Scan the QR code with the app (or
  type the key shown beside it) and enter the code the app shows. The app is
  only switched on once that code is right, so 2FA never starts with a
  secret nobody has.

The first of these shows your recovery codes. Save them before you click
*I have saved them*.

Removing a key, removing the app or creating new recovery codes asks for your
password again: a session left open on somebody else's screen is not enough
to switch 2FA off. Removing your last key and your app switches 2FA off and
deletes the recovery codes with it.

Security keys need the address the browser shows to stay the same: a key is
bound to the host name it was registered on. If you move the instance to a
new domain, register the keys again there. Set `PUBLIC_BASE_URL` when the
instance runs [behind a reverse proxy](/p/docuwaves/pages/behind-a-reverse-proxy)
that does not pass the original host on.

## Signing in

After the password, the login screen asks for the second factor: a security
key if the account has one, otherwise the authenticator code. Links below it
switch to the other kinds the account has, including a recovery code.

The second step has five minutes. Wrong codes count against the same
limit as wrong passwords (10 per address and 30 per account in 15 minutes),
so a stolen password does not buy unlimited guesses at a six-digit
code.

## When somebody is locked out

An administrator can switch off another account's two-factor sign-in from
the **Accounts** panel: the shield button next to an account that has it.
That removes all of its keys, its app and its recovery codes and signs it out
everywhere; the password stays. The person signs in with the password and
sets 2FA up again. Your own account is managed from **Account** only, which
asks for your password.

If the only administrator is locked out, there is no other administrator to
do that. Remove the rows by hand, in the database:

```sql
DELETE FROM mfa_keys WHERE username = 'admin';
DELETE FROM mfa_totp WHERE username = 'admin';
DELETE FROM mfa_recovery_codes WHERE username = 'admin';
```

## What it does not cover

- **[Single sign-on](/p/docuwaves/pages/single-sign-on).** A login through your
  identity provider never asks for a second factor here. That is where 2FA
  belongs for an organisation: turned on once, at the provider, for every
  application. Asking again here would be a second prompt for the same
  person.
- **API tokens.** A token is already a credential that a signed-in account
  created and that can be revoked at any time; it has no interactive moment
  to ask in.
