from datetime import datetime, timedelta, timezone
import feedparser
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from collections import defaultdict
import re

from telegram.ext import (
    ContextTypes,
)


def fetch_rss_news(topic, location="US", language="en") -> list:
    query = topic.replace(" ", "+")
    url = f"https://news.google.com/rss/search?q={query}&hl={language}&gl={location}&ceid={location}:{language}"
    feed = feedparser.parse(url)
    return feed.entries


def fetch_recent_news(topic, location="US", language="en"):
    feeds = []
    seen_links = set()

    for loc, lang in [(location, language), ("US", language), (location, "en")]:
        entries = fetch_rss_news(topic, location=loc, language=lang)

        for entry in entries:
            link = entry.get("link", "")
            if link and link not in seen_links:
                seen_links.add(link)
                feeds.append(entry)

    return feeds


def preprocess_title(title):
    """Basic preprocessing for multilingual text"""
    title = re.sub(r"\s+", " ", title).strip()
    title = title.lower()
    return title


def cluster_news_titles(feeds, similarity_threshold=0.5):
    """Cluster news titles using sentence transformers and agglomerative clustering."""
    if not feeds:
        return {}

    try:

        titles = [entry.get("title", "") for entry in feeds]

        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

        # logger.info("Generating embeddings...")
        embeddings = model.encode(titles, show_progress_bar=False)

        similarity_matrix = cosine_similarity(embeddings)
        distance_matrix = 1 - similarity_matrix

        clustering = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=1 - similarity_threshold,
            metric="precomputed",
            linkage="average",
        )

        labels = clustering.fit_predict(distance_matrix)

        clusters = defaultdict(list)

        for idx, label in enumerate(labels):
            cluster_info = {
                "title": feeds[idx].get("title", ""),
                "link": feeds[idx].get("link", ""),
                "published": feeds[idx].get("published", ""),
                "source": feeds[idx].get("source", {}).get("title", "Unknown"),
            }
            clusters[int(label)].append(cluster_info)

        return dict(clusters)

    except ImportError:
        # logger.warning("sentence-transformers not installed. Using TF-IDF fallback.")
        return cluster_news_titles_tfidf(feeds, similarity_threshold)


def cluster_news_titles_tfidf(feeds, similarity_threshold=0.5):
    """Fallback clustering using TF-IDF with word n-grams."""
    if not feeds:
        return {}

    from sklearn.cluster import AgglomerativeClustering

    titles = [preprocess_title(entry.get("title", "")) for entry in feeds]

    vectorizer = TfidfVectorizer(
        ngram_range=(1, 3),
        min_df=1,
        max_df=0.8,
        lowercase=True,
        stop_words=None,
        token_pattern=r"(?u)\b\w+\b",
    )

    tfidf_matrix = vectorizer.fit_transform(titles)
    similarity_matrix = cosine_similarity(tfidf_matrix)
    distance_matrix = 1 - similarity_matrix

    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=1 - similarity_threshold,
        metric="precomputed",
        linkage="average",
    )

    labels = clustering.fit_predict(distance_matrix)

    clusters = defaultdict(list)

    for idx, label in enumerate(labels):
        cluster_info = {
            "title": feeds[idx].get("title", ""),
            "link": feeds[idx].get("link", ""),
            "published": feeds[idx].get("published", ""),
            "source": feeds[idx].get("source", {}).get("title", "Unknown"),
        }
        clusters[int(label)].append(cluster_info)

    return dict(clusters)


def escape_markdown_v2(text):
    """Escape special characters for Telegram MarkdownV2."""
    # Characters that need to be escaped in MarkdownV2
    special_chars = [
        "_",
        "*",
        "[",
        "]",
        "(",
        ")",
        "~",
        "`",
        ">",
        "#",
        "+",
        "-",
        "=",
        "|",
        "{",
        "}",
        ".",
        "!",
    ]

    for char in special_chars:
        text = text.replace(char, f"\\{char}")

    return text


