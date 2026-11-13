from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
import requests


def ecobici_links(session: requests.Session) -> list[str]:
    url_base = "https://ecobici.cdmx.gob.mx/datos-abiertos/"
    with session.get(url_base, timeout=(10, 60)) as response:
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
    links = []
    for anchor in soup.find_all("a", href=True):
        url = urljoin(url_base, anchor["href"])
        if urlsplit(url).path.lower().endswith(".csv") and url not in links:
            links.append(url)
    return links
