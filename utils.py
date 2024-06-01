import re
from solders.pubkey import Pubkey
import aiohttp
import asyncio
import logging


def extract_url_and_validate_mint_address(text: str):
    url_pattern = re.compile(r"https:\/\/(www\.)?pump\.fun\/[A-Za-z0-9]+")
    match = url_pattern.search(text)

    if not match:
        return None

    url = match.group(0)

    mint_address = url.split("/")[-1]

    try:
        Pubkey.from_string(mint_address)
        return url
    except Exception as e:
        return None


def is_root_domain(url: str):
    ROOT_DOMAIN_PATTERN = re.compile(r"^https:\/\/[^\/]+\/?$")
    return bool(ROOT_DOMAIN_PATTERN.match(url))


async def expand_url(short_url: str):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(short_url, allow_redirects=True) as response:
                return str(response.url)
    except aiohttp.ClientError as e:
        logging.error(f"Error expanding URL: {e}")
        return short_url


async def replace_short_urls(text: str):
    URL_PATTERN = re.compile(r"(https?://t\.co/\S+?)([\.,!?]*)(?:\s|$)")

    matches = URL_PATTERN.findall(text)
    tasks = [expand_url(url) for url, _ in matches]
    expanded_urls = await asyncio.gather(*tasks)

    for (short_url, punctuation), expanded_url in zip(matches, expanded_urls):
        text = text.replace(short_url, expanded_url + punctuation)

    return text
