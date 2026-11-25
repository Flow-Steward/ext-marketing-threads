# Changelog

## 0.1.3

- The Setup Guide, API, API coverage, Changelog and Support pages open without choosing a project; only the pages that need one ask for it.

## 0.1.2 — 2026-11-24

- Every input has one readable label in every step; inputs that mean the same are described the same.
- New pages: a detailed Setup Guide (the Meta app, permissions, testers, getting and renewing the token, media, limits, errors), one page per area of the Threads API, and Threads API coverage with every step's endpoint, inputs and returned fields, generated from the pinned documentation.
- A detailed README with what you can automate.

## 0.1.1 — 2026-11-24

- The tests check the install folder from the extension id, not the checkout folder, so they pass in the repository's own checkout (v0.1.0 was tagged, but its release did not build).

## 0.1.0

First version.

- Everyday steps: Test connection, Get my profile, Get all my posts, Publish a post (text, image, video or carousel), Reply to a post, Get all replies to a post, Get post insights, Get account insights, Get publishing limits.
- A step for each of the 25 Threads API endpoints this release covers, built from the Threads documentation pages downloaded on 2026-11-23 (API version v1.0).
- An answer cut off before its end (fewer bytes than Content-Length, or a chunked answer that stops early) is never taken for a whole one: a read fails with `invalid_response`, a change has an unknown outcome. An empty answer where JSON is documented is `invalid_response`.
- Create media container with `media_type` TEXT and `auto_publish_text` true returns processing `completed` and `applied` true: Threads publishes such a post without the publish step.
- A carousel that stops after some of its containers were created fails with `timeout_unknown` and returns `created_container_ids` and `stage` (items created of all, carousel container not created, nothing published); unpublished containers expire after 24 hours.
