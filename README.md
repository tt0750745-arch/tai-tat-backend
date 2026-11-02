# Tải tất — Render backend (ready to deploy, not deployed yet)

Prepared for https://tiendopay.tt0750745.workers.dev . No paid service is required by the configuration.

## Deploy

1. Put this folder at the root of a Git repository accessible to Render.
2. Create ONE Render Web Service: runtime Docker, plan **free**, Dockerfile `./Dockerfile`, context `.`, health endpoint `/health`.
3. Set `API_KEY` to a randomly generated secret of at least 32 characters. With a Blueprint, `render.yaml` generates this automatically.
4. Wait for a successful deploy and confirm `/health` returns `ok: true, ready: true`.
5. In the existing Cloudflare Worker, set `BACKEND_URL` to the returned service URL and `BACKEND_KEY` to the same secret. Never put the shared key in HTML, browser storage or a source repository.
6. Add `renderGateway()` from worker-gateway.mjs to the Worker's fetch handler before generic API routing. Add a button enabled only when `/api/server/ready` reports `enabled`.

## Browser contract

- POST `/api/server/jobs` JSON `{ "url": "https://..." }` returns an opaque `id` and `ticket`.
- Poll GET `/api/server/status?id=...&ticket=...` every 3–5 seconds until `state` is `done` or `error`.
- On `done`, show a normal download link to `/api/server/file?id=...&ticket=...`.
- Keep id/ticket only in page memory. Stop polling when the page is closed or after 4 minutes.
- Do not send a platform password, cookie, or shared API_KEY to the browser.

## Limits

One active download, no playlists, at most 10-minute media, 720p selection, final file <=50 MiB, 180-second job deadline, temporary files expire after 15 minutes and are removed at the next request. Maximum 10 retained jobs. Render may also erase files on sleep/restart. No persistent disk or paid add-on is configured.

Render Free sleeps after 15 idle minutes. The next request can take roughly a minute to wake it. Bandwidth and outbound-traffic limits still apply. Never bypass Free sleep by artificial keepalive requests.

## Runtime

Python 3.12, Node.js 24, FFmpeg from Debian Bookworm and yt-dlp[default] 2026.10.26. FFmpeg is used for local merge operations. No user cookies; known platform URLs only; child downloader rejects connections to private/non-global IP addresses. Input is passed through an argument array, never a shell command. Authentication is mandatory for job and download endpoints. Health is public.

This does not guarantee YouTube/TikTok access from Render's IP addresses. Platform blocking or a need for sign-in is reported as an error, not bypassed.

## Validation completed

`python3 -m unittest -v test_app.py` — 4 tests pass, covering authorization, denied URLs, one-job limit, job tickets, download headers and expiry cleanup.
Python source compiles. The Docker image has NOT been built or run in this session. Real yt-dlp download and FFmpeg merge must be verified on the deployed Render service before announcing platform support.

## Open source

- yt-dlp: https://github.com/yt-dlp/yt-dlp , Unlicense for core with third-party licenses documented upstream.
- FFmpeg: https://ffmpeg.org/legal.html (Debian package license applies).
- Node.js: https://github.com/nodejs/node/blob/main/LICENSE .
The container installs official upstream/runtime packages; it does not redistribute binaries in this ZIP.
