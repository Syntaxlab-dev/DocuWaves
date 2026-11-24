---
order: 12
published: true
title: A demo instance
---

A public instance anybody can sign in to and try, reset every night.
DocuWaves' own demo runs this way, and so can yours, for a team that wants
to try it before moving their documentation.

## Demo mode

`DEMO_MODE=1` with `DEMO_USERNAME` and `DEMO_PASSWORD` makes an instance a
demo:

- The **sign-in page shows the login** and fills it in. In a demo it is not
  a secret, it is the point.
- **Writing, publishing, importing a ZIP, versions, branding**, everything
  an author does, works as usual.
- **Switched off**, with a message saying so: changing the password,
  two-factor, accounts and API tokens (one visitor must not lock out the
  next), e-mail notifications (the demo would relay mail to any address),
  the [import from a Git URL](/p/docuwaves/pages/importing-from-a-git-repository)
  (it makes the server open connections) and docs-as-code syncs.

Never set `DEMO_MODE` on an instance with real documentation: the login is
shown to everyone.

## Reset every night

`deploy/demo/` in the repository has everything:

- `docker-compose.yml`: the demo, with its data in a volume of its own and
  the docs it starts with mounted from a folder (`DEMO_SEED`, for example a
  checkout of DocuWaves' `docs/`)
- `reset.sh`: deletes the data, pulls the latest image, starts the demo
  and fills it with `python -m app.cli demo-seed /seed`, which creates the
  demo account and imports the docs as a project
- `docuwaves-demo-reset.service` and `.timer`: run `reset.sh` every night
  at 03:00

```bash
sudo mkdir -p /opt/docuwaves-demo && cd /opt/docuwaves-demo
# copy the files from deploy/demo/ here, and the seed docs into ./seed
echo "DEMO_PASSWORD=try-docuwaves" > .env
./reset.sh
sudo cp docuwaves-demo-reset.* /etc/systemd/system/
sudo systemctl enable --now docuwaves-demo-reset.timer
```

Put a reverse proxy with HTTPS in front of port 8080, as for any instance.
The reset deletes the volume `demo-data`: keep this folder for the demo
only.
