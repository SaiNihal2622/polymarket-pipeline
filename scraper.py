from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

import feedparser
import httpx

import config

log = logging.getLogger(__name__)


@dataclass
class NewsItem:
    headline: str
    source: str
    url: str
    published_at: datetime
    summary: str = ""

    def age_hours(self) -> float:
        delta = datetime.now(timezone.utc) - self.published_at
        return delta.total_seconds() / 3600


def scrape_rss(feed_url: str, lookback_hours: int) -> list[NewsItem]:
    """Parse a single RSS feed and return recent items."""
    items = []
    try:
        feed = feedparser.parse(feed_url)
    except Exception:
        return items

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    source_name = feed.feed.get("title", feed_url)

    for entry in feed.entries:
        published = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            published = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
        else:
            published = datetime.now(timezone.utc)

        if published < cutoff:
            continue

        items.append(NewsItem(
            headline=entry.get("title", "").strip(),
            source=source_name,
            url=entry.get("link", ""),
            published_at=published,
            summary=entry.get("summary", "")[:500],
        ))

    return items


def scrape_newsapi(query: str, lookback_hours: int) -> list[NewsItem]:
    """Pull from NewsAPI.org if key is configured."""
    if not config.NEWSAPI_KEY:
        return []

    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    from_dt = cutoff.strftime("%Y-%m-%dT%H:%M:%S")

    try:
        resp = httpx.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "from": from_dt,
                "sortBy": "publishedAt",
                "language": "en",
                "pageSize": 100,
                "apiKey": config.NEWSAPI_KEY,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return items

    for article in data.get("articles", []):
        pub_str = article.get("publishedAt", "")
        try:
            published = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            published = datetime.now(timezone.utc)

        items.append(NewsItem(
            headline=article.get("title", "").strip(),
            source=article.get("source", {}).get("name", "NewsAPI"),
            url=article.get("url", ""),
            published_at=published,
            summary=(article.get("description") or "")[:500],
        ))

    return items