def format_clusters_for_telegram(clusters, max_clusters=10):
    """Format clusters for Telegram message in MarkdownV2 (respects 4096 char limit)"""
    messages = []

    sorted_clusters = sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True)
    multi_article_clusters = [
        (arts[0]["title"], arts) for cid, arts in sorted_clusters if len(arts) > 1
    ]
    single_article_cluster = [
        arts[0] for cid, arts in sorted_clusters if len(arts) == 1
    ]

    if not multi_article_clusters:
        return ["No clustered news found\\."]

    # Header message
    # header = f"🔍 *Found {len(multi_article_clusters)} news clusters*\n\n"
    # now = datetime.now().strftime("%d-%m-%Y")
    # header = f"🗞 *News Clusters for {escape_markdown_v2(now)}*\n\n"
    header = ""
    current_message = header

    for _, (cluster_title, articles) in enumerate(
        multi_article_clusters[:max_clusters], 1
    ):
        # Use the first (presumably most representative) article title as cluster title
        cluster_title = cluster_title[:120]  # Limit length
        cluster_title_escaped = escape_markdown_v2(cluster_title)

        # Build cluster section
        cluster_text = f"*{cluster_title_escaped}*\n\n"
        # cluster_text += f"_{len(articles)} related articles_\n\n"

        # Add related articles (skip first one as it's the title)
        for _, article in enumerate(articles[:5], 1):
            title = article["title"][:100]  # Truncate long titles
            title_escaped = escape_markdown_v2(title)

            # Clean and escape URL
            url = article["link"].strip()
            # URLs in MarkdownV2 links don't need escaping inside the parentheses

            # Escape source name
            source = escape_markdown_v2(article["source"][:30])

            # Format: • Title - Source
            cluster_text += f"  • [{title_escaped}]({url})\n"
            cluster_text += f"    _via {source}_\n\n"

        # Add "more articles" note if needed
        if len(articles) > 5:
            remaining = len(articles) - 5
            cluster_text += f"  _\\.\\.\\.and {remaining} more related articles_\n\n"

        cluster_text += "─" * 35 + "\n\n"

        # Check message length (Telegram limit is 4096, leave buffer)
        if len(current_message + cluster_text) > 3900:
            messages.append(current_message)
            current_message = header + cluster_text
        else:
            current_message += cluster_text

    # Add single article clusters at the end
    if single_article_cluster:
        single_title_escaped = escape_markdown_v2("Mixed Articles")

        single_text = f"*{single_title_escaped}*\n\n"

        for _, article in enumerate(single_article_cluster[:10], 1):
            title = article["title"][:100]  # Truncate long titles
            title_escaped = escape_markdown_v2(title)

            url = article["link"].strip()
            source = escape_markdown_v2(article["source"][:30])

            single_text += f"  • [{title_escaped}]({url})\n"
            single_text += f"    _via {source}_\n\n"

        if len(single_article_cluster) > 10:
            remaining = len(single_article_cluster) - 10
            single_text += f"  _\\.\\.\\.and {remaining} more articles_\n\n"

        single_text += "─" * 35 + "\n\n"

        if len(current_message + single_text) > 3900:
            messages.append(current_message)
            current_message = header + single_text
        else:
            current_message += single_text

    # Add final message
    if current_message and current_message != header:
        messages.append(current_message)

    # Add summary footer to last message
    # if messages:
    #     single_clusters = [c for c in sorted_clusters if len(c[1]) == 1]
    #     if single_clusters:
    #         footer = (
    #             f"\n💡 _{len(single_clusters)} unique articles not grouped with others_"
    #         )

    #         # Check if footer fits in last message
    #         if len(messages[-1] + footer) < 4000:
    #             messages[-1] += footer
    #         else:
    #             messages.append(footer)

    return messages if messages else ["No news found for your query\\."]


def filter_recent_news(feeds: list) -> list:
    now = datetime.now(timezone.utc)
    two_days_ago = now - timedelta(days=2)
    recent_feeds = [
        entry
        for entry in feeds
        if "published_parsed" in entry
        and datetime(*entry.published_parsed[:6], tzinfo=timezone.utc) > two_days_ago
    ]
    return recent_feeds


async def process_and_send_news(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    topic: str,
    location: str,
    language: str,
):
    """Process news request and send results."""
    try:
        # logger.info(
        #     f"Processing news for chat_id={chat_id}: topic={topic}, location={location}, language={language}"
        # )

        feeds = fetch_recent_news(topic, location=location, language=language)

        if not feeds:
            await context.bot.send_message(
                chat_id=chat_id, text="❌ No news articles found for your query\\."
            )
            return

        await context.bot.send_message(
            chat_id=chat_id,
            text="✅ Fetched articles. Analyzing...",
        )

        # Filter articles from last 48 hours
        recent_feeds = filter_recent_news(feeds)

        clusters = cluster_news_titles(recent_feeds, similarity_threshold=0.5)

        messages = format_clusters_for_telegram(clusters)

        if messages:
            now = datetime.now().strftime("%d-%m-%Y")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🗞 *News Clusters for {escape_markdown_v2(now)}*\n\n",
                parse_mode="MarkdownV2",
                disable_web_page_preview=True,
            )

        for msg in messages:
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg,
                parse_mode="MarkdownV2",
                disable_web_page_preview=True,
            )

    except Exception as e:
        # logger.error(f"Error processing news: {e}", exc_info=True)
        await context.bot.send_message(
            chat_id=chat_id, text=f"❌ An error occurred: {str(e)}"
        )
