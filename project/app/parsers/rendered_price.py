from __future__ import annotations

import re
from typing import Iterable


def _http_get(url: str, timeout: int) -> str | None:
    try:
        import requests
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception:
        return None


def _collect_prices(payload: str, patterns: Iterable[str], price_min: int, price_max: int) -> list[int]:
    candidates: list[int] = []
    for pattern in patterns:
        for raw in re.findall(pattern, payload, flags=re.IGNORECASE | re.DOTALL):
            value = raw if isinstance(raw, str) else raw[0]
            numeric = int(re.sub(r"\D", "", value)) if value else 0
            if price_min <= numeric <= price_max:
                candidates.append(numeric)
    return candidates


def _normalize_kupibilet_card_text(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    text = re.sub(r"(?:скидка\s*)?[−-]?\s*\d{1,2}%\s*[∙·•]?\s*\d{1,2}:\d{2}:\d{2}", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d{1,2}:\d{2}:\d{2}\b", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _build_kupibilet_card_fingerprint(card: dict) -> str:
    link_text = re.sub(r"\s+", "", str(card.get("link_text") or "").strip())
    current_price_text = _normalize_kupibilet_card_text(str(card.get("current_price_text") or ""))
    original_price_text = _normalize_kupibilet_card_text(str(card.get("original_price_text") or ""))
    tag_text = _normalize_kupibilet_card_text(str(card.get("tag_text") or ""))
    body_text = _normalize_kupibilet_card_text(str(card.get("text") or ""))
    json_text = _normalize_kupibilet_card_text(str(card.get("json") or ""))

    body_signature = body_text or json_text
    if link_text and body_signature:
        return f"{link_text}::{current_price_text}::{original_price_text}::{body_signature}"
    if body_signature:
        return f"{current_price_text}::{original_price_text}::{body_signature}"
    return link_text


def extract_rendered_price(
    url: str,
    patterns: Iterable[str],
    price_min: int = 3000,
    price_max: int = 500000,
    timeout_ms: int = 45000,
    pick: str = "first",
) -> int | None:
    try:
        import requests
    except Exception:
        return None

    html = _http_get(url, timeout=timeout_ms // 1000)
    if html is None:
        return None

    text_candidates = _collect_prices(html, patterns, price_min, price_max)

    html_patterns = [
        p.replace(r"\s+", r"(?:\s|<[^>]+>)+") for p in patterns
    ]
    html_candidates = _collect_prices(html, html_patterns, price_min, price_max)

    all_candidates = text_candidates + html_candidates
    if not all_candidates:
        return None
    if pick == "min":
        return min(all_candidates)
    return all_candidates[0]


def extract_rendered_attr_price(
    url: str,
    selector: str,
    attribute: str,
    price_min: int = 3000,
    price_max: int = 500000,
    timeout_ms: int = 45000,
) -> int | None:
    try:
        import requests
    except Exception:
        return None

    html = _http_get(url, timeout=timeout_ms // 1000)
    if html is None:
        return None

    try:
        from lxml import html as lxml_html
        tree = lxml_html.fromstring(html)
        elements = tree.cssselect(selector)
        if not elements:
            return None
        raw_value = elements[0].get(attribute, "")
    except Exception:
        return None

    digits = re.sub(r"\D", "", raw_value or "")
    numeric = int(digits) if digits else 0
    if price_min <= numeric <= price_max:
        return numeric
    return None


def extract_rendered_text_price(
    url: str,
    selector: str,
    price_min: int = 3000,
    price_max: int = 500000,
    timeout_ms: int = 45000,
) -> int | None:
    try:
        import requests
        from lxml import html as lxml_html
    except Exception:
        return None

    html = _http_get(url, timeout=timeout_ms // 1000)
    if html is None:
        return None

    try:
        tree = lxml_html.fromstring(html)
        elements = tree.cssselect(selector)
        if not elements:
            return None
        raw_value = elements[0].text_content().strip()
    except Exception:
        return None

    digits = re.sub(r"\D", "", raw_value or "")
    if not digits:
        return None

    numeric = int(digits)
    if price_min <= numeric <= price_max:
        return numeric
    return None


def extract_rendered_text_content(
    url: str,
    selector: str,
    timeout_ms: int = 45000,
) -> str | None:
    try:
        import requests
        from lxml import html as lxml_html
    except Exception:
        return None

    html = _http_get(url, timeout=timeout_ms // 1000)
    if html is None:
        return None

    try:
        tree = lxml_html.fromstring(html)
        elements = tree.cssselect(selector)
        if not elements:
            return None
        return elements[0].text_content().strip() or None
    except Exception:
        return None


def extract_rendered_page_payload(
    url: str,
    timeout_ms: int = 45000,
    selector: str = "body",
) -> tuple[str, str] | None:
    try:
        import requests
        from lxml import html as lxml_html
    except Exception:
        return None

    html = _http_get(url, timeout=timeout_ms // 1000)
    if html is None:
        return None

    try:
        tree = lxml_html.fromstring(html)
        elements = tree.cssselect(selector)
        if not elements:
            return html, html
        return elements[0].text_content().strip() or "", html
    except Exception:
        return html, html


def extract_rendered_nested_text_price(
    url: str,
    parent_selector: str,
    child_selector: str,
    price_min: int = 3000,
    price_max: int = 500000,
    timeout_ms: int = 45000,
) -> int | None:
    try:
        import requests
        from lxml import html as lxml_html
    except Exception:
        return None

    html = _http_get(url, timeout=timeout_ms // 1000)
    if html is None:
        return None

    try:
        tree = lxml_html.fromstring(html)
        parents = tree.cssselect(parent_selector)
        if not parents:
            return None
        children = parents[0].cssselect(child_selector)
        if not children:
            return None
        raw_value = children[0].text_content().strip()
    except Exception:
        return None

    numeric = int(re.sub(r"\D", "", raw_value)) if raw_value else 0
    if price_min <= numeric <= price_max:
        return numeric
    return None


def extract_rendered_ticket_cards(
    url: str,
    limit: int = 10,
    timeout_ms: int = 45000,
) -> list[dict]:
    return []


def extract_rendered_kupibilet_special_cards(
    url: str,
    limit: int = 30,
    timeout_ms: int = 45000,
    deep_scan: bool = True,
) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return []

    cards: list[dict] = []
    seen_fingerprints: set[str] = set()
    browser = None
    pw = None
    try:
        pw = sync_playwright()
        p = pw.__enter__()
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        try:
            page.wait_for_selector("text=₽", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(max(3000, timeout_ms // 10))

        text = page.inner_text("body")
        if not text or len(text) < 200:
            return []

        # Extract JSON-LD Flight data for booking links and structured info
        dest_to_ld: dict[str, str] = {}
        for script in page.query_selector_all('script[type="application/ld+json"]'):
            try:
                raw = script.inner_text() or ""
                import json as _json
                data = _json.loads(raw)
                flights = []
                if isinstance(data, dict):
                    if data.get("@type") == "Flight":
                        flights.append(data)
                    for item in data.get("@graph", []):
                        if item.get("@type") == "Flight":
                            flights.append(item)
                for f in flights:
                    name = f.get("name", "")
                    if "→" not in name:
                        continue
                    parts = name.split("→")
                    if len(parts) == 2:
                        dest = parts[1].strip()
                        offer = f.get("offers", {})
                        url = (offer.get("url") if isinstance(offer, dict) else "") or ""
                        if url and dest:
                            dest_to_ld[dest.lower()] = _json.dumps(f, ensure_ascii=False)
            except Exception:
                pass

        raw_lines = text.split("\n")
        stripped_lines = [l.strip() for l in raw_lines]

        # Locate the offers section
        try:
            start_idx = stripped_lines.index("Лазейки") + 1
        except ValueError:
            start_idx = 0

        # Find section end
        end_idx = len(stripped_lines)
        for marker in ("Карта городов", "Интересные места", "Интересные события"):
            try:
                pos = stripped_lines.index(marker, start_idx)
                if pos < end_idx:
                    end_idx = pos
            except ValueError:
                pass

        # Skip category-tab lines that come right after "Лазейки"
        category_tabs = {
            "Архитектура", "Исторические места", "Красивые виды", "Музеи",
            "На море", "Пеший туризм", "Пеший туризм / Треккинг",
            "Леса", "Реки и озера", "Рыбалка", "Охота",
        }
        while start_idx < end_idx and stripped_lines[start_idx] in category_tabs:
            start_idx += 1

        # Group into cards: each card starts with a price line (number + ₽)
        price_re = re.compile(r"\d[\d\s]*₽")
        blocks: list[list[str]] = []
        current: list[str] = []
        i = start_idx
        while i < end_idx:
            line = stripped_lines[i]
            if not line:
                i += 1
                continue
            if line == "Горячие билеты":
                if current:
                    blocks.append(current)
                    current = []
                i += 1
                continue
            # Detect new card: a price line after a card-ending line
            is_price = bool(price_re.search(line))
            if is_price and current and current[-1] in ("О городе", "На карте"):
                blocks.append(current)
                current = []
            current.append(line)
            i += 1
        if current:
            blocks.append(current)

        # Parse each block into a card
        for block in blocks:
            block_text = "\n".join(block)
            # Must contain a route arrow
            if "→" not in block_text:
                continue

            current_price = ""
            original_price = ""
            prices_found: list[str] = []
            for line in block:
                m = re.search(r"(\d[\d\s]*)\s*₽", line)
                if m:
                    prices_found.append(m.group(1).replace("\u00a0", "").replace(" ", ""))

            if len(prices_found) >= 2:
                original_price = prices_found[0]
                current_price = prices_found[1]
            elif len(prices_found) == 1:
                current_price = prices_found[0]

            # Extract destination name for JSON-LD lookup
            route_m = re.search(r"→\s*(.+)", block_text)
            dest_name = route_m.group(1).strip() if route_m else ""

            # Find JSON-LD for this destination
            json_str = ""
            link_text = ""
            if dest_name:
                ld_entry = dest_to_ld.get(dest_name.lower())
                if ld_entry:
                    json_str = ld_entry
                    try:
                        import json as _json2
                        ld_parsed = _json2.loads(ld_entry)
                        offer = ld_parsed.get("offers", {})
                        if isinstance(offer, dict):
                            link_text = offer.get("url", "") or ""
                    except Exception:
                        pass

            # Extract tag/timer
            tag_text = ""
            for line in block:
                if re.search(r"[−-]\s*\d{1,2}%\s*[∙·•]?\s*\d{1,2}:\d{2}:\d{2}", line):
                    tag_text = line.strip()
                    break

            fingerprint = _build_kupibilet_card_fingerprint({
                "link_text": link_text,
                "current_price_text": current_price,
                "original_price_text": original_price,
                "text": block_text,
            })
            if fingerprint and fingerprint not in seen_fingerprints:
                seen_fingerprints.add(fingerprint)
                cards.append({
                    "text": block_text,
                    "raw_text": block_text,
                    "json": json_str,
                    "link_text": link_text,
                    "current_price_text": current_price,
                    "original_price_text": original_price,
                    "tag_text": tag_text,
                })

        if limit and len(cards) > limit:
            cards = cards[:limit]

        return cards
    except Exception:
        return cards
    finally:
        try:
            if browser:
                browser.close()
        except Exception:
            pass
        try:
            if pw:
                pw.__exit__(None, None, None)
        except Exception:
            pass
