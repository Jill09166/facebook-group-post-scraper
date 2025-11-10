import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any

from extractors.facebook_group_parser import FacebookGroupParser
from outputs.exporter import export_posts

def setup_logger(verbosity: int) -> logging.Logger:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("facebook-group-post-scraper")
    return logger

def load_settings(config_path: Path | None = None) -> Dict[str, Any]:
    """
    Load scraper settings from settings.json; fall back to settings.example.json.
    """
    src_dir = Path(__file__).resolve().parent
    config_dir = src_dir / "config"

    if config_path is None:
        primary = config_dir / "settings.json"
        fallback = config_dir / "settings.example.json"
        if primary.exists():
            config_path = primary
        else:
            config_path = fallback

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        settings = json.load(f)

    return settings

def load_input_urls(data_dir: Path) -> List[str]:
    input_file = data_dir / "input_urls.txt"
    if not input_file.exists():
        raise FileNotFoundError(f"Input URLs file not found: {input_file}")

    with input_file.open("r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    return urls

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Facebook group posts and export them to JSON/CSV/XLSX."
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to a settings.json configuration file.",
    )
    parser.add_argument(
        "--max-posts",
        type=int,
        default=None,
        help="Maximum number of posts per group to scrape (overrides config).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for exported files (overrides config).",
    )
    parser.add_argument(
        "--output-formats",
        type=str,
        default=None,
        help="Comma-separated list of output formats: json,csv,xlsx (overrides config).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity level (can be used multiple times).",
    )
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    logger = setup_logger(args.verbose)

    try:
        config_path = Path(args.config) if args.config else None
        settings = load_settings(config_path)
    except Exception as e:
        logger.error("Failed to load settings: %s", e)
        sys.exit(1)

    root_dir = Path(__file__).resolve().parents[1]
    data_dir = root_dir / "data"

    try:
        urls = load_input_urls(data_dir)
    except Exception as e:
        logger.error("Failed to load input URLs: %s", e)
        sys.exit(1)

    session_cookie = settings.get("session_cookie")
    if not session_cookie or "your_facebook_session_cookie_here" in session_cookie:
        logger.warning(
            "Session cookie is not configured. "
            "You must set a valid 'session_cookie' in src/config/settings.json."
        )

    proxies = settings.get("proxies") or {}
    request_timeout = settings.get("request_timeout", 10)
    user_agent = settings.get("user_agent") or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0 Safari/537.36"
    )

    max_posts_per_group = args.max_posts or settings.get("max_posts_per_group", 100)
    pagination_limit = settings.get("pagination_limit", 10)

    configured_output_dir = settings.get("output_dir", str(data_dir))
    output_dir = Path(args.output_dir) if args.output_dir else Path(configured_output_dir)

    if args.output_formats:
        output_formats = [f.strip().lower() for f in args.output_formats.split(",") if f.strip()]
    else:
        output_formats = settings.get("output_formats", ["json", "csv", "xlsx"])

    logger.info("Starting Facebook group post scraping.")
    logger.debug("Using settings: %s", settings)

    parser = FacebookGroupParser(
        session_cookie=session_cookie or "",
        proxies=proxies,
        user_agent=user_agent,
        timeout=request_timeout,
        logger=logging.getLogger("facebook-group-parser"),
    )

    all_posts: List[Dict[str, Any]] = []

    for url in urls:
        logger.info("Scraping group: %s", url)
        try:
            posts = parser.fetch_group_posts(
                group_url=url,
                max_posts=max_posts_per_group,
                pagination_limit=pagination_limit,
            )
            logger.info("Scraped %d posts from %s", len(posts), url)
            all_posts.extend(posts)
        except Exception as e:
            logger.error("Failed to scrape %s: %s", url, e)

    if not all_posts:
        logger.warning("No posts were scraped. Nothing to export.")
        return

    try:
        export_posts(
            posts=all_posts,
            output_dir=output_dir,
            base_filename="facebook_group_posts",
            formats=output_formats,
            logger=logging.getLogger("exporter"),
        )
    except Exception as e:
        logger.error("Failed to export posts: %s", e)
        sys.exit(1)

    logger.info("Scraping and export complete.")

if __name__ == "__main__":
    main()