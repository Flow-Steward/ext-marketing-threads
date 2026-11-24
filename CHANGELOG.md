# Changelog

## 0.1.0

First version.

- Everyday steps: Test connection, Get my profile, Get all my posts, Publish a post (text, image, video or carousel), Reply to a post, Get all replies to a post, Get post insights, Get account insights, Get publishing limits.
- A step for each of the 25 Threads API endpoints this release covers, built from the Threads documentation pages downloaded on 2026-11-23 (API version v1.0).
- An answer cut off before its end (fewer bytes than Content-Length, or a chunked answer that stops early) is never taken for a whole one: a read fails with `invalid_response`, a change has an unknown outcome. An empty answer where JSON is documented is `invalid_response`.
- Create media container with `media_type` TEXT and `auto_publish_text` true returns processing `completed` and `applied` true: Threads publishes such a post without the publish step.
