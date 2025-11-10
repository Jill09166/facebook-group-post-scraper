import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from .utils_datetime import parse_facebook_datetime

@dataclass
class FacebookPost:
    createdAt: int
    url: str
    user: Dict[str, Any]
    text: str
    attachments: List[Dict[str, Any]]
    reactionCount: int
    shareCount: int
    commentCount: int
    topComments: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "createdAt": self.createdAt,
            "url": self.url,
            "user": self.user,
            "text": self.text,
            "attachments": self.attachments,
            "reactionCount": self.reactionCount,
            "shareCount": self.shareCount,
            "commentCount": self.commentCount,
            "topComments": self.topComments,
        }

class FacebookGroupParser:
    """
    A lightweight HTML-based scraper for Facebook group posts.

    This scraper relies on session cookies and parses the HTML returned by Facebook
    group pages. Because Facebook changes its markup frequently, selectors are
    written defensively to avoid crashes if the structure doesn't match exactly.

    The goal is to produce structured post data as described in the README.
    """

    def __init__(
        self,
        session_cookie: str,
        proxies: Optional[Dict[str, str]] = None,
        user_agent: Optional[str] = None,
        timeout: int = 10,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.session_cookie = session_cookie
        self.proxies = proxies or {}
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/129.0 Safari/537.36"
        )
        self.timeout = timeout
        self.logger = logger or logging.getLogger(__name__)

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "User-Agent": self.user_agent,
            "Accept-Language": "en-US,en;q=0.9",
        }
        if self.session_cookie:
            headers["Cookie"] = self.session_cookie
        return headers

    def fetch_group_page(self, url: str, page: int = 1) -> str:
        """
        Fetch a single page of posts from the group.

        The implementation uses simple pagination via a `?page=` query, which
        may need adjustment for real-world scraping. The function is written
        to be robust and easy to adapt.
        """
        page_url = url
        if page > 1:
            separator = "&" if "?" in url else "?"
            page_url = f"{url}{separator}page={page}"

        self.logger.debug("Requesting URL: %s", page_url)

        response = requests.get(
            page_url,
            headers=self._build_headers(),
            proxies=self.proxies,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.text

    def fetch_group_posts(
        self,
        group_url: str,
        max_posts: int = 100,
        pagination_limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Fetch multiple pages of posts for a given group URL until max_posts
        or pagination_limit pages are reached.
        """
        posts: List[Dict[str, Any]] = []
        page = 1

        while len(posts) < max_posts and page <= pagination_limit:
            self.logger.debug("Fetching page %d for group %s", page, group_url)
            try:
                html = self.fetch_group_page(group_url, page=page)
            except Exception as e:
                self.logger.warning("Failed to fetch page %d: %s", page, e)
                break

            page_posts = self.parse_posts_from_html(html, group_url)
            self.logger.debug("Found %d posts on page %d", len(page_posts), page)

            if not page_posts:
                # No more posts or unable to parse this page.
                break

            posts.extend(page_posts)
            if len(posts) >= max_posts:
                break

            page += 1

        # Trim to max_posts just in case
        return posts[:max_posts]

    def parse_posts_from_html(self, html: str, group_url: str) -> List[Dict[str, Any]]:
        """
        Parse posts from a Facebook group HTML page.

        Because Facebook's structure is complex, this parser looks for generic
        patterns. It will also attempt to parse embedded JSON (e.g., in
        data-ft attributes) when available.
        """
        soup = BeautifulSoup(html, "html.parser")

        # Heuristic: posts often live in <div> elements with a role="article"
        # or data-pagelet attributes.
        article_divs = soup.find_all("div", attrs={"role": "article"})
        if not article_divs:
            # Fallback: try common feed container class names
            article_divs = soup.select("div[aria-posinset], div.story_body_container")

        posts: List[Dict[str, Any]] = []

        for idx, div in enumerate(article_divs):
            try:
                post = self._parse_single_post(div, group_url)
                posts.append(post.to_dict())
            except Exception as e:
                self.logger.debug("Failed to parse post index %d: %s", idx, e)

        return posts

    def _parse_single_post(self, div: Any, group_url: str) -> FacebookPost:
        """
        Parse a single post container into a FacebookPost object.
        """

        # Post URL: look for an <a> that looks like a permalink.
        url = self._extract_post_url(div, group_url)

        # Author
        user = self._extract_user(div)

        # Post text
        text = self._extract_post_text(div)

        # Attachments
        attachments = self._extract_attachments(div)

        # Engagement metrics
        reaction_count, comment_count, share_count = self._extract_engagement(div)

        # Created at timestamp
        created_at = self._extract_created_at(div)

        # Top comments (best-effort)
        top_comments = self._extract_top_comments(div)

        return FacebookPost(
            createdAt=created_at,
            url=url,
            user=user,
            text=text,
            attachments=attachments,
            reactionCount=reaction_count,
            shareCount=share_count,
            commentCount=comment_count,
            topComments=top_comments,
        )

    def _extract_post_url(self, div: Any, group_url: str) -> str:
        # Try to find permalink anchors
        anchor = div.find("a", href=True, string=lambda s: s and "Comment" not in s)
        if anchor and "permalink" in anchor["href"]:
            return self._normalize_url(anchor["href"])

        # Fallback: first link that looks like a post
        anchors = div.find_all("a", href=True)
        for a in anchors:
            href = a["href"]
            if "/posts/" in href or "/permalink/" in href:
                return self._normalize_url(href)

        # Last resort: use the group URL
        return group_url

    def _normalize_url(self, href: str) -> str:
        if href.startswith("http://") or href.startswith("https://"):
            return href
        if href.startswith("/"):
            return f"https://www.facebook.com{href}"
        return f"https://www.facebook.com/{href.lstrip('./')}"

    def _extract_user(self, div: Any) -> Dict[str, Any]:
        # Author name: often the first <strong> or <span> with a link
        name = ""
        profile_url = ""

        # Look for anchor with href and text
        author_link = None
        for a in div.find_all("a", href=True):
            if a.get("role") == "link" or a.get("tabindex") is not None:
                if a.text.strip():
                    author_link = a
                    break

        if author_link is not None:
            name = author_link.text.strip()
            profile_url = self._normalize_url(author_link["href"])

        # Try to derive a user ID from profile URL (simple heuristic)
        user_id = ""
        if "facebook.com" in profile_url:
            # If URL is like /profile.php?id=123 or /username
            if "profile.php?id=" in profile_url:
                user_id = profile_url.split("profile.php?id=")[-1].split("&")[0]
            else:
                user_id = profile_url.rstrip("/").split("/")[-1]

        return {
            "id": user_id,
            "name": name,
            "url": profile_url,
        }

    def _extract_post_text(self, div: Any) -> str:
        # Try to get story text; there might be multiple <span> or <div> tags.
        text_container = None

        # Common patterns
        candidates = div.select("div[dir='auto'], span[dir='auto']")
        if candidates:
            # Join all candidate text snippets
            texts = [c.get_text(separator=" ", strip=True) for c in candidates]
            text = " ".join(t for t in texts if t)
            if text:
                return text

        # Fallback: just get all text inside the post container
        raw_text = div.get_text(separator=" ", strip=True)
        return raw_text

    def _extract_attachments(self, div: Any) -> List[Dict[str, Any]]:
        attachments: List[Dict[str, Any]] = []

        # Look for images
        for img in div.find_all("img"):
            src = img.get("src")
            if not src:
                continue
            alt = img.get("alt", "")
            attachments.append(
                {
                    "type": "image",
                    "url": src,
                    "alt": alt,
                }
            )

        # Look for links that are not the author profile or comments
        for a in div.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if "facebook.com" in href and "groups" not in href:
                # Likely a profile or internal link; skip
                continue
            if "comment" in href.lower():
                continue
            if not href:
                continue
            attachments.append(
                {
                    "type": "link",
                    "url": self._normalize_url(href),
                    "text": text,
                }
            )

        # Deduplicate by URL
        seen = set()
        unique_attachments: List[Dict[str, Any]] = []
        for att in attachments:
            key = (att.get("type"), att.get("url"))
            if key in seen:
                continue
            seen.add(key)
            unique_attachments.append(att)

        return unique_attachments

    def _extract_engagement(self, div: Any) -> tuple[int, int, int]:
        """
        Attempt to extract reaction, comment, and share counts.
        """
        reaction_count = 0
        comment_count = 0
        share_count = 0

        text = div.get_text(" ", strip=True)

        def parse_count(label: str) -> Optional[int]:
            # Look for patterns like "12 Comments", "3 Shares", "10 reactions"
            lowered = text.lower()
            if label not in lowered:
                return None
            parts = lowered.split(label)[0].split()
            if not parts:
                return None
            last = parts[-1]
            try:
                # Handle e.g. "1.2K" or "3k"
                if "k" in last:
                    last = last.replace("k", "")
                    return int(float(last) * 1000)
                return int(last)
            except ValueError:
                return None

        rc = parse_count("reactions")
        if rc is not None:
            reaction_count = rc

        cc = parse_count("comments")
        if cc is not None:
            comment_count = cc

        sc = parse_count("shares")
        if sc is not None:
            share_count = sc

        return reaction_count, comment_count, share_count

    def _extract_created_at(self, div: Any) -> int:
        """
        Extract a Unix timestamp for the post creation time.
        """
        # Look for <abbr> or <span> with a data-utime or datetime attribute
        ts_candidates = div.find_all(["abbr", "span", "a"])
        for el in ts_candidates:
            utime = el.get("data-utime") or el.get("data-tooltip-content")
            datetime_attr = el.get("datetime")
            title = el.get("title")

            for raw in (utime, datetime_attr, title):
                if not raw:
                    continue
                ts = parse_facebook_datetime(raw)
                if ts:
                    return ts

        # Fallback: parse from text content if there's a relative time like "2 h" or "3 d"
        text = div.get_text(" ", strip=True)
        ts = parse_facebook_datetime(text)
        if ts:
            return ts

        # Last resort: use current timestamp
        return parse_facebook_datetime("now") or 0

    def _extract_top_comments(self, div: Any) -> List[Dict[str, Any]]:
        """
        Parse top-level comments, if visible in the HTML.

        Because comments are often loaded dynamically, this may return an empty list.
        """
        comments: List[Dict[str, Any]] = []

        # Look for containers that might hold comments
        comment_containers = div.find_all(
            "div",
            attrs={
                "aria-label": lambda v: v and "Comment" in v,
            },
        )

        for cdiv in comment_containers:
            try:
                comment_author = ""
                comment_author_url = ""
                author_link = cdiv.find("a", href=True)
                if author_link and author_link.text.strip():
                    comment_author = author_link.text.strip()
                    comment_author_url = self._normalize_url(author_link["href"])

                comment_text = cdiv.get_text(" ", strip=True)
                created_at = parse_facebook_datetime(comment_text) or 0

                comments.append(
                    {
                        "text": comment_text,
                        "createdAt": created_at,
                        "author": {
                            "name": comment_author,
                            "id": "",
                            "url": comment_author_url,
                        },
                        "reactionCount": 0,
                        "commentCount": 0,
                    }
                )
            except Exception as e:
                self.logger.debug("Failed to parse a comment: %s", e)

        # In a real-world scenario, comments might also be found inside embedded JSON.
        # We can look for script tags with JSON and attempt to parse them as a fallback.
        if not comments:
            comments.extend(self._extract_comments_from_json(div))

        return comments

    def _extract_comments_from_json(self, div: Any) -> List[Dict[str, Any]]:
        comments: List[Dict[str, Any]] = []

        for script in div.find_all("script"):
            script_text = script.string or ""
            if "comment" not in script_text.lower():
                continue
            try:
                # Heuristic: find JSON-like blobs in the script text
                start = script_text.find("{")
                end = script_text.rfind("}")
                if start == -1 or end == -1 or end <= start:
                    continue
                json_blob = script_text[start : end + 1]
                data = json.loads(json_blob)

                if not isinstance(data, dict):
                    continue

                # We don't know the exact schema; do a best-effort extraction
                potential_comments = data.get("comments") or data.get("edges") or []
                if isinstance(potential_comments, list):
                    for item in potential_comments:
                        if not isinstance(item, dict):
                            continue
                        node = item.get("node", item)
                        text = node.get("text") or node.get("body") or ""
                        author = node.get("author", {})
                        created_at_raw = node.get("created_time") or node.get("created_at")
                        created_at = 0
                        if created_at_raw is not None:
                            created_at = parse_facebook_datetime(str(created_at_raw)) or 0

                        comments.append(
                            {
                                "text": text,
                                "createdAt": created_at,
                                "author": {
                                    "name": author.get("name", ""),
                                    "id": author.get("id", ""),
                                    "url": author.get("url", ""),
                                },
                                "reactionCount": node.get("reaction_count", 0),
                                "commentCount": node.get("comment_count", 0),
                            }
                        )
            except Exception as e:
                self.logger.debug("Failed to parse comments from JSON: %s", e)

        return comments