def scrape_reddit(subreddits: list[str], lookback_hours: int) -> list[NewsItem]:
    """
    Scrape Reddit's JSON API (no auth required).
    Returns top/new posts from specified subreddits.
    """
    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    headers = {"User-Agent": "polymarket-pipeline/3.0 (research bot)"}

    for sub in subreddits:
        for sort in ("new", "hot"):
            try:
                resp = httpx.get(
                    f"https://www.reddit.com/r/{sub}/{sort}.json",
                    params={"limit": 25, "t": "day"},
                    headers=headers,
                    timeout=10,
                    follow_redirects=True,
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
                posts = data.get("data", {}).get("children", [])
                for post in posts:
                    p = post.get("data", {})
                    # Skip self-posts without meaningful titles, stickied posts
                    if p.get("stickied") or p.get("is_meta"):
                        continue
                    title = p.get("title", "").strip()
                    if not title or len(title) < 15:
                        continue
                    created = p.get("created_utc", 0)
                    published = datetime.fromtimestamp(created, tz=timezone.utc)
                    if published < cutoff:
                        continue
                    items.append(NewsItem(
                        headline=title,
                        source=f"Reddit/r/{sub}",
                        url=f"https://reddit.com{p.get('permalink', '')}",
                        published_at=published,
                        summary=p.get("selftext", "")[:300],
                    ))
                time.sleep(0.3)
            except Exception as e:
                log.debug(f"[reddit] r/{sub}/{sort} failed: {e}")
                continue

    return items


def scrape_hackernews(lookback_hours: int) -> list[NewsItem]:
    """
    Scrape Hacker News via Algolia API (no auth, free).
    Returns recent tech/AI/finance stories.
    """
    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    cutoff_ts = int(cutoff.timestamp())

    try:
        resp = httpx.get(
            "https://hn.algolia.com/api/v1/search_by_date",
            params={
                "tags": "story",
                "numericFilters": f"created_at_i>{cutoff_ts}",
                "hitsPerPage": 50,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        for hit in data.get("hits", []):
            title = (hit.get("title") or "").strip()
            if not title or len(title) < 15:
                continue
            created_ts = hit.get("created_at_i", 0)
            published = datetime.fromtimestamp(created_ts, tz=timezone.utc)
            items.append(NewsItem(
                headline=title,
                source="Hacker News",
                url=hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                published_at=published,
                summary="",
            ))
    except Exception as e:
        log.debug(f"[hackernews] failed: {e}")

    return items


def scrape_cryptopanic(lookback_hours: int) -> list[NewsItem]:
    """
    Scrape CryptoPanic via their public RSS feed (no auth required).
    Returns crypto-specific news headlines.
    """
    # Use public RSS — no API key needed
    rss_feeds = [
        "https://cryptopanic.com/news/rss/",
        "https://cryptopanic.com/news/bitcoin/rss/",
        "https://cryptopanic.com/news/ethereum/rss/",
    ]
    items = []
    for feed_url in rss_feeds:
        try:
            fetched = scrape_rss(feed_url, lookback_hours)
            for item in fetched:
                item.source = "CryptoPanic"
            items.extend(fetched)
        except Exception as e:
            log.debug(f"[cryptopanic] {feed_url} failed: {e}")
    return items


def scrape_twitter(lookback_hours: int) -> list[NewsItem]:
    """Pull tweets from Twitter API v2 if bearer token is configured."""
    if not config.TWITTER_BEARER_TOKEN:
        return []

    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    start_time = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    query_parts = [f'"{kw}"' for kw in config.TWITTER_KEYWORDS[:10]]
    query = "(" + " OR ".join(query_parts) + ") lang:en -is:retweet"

    try:
        resp = httpx.get(
            "https://api.twitter.com/2/tweets/search/recent",
            params={
                "query": query,
                "start_time": start_time,
                "max_results": 50,
                "tweet.fields": "created_at,text",
            },
            headers={"Authorization": f"Bearer {config.TWITTER_BEARER_TOKEN}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return items

    for tweet in data.get("data", []):
        try:
            published = datetime.fromisoformat(tweet["created_at"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            published = datetime.now(timezone.utc)

        items.append(NewsItem(
            headline=tweet.get("text", "")[:200].strip(),
            source="Twitter",
            url=f"https://twitter.com/i/web/status/{tweet.get('id', '')}",
            published_at=published,
            summary="",
        ))

    return items


def scrape_telegram(lookback_hours: int) -> list[NewsItem]:
    """Pull recent Telegram channel messages if configured."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHANNEL_IDS:
        return []

    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    for channel_id in config.TELEGRAM_CHANNEL_IDS:
        try:
            resp = httpx.get(
                f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates",
                params={"chat_id": channel_id, "limit": 50},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            continue

        for update in data.get("result", []):
            msg = update.get("message") or update.get("channel_post") or {}
            text = (msg.get("text") or msg.get("caption") or "").strip()
            if not text or len(text) < 20:
                continue

            ts = msg.get("date", 0)
            published = datetime.fromtimestamp(ts, tz=timezone.utc)
            if published < cutoff:
                continue

            items.append(NewsItem(
                headline=text[:200],
                source=f"Telegram/{channel_id}",
                url="",
                published_at=published,
                summary="",
            ))

    return items


def deduplicate(items: list[NewsItem]) -> list[NewsItem]:
    """Remove near-duplicate headlines by normalized prefix matching."""
    seen = set()
    unique = []
    for item in items:
        key = item.headline.lower()[:80]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


# Subreddits mapped to market categories
_REDDIT_SUBS = [
    # Crypto
    "CryptoCurrency", "Bitcoin", "ethereum", "solana",
    # Finance / stocks
    "wallstreetbets", "stocks", "investing", "SecurityAnalysis",
    # Sports
    "nba", "soccer", "cricket", "tennis", "nfl",
    # Politics / world
    "worldnews", "politics", "geopolitics",
    # Tech / AI
    "technology", "artificial", "MachineLearning", "singularity",
    # Entertainment
    "movies", "entertainment",
]


def scrape_all(lookback_hours: int | None = None) -> list[NewsItem]:
    """Run all scrapers and return deduplicated, sorted results."""
    hours = lookback_hours or config.NEWS_LOOKBACK_HOURS
    all_items: list[NewsItem] = []

    # 1. RSS feeds (primary — fastest, most reliable)
    for feed_url in config.RSS_FEEDS:
        try:
            all_items.extend(scrape_rss(feed_url, hours))
        except Exception:
            pass
        time.sleep(0.2)

    # 2. Reddit (free, no auth — covers sports/crypto/finance/AI well)
    try:
        reddit_items = scrape_reddit(_REDDIT_SUBS, hours)
        all_items.extend(reddit_items)
    except Exception as e:
        log.debug(f"[reddit] scrape_all failed: {e}")

    # 3. Hacker News (tech/AI/startups — covers AI market questions well)
    try:
        all_items.extend(scrape_hackernews(hours))
    except Exception as e:
        log.debug(f"[hackernews] failed: {e}")

    # 4. CryptoPanic (crypto-specific — helps Bitcoin/Ethereum markets)
    try:
        all_items.extend(scrape_cryptopanic(hours))
    except Exception as e:
        log.debug(f"[cryptopanic] failed: {e}")

    # 5. Twitter API v2 (if configured)
    try:
        all_items.extend(scrape_twitter(hours))
    except Exception as e:
        log.debug(f"[twitter] failed: {e}")

    # 6. Telegram (if configured)
    try:
        all_items.extend(scrape_telegram(hours))
    except Exception as e:
        log.debug(f"[telegram] failed: {e}")

    # 7. NewsAPI (if configured — broad coverage)
    if config.NEWSAPI_KEY:
        try:
            all_items.extend(scrape_newsapi(
                "AI OR crypto OR Bitcoin OR NBA OR soccer OR election OR Fed OR IPL OR tariff", hours
            ))
        except Exception as e:
            log.debug(f"[newsapi] failed: {e}")

    unique = deduplicate(all_items)
    unique.sort(key=lambda x: x.published_at, reverse=True)
    return unique


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    items = scrape_all()
    print(f"\n--- Scraped {len(items)} unique headlines ---\n")
    by_source: dict[str, int] = {}
    for item in items:
        src = item.source.split(":")[0][:30]
        by_source[src] = by_source.get(src, 0) + 1
    for src, count in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"  {count:3d}  {src}")
    print()
    for item in items[:30]:
        age = item.age_hours()
        print(f"  [{age:.1f}h] [{item.source[:25]}] {item.headline[:80]}")
