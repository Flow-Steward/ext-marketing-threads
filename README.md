# Threads integration for Flow Steward

<img src="icon.png" width="96" alt="Threads integration for Flow Steward">

[![CI](https://img.shields.io/github/actions/workflow/status/Flow-Steward/ext-marketing-threads/ci.yml?branch=main&label=CI)](https://github.com/Flow-Steward/ext-marketing-threads/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/Flow-Steward/ext-marketing-threads?label=release)](https://github.com/Flow-Steward/ext-marketing-threads/releases/latest)

Automate your Threads presence with Flow Steward workflows and AI agents: publish posts and replies, moderate replies and track insights — without writing code.

This Flow Steward extension is a Threads integration for social media automation. It works through the Threads API from Meta, publishes text, image, video and carousel posts on schedule or on events, brings replies and mentions into your workflows and reports how your posts perform.

## What is this

Threads is Meta's social network for sharing text, images and videos and joining public conversations. This extension is a connector: it adds ready Threads steps to the Flow Steward workflow editor and the same operations as tools for AI agents. Read more about Flow Steward at <https://docs.flowsteward.org>.

## What you can automate

- Publish an announcement, a blog teaser or a product launch on Threads as soon as an earlier step prepares the text and images.
- Post a carousel of up to 20 images and videos from your website or CDN.
- Collect every reply to a post for your support or community team, and answer them from a workflow.
- Hide replies that break your rules, or approve pending replies on posts with reply approvals.
- Pull views, likes, replies, reposts and quotes of your posts into a weekly report.
- Watch your follower count and link clicks over time.
- Find public posts about a keyword or topic.

## Why teams use it

- **Published means published.** **Publish a post** follows Threads' documented protocol: it creates the media container, checks that Threads has processed it and only then publishes. When Threads is still processing a video, the step says so (`processing` `accepted`) and names the container to publish later, instead of reporting a post that does not exist yet.
- **A change is not sent twice.** Steps that change data are never retried automatically; when Threads' answer leaves the outcome unclear, the step says so and you check Threads before running it again.
- **A test run publishes nothing.** Publishing, replying, reposting, hiding and deleting are declared external effects, and Flow Steward suppresses them in test runs.
- **Long lists without gaps.** List steps read page after page; when the step output is full they stop on a whole page and return the cursor to continue from exactly there.
- **Limits in view.** **Get publishing limits** shows how much of the 24-hour posting, reply, deletion and location-search limits is used, and every step returns the rate-limit usage Threads reports.
- **Tokens stay secret.** Flow Steward encrypts and keeps the access token; it travels only in the request header and is removed from every answer, warning and error.

## What's inside

Everyday steps:

- **Test connection** — checks the connection and returns the account's username.
- **Get my profile** — name, username, biography, picture and verification.
- **Get all my posts** — every post of the account, page by page, optionally for a period.
- **Publish a post** — text, image, video or carousel, with topic, link preview, reply control and location.
- **Reply to a post** — a text, image or video reply to a post or to another reply.
- **Get all replies to a post** — top-level replies or the whole conversation.
- **Get post insights** and **Get account insights** — views, likes, replies, reposts, quotes, shares, clicks, followers and follower demographics.
- **Get publishing limits** — how much of the 24-hour limits is used.

Each of the 25 Threads API endpoints this release covers is also a step of its own: media containers and publishing, reposts and deletion, posts and keyword search, replies, conversations and reply moderation, profiles, mentions and public profiles, locations, insights and embedding. The extension's **Coverage** page lists the documented endpoints that are not steps, and why.

## Get started

1. In Flow Steward, open **Extensions → Catalog**, find **Threads** and install it.
2. In the [Meta App Dashboard](https://developers.facebook.com/apps/), create an app with the **Access the Threads API** use case and add the permissions your steps need.
3. Authorize the Threads account in your app and get a long-lived user access token, as Meta's [Get access tokens](https://developers.facebook.com/documentation/threads/get-started/get-access-tokens-and-permissions) and [Long-lived tokens](https://developers.facebook.com/documentation/threads/get-started/long-lived-tokens) guides describe.
4. On the extension's **Connection** page, create a connection, paste the long-lived access token, then press **Test connection**.
5. Build your first workflow: for example, on a schedule → **Publish a post** with text from an earlier step → **Get post insights** a day later.

## Requirements

- A Threads account and a Meta app with the Threads use case. Until Meta approves the app's permissions, it works only for the accounts added to the app as Threads testers.
- A long-lived Threads user access token, which you obtain yourself in your Meta app. Per Meta's documentation it is valid for 60 days; you renew it yourself, as Meta describes, and save the new one in the connection. The extension's steps never issue or renew tokens.
- The permissions the steps name: `threads_basic` always, `threads_content_publish` to publish, `threads_read_replies` and `threads_manage_replies` for replies, `threads_manage_insights` for insights, `threads_delete` to delete, and `threads_keyword_search`, `threads_location_tagging`, `threads_manage_mentions` or `threads_profile_discovery` for the steps that name them.
- Images and videos at public URLs: Threads takes media only from a public URL, which it downloads itself, so a workflow file must first be published at a public URL. Images JPEG or PNG up to 8 MB; videos MP4 or MOV up to 1 GB and 5 minutes.
- Flow Steward 0.9.23 or later.

## FAQ

**How do I schedule Threads posts automatically?**
Start a workflow on a schedule and end it with **Publish a post**. Earlier steps can prepare the text, pick an image address or ask for human approval.

**What happens with a video that takes long to process?**
The step checks the container's status once a minute for up to five minutes, as Threads recommends. If the video is still processing, the step returns `processing` `accepted` with the container ID; publish it later with **Get media container status** and **Publish media container**.

**Can I upload an image file from my workflow?**
Threads accepts media only from a public address, which it downloads itself; put the file where Threads can reach it and give that address.

**Can I try a workflow without posting?**
Yes. A test run of a workflow never publishes, replies, hides or deletes anything.

**Which Threads API operations are supported?**
Every endpoint of the Threads API reference except the debugger of access tokens, each as its own step, plus the everyday steps. The **Coverage** page lists the endpoints that are not steps (handling of tokens, trending topics, the debugger) and why.

## In your language

La integración de Threads con Flow Steward automatiza tu presencia en Threads sin escribir código. La extensión usa la API de Threads de Meta: publica publicaciones de texto, imagen, vídeo y carrusel, responde y modera respuestas, y lee las estadísticas de tus publicaciones y de tu cuenta. Para la conexión necesitas una app de Meta con el caso de uso de Threads y una credencial de acceso de larga duración (token).

## Links

- Flow Steward documentation: <https://docs.flowsteward.org>
- Flow Steward extension catalog: <https://github.com/Flow-Steward/extensions>
- Issues and support: <https://github.com/Flow-Steward/ext-marketing-threads/issues>
- Threads API documentation: <https://developers.facebook.com/documentation/threads/>
- Changes: [CHANGELOG.md](CHANGELOG.md)

## For developers

Threads publishes no machine-readable specification. Every generated step comes from facts extracted from its documentation pages (`tests/reference/threads_api.json`, pages downloaded 2026-11-23, each pinned by SHA-256 in `tests/reference/pins.json`). To rebuild, download the pages listed in `tests/reference/extract_reference.py` to `tests/reference/sources/` (not committed), then:

```bash
python3 tests/reference/extract_reference.py
python3 tests/reference/build_contracts.py
```

A read-only test against the real API runs when `THREADS_TOKEN_FILE` names a file holding a token.

From a Flow Steward checkout (the checks run in the `fs-audit` container):

```bash
./core/entrypoints/cli/scripts/lint.sh --checks extension-static,extension-tests --extension-root "$PWD/workspace/extensions/flowsteward_threads"
./flow-steward extensions validate flowsteward.threads --root workspace/extensions --health --marketplace
./flow-steward extensions test flowsteward.threads --root workspace/extensions
```

Threads and its marks belong to Meta Platforms, Inc.; see [BRANDING.md](BRANDING.md) for the icon's source.
