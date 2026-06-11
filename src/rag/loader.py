"""Loader: fetches raw Stripe documentation pages over HTTP."""

import asyncio
import json
import logging
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

LLMS_TXT_URL = "https://docs.stripe.com/llms.txt"
OUTPUT_PATH = Path("data/stripe_docs.jsonl")
_CONCURRENCY = 20
_TIMEOUT = 30.0

# Marker injected by fetch_all_docs to delimit doc boundaries in the
# assembled string. The stripe-doc-start prefix is chosen to be
# unambiguous — it cannot appear as normal Markdown prose.
_DOC_MARKER = "<!-- stripe-doc-start: {url} -->"
_DOC_MARKER_RE = re.compile(r"<!-- stripe-doc-start: ([^>]+) -->")

# Extracts (title, url) pairs from llms.txt list items:
#   - [Title](https://docs.stripe.com/path.md)
_INDEX_URL_RE = re.compile(
    r"\[([^\]]+)\]\((https://docs\.stripe\.com/[^)]+\.md)\)"
)


def fetch_stripe_docs(url: str) -> str:
    """GET url (llms.txt index), raise on non-200 or empty body."""
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(url)
    if resp.status_code != 200:
        raise RuntimeError(
            f"fetch_stripe_docs: HTTP {resp.status_code} from {url}"
        )
    text = resp.text
    if not text.strip():
        raise ValueError("Empty response from Stripe")
    print(f"Fetched {len(text)} bytes from {url}")
    return text


async def _fetch_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    url: str,
) -> tuple[str, str]:
    async with sem:
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                log.warning("skip %s — HTTP %d", url, resp.status_code)
                return url, ""
            return url, resp.text
        except httpx.TimeoutException:
            log.warning("skip %s — timed out", url)
            return url, ""
        except Exception as exc:
            log.warning("skip %s — %s", url, exc)
            return url, ""


async def _async_fetch_all(index: str) -> str:
    pairs = list(dict.fromkeys(_INDEX_URL_RE.findall(index)))  # dedup, order-stable
    urls = [url for _, url in pairs]
    print(f"Discovered {len(urls)} doc URLs")
    print(f"Fetching {len(urls)} docs in parallel (concurrency={_CONCURRENCY})…")

    sem = asyncio.Semaphore(_CONCURRENCY)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        results = await asyncio.gather(
            *[_fetch_one(client, sem, url) for url in urls]
        )

    parts: list[str] = []
    failed = 0
    for url, body in results:
        if body:
            parts.append(f"{_DOC_MARKER.format(url=url)}\n{body}")
        else:
            failed += 1

    print(f"Fetched {len(parts)} docs ({failed} failed/skipped)")
    return "\n\n".join(parts)


def fetch_all_docs(index: str) -> str:
    """Parse URLs from llms.txt index, batch-fetch each .md, return assembled string."""
    return asyncio.run(_async_fetch_all(index))


def parse_llms_txt(raw: str) -> Iterator[dict]:
    """Parse assembled doc string into records.

    Format observed (https://docs.stripe.com/llms.txt + individual .md files):
    - llms-full.txt (spec URL) returns HTTP 404; Stripe publishes llms.txt
      (an index) and per-path *.md files instead.
    - Individual .md files: no frontmatter, first line is "# Title", pure Markdown.
    - fetch_all_docs assembles them with <!-- stripe-doc-start: URL --> markers
      so this function can remain a pure string parser with no network calls.

    Yields dicts with keys: url, title, content.
    Drops records with missing url, missing title, or content < 50 chars.
    """
    # re.split with a capturing group keeps the captured text in the result list:
    # [preamble, url1, body1, url2, body2, ...]
    parts = _DOC_MARKER_RE.split(raw)

    # parts[0] is text before the first marker (discard); then alternating url/body
    for i in range(1, len(parts) - 1, 2):
        url = parts[i].strip()
        body = parts[i + 1]

        if not url or not url.startswith("https://docs.stripe.com"):
            log.warning("drop record — missing or non-Stripe url")
            continue

        # Extract title from first H1 line
        title_match = re.search(r"^# (.+)$", body, re.MULTILINE)
        if not title_match:
            log.warning("drop %s — no H1 title found", url)
            continue
        title = title_match.group(1).strip()

        content = body.strip()
        if len(content) < 50:
            log.warning("drop %s — content too short (%d chars)", url, len(content))
            continue

        yield {"url": url, "title": title, "content": content}


def save_jsonl(docs: Iterable[dict], path: Path) -> int:
    """Write docs to path as JSONL, one record per line. Returns count written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as fh:
        for doc in docs:
            fh.write(json.dumps(doc, ensure_ascii=False) + "\n")
            count += 1
    return count


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )
    raw_index = fetch_stripe_docs(LLMS_TXT_URL)
    full_raw = fetch_all_docs(raw_index)
    docs = parse_llms_txt(full_raw)
    n = save_jsonl(docs, OUTPUT_PATH)
    print(f"Wrote {n} docs to {OUTPUT_PATH}")
