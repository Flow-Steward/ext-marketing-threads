# Threads integration for Flow Steward

<img src="icon.png" width="96" alt="Threads integration for Flow Steward">

[![CI](https://img.shields.io/github/actions/workflow/status/Flow-Steward/ext-marketing-threads/ci.yml?branch=main&label=CI)](https://github.com/Flow-Steward/ext-marketing-threads/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/Flow-Steward/ext-marketing-threads?label=release)](https://github.com/Flow-Steward/ext-marketing-threads/releases/latest)
[![Threads API](https://img.shields.io/badge/Threads%20API-v1.0-000000)](https://developers.facebook.com/documentation/threads/)
[![Steps](https://img.shields.io/badge/steps-34-blue)](#whats-inside)

Automate your Threads presence with Flow Steward workflows and AI agents — no code. Publish text, image, video and carousel posts on a schedule or when something happens, answer and moderate replies, follow mentions and keywords, and report how your posts and your account perform.

The extension works through Meta's Threads API. Every documented endpoint the API reference describes is a workflow step of its own, and everyday steps cover the common jobs: publishing, replies, insights and limits.

## What is this

[Threads](https://www.threads.com) is Meta's social network for sharing text, images and videos and joining public conversations. [Flow Steward](https://docs.flowsteward.org) runs workflows and AI agents that connect business systems.

This extension connects the two. Once installed, Threads appears in the Flow Steward workflow editor as a set of steps, and the same operations are available to AI agents as tools. Each connection is one Threads account, with the long-lived access token your Meta app issued for it; Flow Steward keeps the token encrypted and never shows it again.

## What you can automate

### Publishing

- **Announcements on every channel at once.** When a blog post, a release or a product launch goes live, publish a Threads post with its teaser and link — prepared by an earlier step or an AI agent.
- **Scheduled content calendar.** Publish the posts of an editorial calendar at the planned time, with topic tags, link previews, reply controls and location tags.
- **Image and video posts and carousels.** Publish images and videos from your website, CDN or public storage, or a carousel of 2 to 20 of them, with alternative text for each.
- **Reposts and quotes.** Repost a post or quote it with your own text.

### Community

- **Reply inbox.** Collect every reply to your posts — top-level or the whole conversation — for your support or community team, or for an AI agent that drafts answers.
- **Answer from a workflow.** Reply to a post or to another reply with text, an image or a video after review.
- **Moderation.** Hide replies that break your rules, and approve or ignore pending replies on posts with reply approvals.
- **Mentions.** Read the posts that mention your account and route them to the right person.

### Listening and research

- **Keyword search.** Find public posts about a keyword or topic, the most recent or the top ones, and pass them to an analysis step.
- **Public profiles.** Look up a public profile and read its recent posts.
- **Locations.** Search locations to tag in your posts.

### Reporting

- **Post performance.** Pull views, likes, replies, reposts, quotes and shares of each post into a weekly report.
- **Account growth.** Track followers, profile views and link clicks over time, and follower demographics by country, city, age or gender.
- **Limits.** See how much of the 24-hour publishing, reply, deletion and location-search limits is used before a large run.

## Why teams use it

- **Published means published.** **Publish a post** follows Threads' documented protocol: it creates the media container, checks that Threads has processed it and only then publishes. When a video takes longer, the step says so (`processing: accepted`) and names the container to publish later, instead of reporting a post that does not exist yet.
- **Carousels that stop cleanly.** If a carousel stops part way, the result lists the containers already created and the stage reached; nothing is published.
- **Changes are sent once.** Steps that change data are never retried automatically; when Threads' answer leaves the outcome unclear, the step says so and you check Threads before running it again.
- **Test runs publish nothing.** Publishing, replying, reposting, hiding and deleting are declared external effects, suppressed in test runs.
- **Long lists without gaps.** List steps read page after page and return the cursor to continue from exactly where they stopped.
- **Limits in view.** Every step returns the rate-limit usage Threads reports, and **Get publishing limits** shows the 24-hour limits.
- **Tokens stay secret.** The access token travels only in the request header and is removed from every answer, warning and error.

## What's inside

### Everyday steps

- **Test connection** — checks the connection and returns the account's username.
- **Get my profile** — name, username, biography, picture and verification.
- **Get all my posts** — every post of the account, page by page, optionally for a period.
- **Publish a post** — text, image, video or carousel, with topic, link preview, reply control and location.
- **Reply to a post** — a text, image or video reply to a post or to another reply.
- **Get all replies to a post** — top-level replies or the whole conversation.
- **Get post insights** and **Get account insights** — views, likes, replies, reposts, quotes, shares, clicks, followers and follower demographics.
- **Get publishing limits** — how much of the 24-hour limits is used.

### Threads API steps by area

- **Publishing** (5 steps) — create media containers, publish them, read a container's status, repost and delete posts.
- **Posts** (3 steps) — read a post, search posts by keyword, get a post's embed HTML.
- **Replies** (5 steps) — replies, conversations, hiding replies, pending replies and their approval.
- **Profiles** (8 steps) — the connected profile, its posts, replies, mentions and ghost posts, public profiles and their posts, and publishing limits.
- **Insights** (2 steps) — metrics of a post and of the account.
- **Locations** (2 steps) — search and read locations to tag.

The **Threads API coverage** page of the installed extension lists every step with the Threads endpoint it calls, the documentation page it comes from, its inputs and what it returns, and the documented endpoints that are not steps, with the reason.

### Pages in Flow Steward

- **Setup Guide** — the Meta app, permissions, testers, getting and renewing the token, media and limits, errors.
- **Connection** — the connection form and where the token comes from.
- **Threads API** and one page per area — every step with what it does.
- **Threads API coverage**, **Changelog**, **Support**.

## Get started

1. **Install the extension.** In Flow Steward open **Extensions → Catalog**, find **Threads** and install it.
2. **Create the Meta app.** In the [Meta App Dashboard](https://developers.facebook.com/apps/) create an app with the **Access the Threads API** use case and add the permissions your steps need.
3. **Get a long-lived token.** Authorize the Threads account in your app and exchange the token for a long-lived one, as Meta's [Get access tokens](https://developers.facebook.com/documentation/threads/get-started/get-access-tokens-and-permissions) and [Long-lived tokens](https://developers.facebook.com/documentation/threads/get-started/long-lived-tokens) guides describe.
4. **Connect it.** On the extension's **Connection** page enter a name, paste the token, save and press **Test connection**.
5. **Build your first workflow.** For example: *on a schedule* → **Publish a post** with text from an earlier step → *a day later* **Get post insights**.

The **Setup Guide** page of the extension walks through every screen.

## Requirements

- **A Threads account** and **a Meta app** with the Threads use case. Until Meta approves the app's permissions in App Review, it works for the accounts in the app's roles, such as Threads Testers.
- **A long-lived Threads user access token** that your Meta app issues. Meta's documentation makes it valid for 60 days; refresh it before then, as Meta describes, and save the new one in the connection.
- **The permissions the steps name:** `threads_basic` always, `threads_content_publish` to publish, `threads_read_replies` and `threads_manage_replies` for replies, `threads_manage_insights` for insights, `threads_delete` to delete, and `threads_keyword_search`, `threads_location_tagging`, `threads_manage_mentions` or `threads_profile_discovery` for the steps that name them.
- **Media at public addresses.** Threads downloads images and videos itself from a public address. Images JPEG or PNG up to 8 MB; videos MP4 or MOV up to 1 GB and 5 minutes.
- **Flow Steward** 0.9.23 or later.

## FAQ

**How do I schedule Threads posts automatically?**
Start a workflow on a schedule and end it with **Publish a post**. Earlier steps can prepare the text, pick an image address or ask for human approval.

**What happens with a video that takes long to process?**
The step checks the container's status once a minute for up to five minutes, as Threads recommends. If the video is still processing, the step returns `processing: accepted` with the container ID; publish it later with **Get media container status** and **Publish media container**.

**Can I post an image file produced by my workflow?**
Threads takes media from a public address, which it downloads itself. Put the file where Threads can reach it — your website, a CDN or public storage — and give that address.

**How long does an access token last?**
A long-lived token is valid for 60 days. Refresh it once it is at least a day old and before it expires, as Meta's guide describes, and save the new one in the connection.

**Can I try a workflow without posting?**
Yes. A test run of a workflow never publishes, replies, hides or deletes anything.

**Which Threads API operations are supported?**
Every endpoint of the Threads API reference has its own step, plus the everyday steps. The **Threads API coverage** page lists the documented endpoints handled outside workflow steps — the token endpoints, trending topics and the token debugger — and why.

## In your language

**Русский.** Интеграция Threads для Flow Steward автоматизирует присутствие в Threads без программирования: публикации текста, изображений, видео и каруселей по расписанию или по событию, ответы и модерация ответов, упоминания, поиск по ключевым словам и статистика публикаций и аккаунта. Для подключения нужно приложение Meta с вариантом использования Threads и долгосрочный токен доступа.

**Español.** La integración de Threads con Flow Steward automatiza tu presencia en Threads sin escribir código: publica publicaciones de texto, imagen, vídeo y carrusel, responde y modera respuestas, sigue menciones y palabras clave, y lee las estadísticas de tus publicaciones y de tu cuenta.

**Deutsch.** Die Threads-Integration für Flow Steward automatisiert Ihre Präsenz auf Threads ohne Programmierung: Text-, Bild-, Video- und Karussell-Beiträge veröffentlichen, Antworten beantworten und moderieren, Erwähnungen und Stichwörter verfolgen und die Statistiken von Beiträgen und Konto lesen.

**Français.** L'intégration Threads pour Flow Steward automatise votre présence sur Threads sans code : publications de texte, d'images, de vidéos et de carrousels, réponses et modération, mentions et mots-clés, statistiques des publications et du compte.

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
