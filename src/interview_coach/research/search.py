"""One public search for titles and links. Failure means the user should paste.

This does not log in anywhere, does not follow result pages, and drops sites
that sit behind a hiring login wall. Titles and URLs are the only fields kept.
"""

from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from urllib.error import HTTPError, URLError

from interview_coach.research.extract import AD_PATTERNS, extract_skills, looks_stale

BLOCKED_HOSTS = (
    "zhipin.com",
    "bosszhipin.com",
    "lagou.com",
    "linkedin.com",
    "nowcoder.com",
    "glassdoor.com",
)
_RESULT = re.compile(
    r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_SNIPPET = re.compile(
    r'class="result__snippet"[^>]*>(.*?)</(?:a|td|span|div)>',
    re.IGNORECASE | re.DOTALL,
)
_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class SearchHit:
    url: str
    title: str
    snippet: str = ""


class SearchUnavailable(RuntimeError):
    """The public search could not be used. The caller should offer --paste."""


def search_public(query: str, *, opener=None, timeout: float = 5.0) -> list[SearchHit]:
    """Fetch one result page. Raises SearchUnavailable instead of scraping a login wall."""
    text = " ".join(query.split())
    if not text:
        raise SearchUnavailable("empty query")
    target = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": text})
    request = urllib.request.Request(
        target,
        headers={
            "Accept": "text/html",
            "User-Agent": "interview-coach/research",
        },
        method="GET",
    )
    fetch = opener or urllib.request.urlopen
    try:
        with fetch(request, timeout=timeout) as response:
            raw = response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise SearchUnavailable("network unavailable") from exc
    if isinstance(raw, bytes):
        page = raw.decode("utf-8", errors="replace")
    else:
        page = str(raw)
    hits = filter_hits(parse_serp(page), today_year=_year_now())
    if not hits:
        raise SearchUnavailable("no usable public results")
    return hits


def parse_serp(page: str) -> list[SearchHit]:
    snippets = [_clean(match) for match in _SNIPPET.findall(page)]
    hits: list[SearchHit] = []
    for index, match in enumerate(_RESULT.findall(page)):
        url = _unwrap(html.unescape(match[0]))
        title = _clean(match[1])
        if not url or not title:
            continue
        snippet = snippets[index] if index < len(snippets) else ""
        hits.append(SearchHit(url=url, title=title[:160], snippet=snippet[:240]))
        if len(hits) == 8:
            break
    return hits


def filter_hits(hits: list[SearchHit], *, today_year: int) -> list[SearchHit]:
    kept: list[SearchHit] = []
    for hit in hits:
        if _blocked(hit.url):
            continue
        blob = f"{hit.title}\n{hit.snippet}"
        if any(pattern in blob for pattern in AD_PATTERNS):
            continue
        if looks_stale(blob, today_year):
            continue
        kept.append(hit)
    return kept


def skills_from_hits(hits: list[SearchHit], limit: int = 6):
    """Skills mentioned by two or more results. Snippets are not returned."""
    from interview_coach.research.extract import consistent_skills

    groups = [extract_skills(f"{hit.title}\n{hit.snippet}", limit=limit) for hit in hits]
    groups = [group for group in groups if group]
    return consistent_skills(groups, limit=limit)


def _blocked(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return any(host == blocked or host.endswith("." + blocked) for blocked in BLOCKED_HOSTS)


def _unwrap(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return query["uddg"][0]
    return url


def _clean(value: str) -> str:
    text = html.unescape(_TAG.sub("", value))
    return " ".join(text.split())


def _year_now() -> int:
    from datetime import date

    return date.today().year
