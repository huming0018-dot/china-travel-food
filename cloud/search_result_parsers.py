"""Pure search-result HTML parsers; no HTTP, project state or credential access.

BeautifulSoup owns HTML/CSS parsing. These selectors retain the project's
existing Bing/DDG output contract, not a guarantee of current live layouts.
"""

def parse_bing_html(html):
    from bs4 import BeautifulSoup
    s = BeautifulSoup(html, "html.parser")
    out = []
    for it in s.select("li.b_algo"):
        a = it.select_one("h2 a")
        if not a:
            continue
        href = a.get("href", "")
        if not href.startswith("http"):
            continue
        title = a.get_text(" ", strip=True)
        cap = it.select_one(".b_caption p") or it.select_one("p")
        snippet = cap.get_text(" ", strip=True) if cap else title
        host = href.split("://", 1)[-1].split("/", 1)[0]
        out.append({"source_url": href, "source_title": title[:120],
                    "snippet": snippet[:400], "source_host": host})
    return out[:8]


def parse_ddg_html(html):
    from bs4 import BeautifulSoup
    import re
    import urllib.parse as up
    s = BeautifulSoup(html, "html.parser")
    out = []
    for it in s.select("div.result"):
        a = it.select_one("a.result__a")
        if not a:
            continue
        href = a.get("href", "")
        m = re.search(r"uddg=([^&]+)", href)
        if m:
            href = up.unquote(m.group(1))
        if not href.startswith("http"):
            continue
        sn = it.select_one(".result__snippet")
        title = a.get_text(" ", strip=True)
        snippet = sn.get_text(" ", strip=True) if sn else title
        host = href.split("://", 1)[-1].split("/", 1)[0]
        out.append({"source_url": href, "source_title": title[:120],
                    "snippet": snippet[:400], "source_host": host})
    return out[:8]

