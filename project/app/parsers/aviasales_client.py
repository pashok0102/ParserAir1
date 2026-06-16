from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
import re
from threading import Lock
from time import monotonic
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import requests
from requests.adapters import HTTPAdapter

from app.config import Settings
from app.parsers.rendered_price import (
    extract_rendered_attr_price,
    extract_rendered_kupibilet_special_cards,
    extract_rendered_nested_text_price,
    extract_rendered_page_payload,
    extract_rendered_price,
    extract_rendered_ticket_cards,
    extract_rendered_text_content,
    extract_rendered_text_price,
)


@dataclass
class Ticket:
    origin: str
    destination: str
    price: int
    airline: str
    departure_at: str
    transfers: int
    link: str
    source: str = "Aviasales"
    updated_at: str = ""
    estimated_price: bool = False
    baggage_info: str = ""
    original_price: int | None = None
    hot_discount_percent: int | None = None
    hot_expires_at: str = ""
    special_offer_label: str = ""


class AviasalesClient:
    API_PAGE_LIMIT = 100
    ANYWHERE_CANDIDATE_MULTIPLIER = 8
    ANYWHERE_CANDIDATE_LIMIT = 150
    ANYWHERE_MAX_WORKERS = 6
    ANYWHERE_EXACT_CANDIDATES = 18
    ANYWHERE_EXACT_TIMEOUT_SECONDS = 10
    EXACT_RENDERED_PRICE_MAX_WORKERS = 6
    EXACT_RENDERED_PRICE_CANDIDATES = 12
    EXACT_PRICE_CACHE_TTL_SECONDS = 300
    EXACT_PRICE_CACHE_VERSION = "v3-proposal-main-price"
    CITY_IATA_ALIASES = {
        "москва": "MOW",
        "moscow": "MOW",
        "мск": "MOW",
    }
    CITY_LABEL_ALIASES = {
        "MOW": "Москва",
    }

    def __init__(self, settings: Settings):
        self.settings = settings
        self._location_cache: dict[str, str] = {}
        self._location_name_cache: dict[str, str] = {}
        self._airport_name_cache: dict[str, str] = {}
        self._exact_price_cache: dict[str, tuple[float, int | None, str]] = {}
        self._exact_price_cache_lock = Lock()
        self.session = self._build_session()

    @staticmethod
    def _build_session() -> requests.Session:
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=32, pool_maxsize=32)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*"})
        return session

    @staticmethod
    def _safe_sort_price(value: object, fallback: int = 10**9) -> int:
        if isinstance(value, (int, float)):
            return int(value)
        digits = re.sub(r"\D", "", str(value or ""))
        return int(digits) if digits else fallback

    def get_hot_tickets(
        self,
        route: str,
        limit: int = 10,
        request_limit: int = 100,
        departure_date: date | None = None,
        strict_exact_price: bool = True,
    ) -> list[Ticket]:
        origin, destination = self._parse_route(route)
        raw_tickets = self._fetch_tickets(origin=origin, destination=destination, limit=request_limit)

        now = datetime.now(timezone.utc)
        upcoming: list[dict] = []
        for ticket in raw_tickets:
            departure_dt = self._parse_iso(ticket.get("departure_at"))
            if departure_dt < now:
                continue
            if departure_date and departure_dt.date() != departure_date:
                continue
            ticket["estimated_price"] = True
            upcoming.append(ticket)

        upcoming.sort(key=lambda t: (self._safe_sort_price(t.get("price")), self._parse_iso(t.get("departure_at"))))
        selected = upcoming[:limit]
        if strict_exact_price:
            selected = selected[: self.EXACT_RENDERED_PRICE_CANDIDATES]

        max_workers = min(self.EXACT_RENDERED_PRICE_MAX_WORKERS, max(1, len(selected)))
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(self._refine_exact_ticket_price, item) for item in selected]
                for future in as_completed(futures):
                    future.result()
        except RuntimeError:
            for item in selected:
                self._refine_exact_ticket_price(item)

        if strict_exact_price:
            selected = [item for item in selected if not item.get("estimated_price", True)]
        selected.sort(key=lambda t: (self._safe_sort_price(t.get("price")), self._parse_iso(t.get("departure_at"))))
        return [self._to_ticket(item) for item in selected]

    def get_hot_tickets_in_range(
        self,
        route: str,
        start_date: date,
        end_date: date,
        limit: int | None = None,
        request_limit: int = 200,
    ) -> list[Ticket]:
        origin, destination = self._parse_route(route)
        raw_tickets = self._fetch_tickets(origin=origin, destination=destination, limit=request_limit)

        now = datetime.now(timezone.utc)
        selected: list[dict] = []
        for ticket in raw_tickets:
            departure_dt = self._parse_iso(ticket.get("departure_at"))
            if departure_dt < now:
                continue
            dep_date = departure_dt.date()
            if dep_date < start_date or dep_date > end_date:
                continue
            ticket["estimated_price"] = True
            selected.append(ticket)

        selected.sort(key=lambda t: (self._parse_iso(t.get("departure_at")), self._safe_sort_price(t.get("price"))))
        if limit is not None:
            selected = selected[:limit]
        return [self._to_ticket(item) for item in selected]

    def get_hot_tickets_anywhere(
        self,
        origin_value: str,
        limit: int = 10,
        request_limit: int = 100,
        departure_date: date | None = None,
        refine_exact: bool = True,
    ) -> list[Ticket]:
        origin = self._resolve_location_code(origin_value)
        candidate_limit = min(
            max(limit * self.ANYWHERE_CANDIDATE_MULTIPLIER, request_limit, limit),
            self.ANYWHERE_CANDIDATE_LIMIT,
        )
        raw_tickets = self._fetch_anywhere_tickets(origin=origin, limit=candidate_limit, departure_date=departure_date)

        now = datetime.now(timezone.utc)
        candidates: list[dict] = []
        seen_destinations: set[str] = set()
        for ticket in raw_tickets:
            departure_dt = self._parse_iso(ticket.get("departure_at"))
            if departure_dt < now:
                continue
            destination = str(ticket.get("destination", "")).upper()
            if not destination or destination == origin or destination in seen_destinations:
                continue
            seen_destinations.add(destination)
            candidates.append(ticket)

        candidates.sort(key=lambda t: (self._safe_sort_price(t.get("price")), self._parse_iso(t.get("departure_at"))))

        if not refine_exact:
            return [self._to_ticket(item) for item in candidates[:limit]]

        exact_results: list[Ticket] = []
        exact_candidates = candidates[: min(len(candidates), max(limit * 2, self.ANYWHERE_EXACT_CANDIDATES))]

        def fetch_exact_ticket(candidate: dict) -> Ticket | None:
            destination = str(candidate.get("destination", "")).upper()
            if not destination:
                return None
            route = f"{origin} - {destination}"
            try:
                exact_ticket = self.get_hot_tickets(
                    route=route,
                    limit=1,
                    request_limit=max(100, request_limit, limit * 4),
                    departure_date=departure_date,
                )
            except requests.RequestException:
                return None
            if not exact_ticket:
                return None
            return exact_ticket[0]

        max_workers = min(self.ANYWHERE_MAX_WORKERS, max(1, len(exact_candidates)))
        try:
            executor = ThreadPoolExecutor(max_workers=max_workers)
            futures = [executor.submit(fetch_exact_ticket, candidate) for candidate in exact_candidates]
            try:
                done, not_done = wait(futures, timeout=self.ANYWHERE_EXACT_TIMEOUT_SECONDS)
                for future in done:
                    exact_ticket = future.result()
                    if exact_ticket is not None:
                        exact_results.append(exact_ticket)
                for future in not_done:
                    future.cancel()
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
        except RuntimeError:
            for candidate in exact_candidates:
                exact_ticket = fetch_exact_ticket(candidate)
                if exact_ticket is not None:
                    exact_results.append(exact_ticket)

        if exact_results:
            exact_results.sort(key=lambda t: (t.price, self._parse_iso(t.departure_at)))
            if len(exact_results) >= limit:
                return exact_results[:limit]

            seen_destinations = {ticket.destination for ticket in exact_results}
            fallback_tickets = [self._to_ticket(item) for item in candidates if str(item.get("destination", "")).upper() not in seen_destinations]
            return (exact_results + fallback_tickets)[:limit]

        return [self._to_ticket(item) for item in candidates[:limit]]

    def get_available_departure_dates(self, route: str, request_limit: int = 100) -> list[date]:
        origin, destination = self._parse_route(route)
        raw_tickets = self._fetch_tickets(origin=origin, destination=destination, limit=request_limit)

        now = datetime.now(timezone.utc)
        dates: set[date] = set()
        for ticket in raw_tickets:
            departure_dt = self._parse_iso(ticket.get("departure_at"))
            if departure_dt >= now:
                dates.add(departure_dt.date())
        return sorted(dates)

    def parse_route_to_iata(self, route: str) -> tuple[str, str]:
        return self._parse_route(route)

    def resolve_location_name(self, raw_value: str) -> str:
        normalized = self._repair_mojibake(raw_value)
        if not normalized:
            return ""

        alias_label = self.CITY_LABEL_ALIASES.get(normalized.upper())
        if alias_label:
            return alias_label

        cache_key = normalized.upper()
        if cache_key in self._location_name_cache:
            return self._location_name_cache[cache_key]

        url = "https://autocomplete.travelpayouts.com/places2"
        variants = [
            {"term": normalized, "locale": "ru", "types[]": "city"},
            {"term": normalized, "locale": "ru", "types[]": "airport"},
            {"term": normalized, "locale": "en", "types[]": "city"},
            {"term": normalized, "locale": "en", "types[]": "airport"},
        ]

        for params in variants:
            try:
                response = self.session.get(url, params=params, timeout=20)
                response.raise_for_status()
                payload = response.json()
            except requests.RequestException:
                continue

            if not isinstance(payload, list):
                continue

            matched = self._find_matching_place(payload, normalized)
            if not matched:
                continue

            label = self._build_location_label(matched)
            if label:
                self._location_name_cache[cache_key] = label
                return label

        return normalized

    def resolve_airport_name(self, raw_value: str) -> str:
        normalized = self._repair_mojibake(raw_value)
        if not normalized:
            return ""

        cache_key = normalized.upper()
        if cache_key in self._airport_name_cache:
            return self._airport_name_cache[cache_key]

        url = "https://autocomplete.travelpayouts.com/places2"
        variants = [
            {"term": normalized, "locale": "ru", "types[]": "airport"},
            {"term": normalized, "locale": "en", "types[]": "airport"},
            {"term": normalized, "locale": "ru", "types[]": "city"},
            {"term": normalized, "locale": "en", "types[]": "city"},
        ]

        for params in variants:
            try:
                response = self.session.get(url, params=params, timeout=20)
                response.raise_for_status()
                payload = response.json()
            except requests.RequestException:
                continue

            if not isinstance(payload, list):
                continue

            matched = self._find_matching_place(payload, normalized)
            if not matched:
                continue

            label = self._build_airport_label(matched)
            if label:
                self._airport_name_cache[cache_key] = label
                return label

        fallback = self.resolve_location_name(normalized)
        self._airport_name_cache[cache_key] = fallback
        return fallback

    @staticmethod
    def _repair_mojibake(value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            return normalized

        if not any(marker in normalized for marker in ("Р", "С", "Ð", "Ñ")):
            return normalized

        for encoding in ("cp1251", "latin1"):
            try:
                repaired = normalized.encode(encoding).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            if repaired and repaired != normalized:
                return repaired.strip()

        return normalized

    @staticmethod
    def split_route_parts(route: str) -> tuple[str, str]:
        raw = route.strip()
        if not raw:
            raise ValueError("Маршрут не указан")

        for sep in (" - ", " – ", " — "):
            if sep in raw:
                left, right = raw.split(sep, maxsplit=1)
                left = left.strip()
                right = right.strip()
                if left and right:
                    return left, right

        m = re.fullmatch(r"([A-Za-z]{3})[-–—]([A-Za-z]{3})", raw)
        if m:
            return m.group(1), m.group(2)

        raise ValueError("Маршрут должен быть в формате: Город - Город или IATA-IATA")

    def _parse_route(self, route: str) -> tuple[str, str]:
        city_from, city_to = self.split_route_parts(route)
        return self._resolve_location_code(city_from), self._resolve_location_code(city_to)

    def _fetch_tickets(self, origin: str, destination: str, limit: int) -> list[dict]:
        url = f"{self.settings.base_url}/aviasales/v3/prices_for_dates"
        headers = {"X-Access-Token": self.settings.api_key, "Accept": "application/json"}

        remaining = max(limit, 1)
        page = 1
        all_data: list[dict] = []

        while remaining > 0:
            batch_limit = min(self.API_PAGE_LIMIT, remaining)
            params = {
                "origin": origin,
                "destination": destination,
                "currency": self.settings.currency,
                "one_way": "true",
                "sorting": "price",
                "trip_class": 0,
                "limit": batch_limit,
                "page": page,
            }

            response = self.session.get(url, params=params, headers=headers, timeout=40)
            response.raise_for_status()
            payload = response.json()

            data = payload.get("data", [])
            if isinstance(data, dict):
                data = list(data.values())
            if not isinstance(data, list) or not data:
                break

            all_data.extend(data)
            remaining -= len(data)
            if len(data) < batch_limit:
                break

            page += 1
            if page > 20:
                break

        return all_data

    def _fetch_anywhere_tickets(self, origin: str, limit: int, departure_date: date | None = None) -> list[dict]:
        url = f"{self.settings.base_url}/v1/prices/cheap"
        params = {
            "origin": origin,
            "currency": self.settings.currency,
            "page": 1,
            "token": self.settings.api_key,
            "one_way": "true",
        }
        if departure_date:
            params["depart_date"] = departure_date.isoformat()

        response = self.session.get(url, params=params, timeout=40, headers={"Accept": "application/json"})
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", {})

        items = self._collect_anywhere_items(data)

        normalized: list[dict] = []
        for item in items[: max(limit, 1)]:
            if not isinstance(item, dict):
                continue
            normalized.append(self._normalize_anywhere_ticket(item, origin))

        return normalized

    def _collect_anywhere_items(self, node: object, inherited_destination: str | None = None) -> list[dict]:
        items: list[dict] = []

        if isinstance(node, list):
            for item in node:
                items.extend(self._collect_anywhere_items(item, inherited_destination))
            return items

        if not isinstance(node, dict):
            return items

        if any(key in node for key in ("price", "value", "depart_date", "departure_at")):
            normalized = dict(node)
            if inherited_destination and len(inherited_destination) == 3:
                normalized.setdefault("destination", inherited_destination.upper())
            items.append(normalized)
            return items

        for key, value in node.items():
            next_destination = inherited_destination
            if isinstance(key, str) and len(key) == 3 and key.isalpha():
                next_destination = key.upper()
            items.extend(self._collect_anywhere_items(value, next_destination))

        return items

    @staticmethod
    def _normalize_anywhere_ticket(item: dict, origin: str) -> dict:
        normalized = dict(item)
        normalized["origin"] = normalized.get("origin") or origin
        normalized["destination"] = normalized.get("destination") or normalized.get("destination_iata") or normalized.get("dest")
        normalized["price"] = normalized.get("price") or normalized.get("value") or 0
        normalized["airline"] = normalized.get("airline") or normalized.get("airline_code") or "N/A"
        normalized["transfers"] = normalized.get("transfers", normalized.get("number_of_changes", 0))
        normalized["estimated_price"] = True

        if not normalized.get("departure_at"):
            depart_date = normalized.get("departure_at") or normalized.get("depart_date")
            if depart_date:
                normalized["departure_at"] = f"{depart_date}T00:00:00+00:00"

        if not normalized.get("link"):
            link = normalized.get("link") or normalized.get("url")
            if link:
                normalized["link"] = link
            elif normalized.get("destination"):
                normalized["link"] = AviasalesClient._build_aviasales_one_way_link(
                    origin=str(normalized["origin"]).upper(),
                    destination=str(normalized["destination"]).upper(),
                    departure_at=str(normalized.get("departure_at", "")),
                )

        return normalized

    def _refine_exact_ticket_price(self, item: dict) -> bool:
        link = str(item.get("link") or "").strip()
        if not link:
            origin = str(item.get("origin") or "").upper()
            destination = str(item.get("destination") or "").upper()
            departure_at = str(item.get("departure_at") or "")
            link = self._build_aviasales_one_way_link(origin, destination, departure_at)

        if not link:
            item["estimated_price"] = True
            return False

        if not link.startswith("http"):
            link = f"https://www.aviasales.ru{link}"

        cache_key = f"{self.EXACT_PRICE_CACHE_VERSION}|{link}"
        cache_hit, cached_price, cached_baggage = self._get_cached_exact_price(cache_key)
        if cache_hit:
            if cached_price is None:
                item["estimated_price"] = True
                return False
            item["price"] = cached_price
            item["estimated_price"] = False
            if cached_baggage:
                item["baggage_info"] = cached_baggage
            return True

        rendered_price = extract_rendered_nested_text_price(
            link,
            parent_selector='[data-test-id="proposal-0"]',
            child_selector='[data-test-id="price"]',
            price_min=3000,
            price_max=500000,
            timeout_ms=9000,
        )

        if rendered_price is None:
            rendered_price = extract_rendered_text_price(
                link,
                selector='[data-test-id="proposal-0"] [data-test-id="price"]',
                price_min=3000,
                price_max=500000,
                timeout_ms=9000,
            )

        if rendered_price is None:
            rendered_price = extract_rendered_price(
                link,
                patterns=[
                    r'data-test-id="proposal-0"[\s\S]{0,2000}?data-test-id="price">(\d{1,3}(?:[ \u00A0\u202F]\d{3})+|\d{4,6})\s*₽',
                    r'data-test-id="price">(\d{1,3}(?:[ \u00A0\u202F]\d{3})+|\d{4,6})\s*₽',
                ],
                price_min=3000,
                price_max=500000,
                timeout_ms=9000,
                pick="first",
            )
        if rendered_price is None:
            rendered_price = extract_rendered_attr_price(
                link,
                selector='[data-test-id="proposal-0"]',
                attribute='data-test-price',
                price_min=3000,
                price_max=500000,
                timeout_ms=9000,
            )

        if rendered_price is not None:
            item["price"] = rendered_price
            item["estimated_price"] = False
            baggage_info = self._extract_baggage_info(link)
            if baggage_info:
                item["baggage_info"] = baggage_info
            self._set_cached_exact_price(cache_key, rendered_price, baggage_info)
            return True

        self._set_cached_exact_price(cache_key, None, "")
        item["estimated_price"] = True
        return False

    def _extract_baggage_info(self, link: str) -> str:
        proposal_text = extract_rendered_text_content(
            link,
            selector='[data-test-id="proposal-0"]',
            timeout_ms=7000,
        )
        if not proposal_text:
            return ""

        lines = [line.strip() for line in proposal_text.splitlines() if line.strip()]
        baggage_lines: list[str] = []
        for line in lines:
            normalized = line.lower()
            if normalized.startswith("багаж") or normalized.startswith("ручная кладь"):
                baggage_lines.append(line)

        if baggage_lines:
            return " | ".join(dict.fromkeys(baggage_lines))

        compact_matches = re.findall(
            r"(Багаж\s+[^\n|]+|Ручная\s+кладь\s+[^\n|]+)",
            proposal_text,
            flags=re.IGNORECASE,
        )
        if compact_matches:
            cleaned = [match.strip() for match in compact_matches if match.strip()]
            return " | ".join(dict.fromkeys(cleaned))

        return ""

    def _get_cached_exact_price(self, cache_key: str) -> tuple[bool, int | None, str]:
        now = monotonic()
        with self._exact_price_cache_lock:
            cached = self._exact_price_cache.get(cache_key)
            if not cached:
                return False, None, ""
            expires_at, price, baggage_info = cached
            if expires_at <= now:
                self._exact_price_cache.pop(cache_key, None)
                return False, None, ""
            return True, price, baggage_info

    def _set_cached_exact_price(self, cache_key: str, price: int | None, baggage_info: str = "") -> None:
        with self._exact_price_cache_lock:
            self._exact_price_cache[cache_key] = (monotonic() + self.EXACT_PRICE_CACHE_TTL_SECONDS, price, baggage_info)

    @staticmethod
    def _build_aviasales_one_way_link(origin: str, destination: str, departure_at: str) -> str:
        dep = AviasalesClient._extract_date(departure_at)
        if not dep:
            return ""
        # Aviasales deep-link format for one-way search: ORIGIN + DDMM + DESTINATION + passengers
        return f"/search/{origin}{dep.strftime('%d%m')}{destination}1"

    def _resolve_location_code(self, raw_value: str) -> str:
        normalized = self._repair_mojibake(raw_value)
        alias_code = self.CITY_IATA_ALIASES.get(normalized.lower())
        if alias_code:
            return alias_code
        candidate = normalized.upper()
        if len(candidate) == 3 and candidate.isalpha():
            return candidate

        cache_key = normalized.lower()
        if cache_key in self._location_cache:
            return self._location_cache[cache_key]

        code = self._resolve_city_iata(normalized)
        if code:
            self._location_cache[cache_key] = code
            return code

        raise ValueError(f"Не удалось определить IATA код для '{raw_value}'")

    def _resolve_city_iata(self, location_name: str) -> str | None:
        url = "https://autocomplete.travelpayouts.com/places2"
        variants = [
            {"term": location_name, "locale": "ru", "types[]": "city"},
            {"term": location_name, "locale": "ru", "types[]": "airport"},
            {"term": location_name, "locale": "en", "types[]": "city"},
            {"term": location_name, "locale": "en", "types[]": "airport"},
        ]

        for params in variants:
            response = self.session.get(url, params=params, timeout=40)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                continue
            for item in payload:
                if not isinstance(item, dict):
                    continue
                code = str(item.get("code", "")).upper()
                if len(code) == 3 and code.isalpha():
                    return code
        return None

    @staticmethod
    def _find_matching_place(payload: list[dict], raw_value: str) -> dict | None:
        upper_value = raw_value.upper()
        for item in payload:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code", "")).upper()
            if code == upper_value:
                return item
        return payload[0] if payload else None

    @staticmethod
    def _build_location_label(item: dict) -> str:
        name = str(item.get("name", "")).strip()
        city_name = str(item.get("city_name", "")).strip()

        if city_name and name and name.lower() != city_name.lower():
            return f"{city_name}, {name}"
        if name:
            return name
        if city_name:
            return city_name
        return str(item.get("code", "")).strip()

    @staticmethod
    def _build_airport_label(item: dict) -> str:
        name = str(item.get("name", "")).strip()
        city_name = str(item.get("city_name", "")).strip()

        if name:
            return name
        if city_name:
            return city_name
        return str(item.get("code", "")).strip()

    @staticmethod
    def _parse_iso(value: str | None) -> datetime:
        if not value:
            return datetime.max.replace(tzinfo=timezone.utc)
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return datetime.max.replace(tzinfo=timezone.utc)

    @staticmethod
    def _extract_date(value: str) -> date | None:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None

    @staticmethod
    def _to_ticket(item: dict) -> Ticket:
        return Ticket(
            origin=item.get("origin", ""),
            destination=item.get("destination", ""),
            price=AviasalesClient._safe_sort_price(item.get("price"), fallback=0),
            airline=item.get("airline", "N/A"),
            departure_at=item.get("departure_at", "N/A"),
            transfers=AviasalesClient._safe_sort_price(item.get("transfers"), fallback=0),
            link=item.get("link", ""),
            source="Aviasales",
            updated_at=datetime.now(timezone.utc).isoformat(),
            estimated_price=bool(item.get("estimated_price", False)),
            baggage_info=str(item.get("baggage_info", "") or ""),
        )


class TutuClient:
    IATA_TO_TUTU_ID = {"MOW": 491, "AER": 78, "REN": 64}
    IATA_TO_TUTU_SLUG = {"MOW": "Moskva", "AER": "Sochi", "REN": "Orenburg"}

    PRICE_MIN = 3000
    PRICE_MAX = 500000

    def __init__(self, aviasales_client: AviasalesClient):
        self.aviasales_client = aviasales_client
        self.session = aviasales_client._build_session()

    def get_hot_tickets(
        self,
        route: str,
        limit: int = 10,
        request_limit: int = 100,
        departure_date: date | None = None,
        return_date: date | None = None,
    ) -> list[Ticket]:
        del return_date
        city_from, city_to = self.aviasales_client.split_route_parts(route)
        iata_from, iata_to = self.aviasales_client.parse_route_to_iata(route)
        fallback_ticket = self._get_reference_ticket(
            route=route,
            request_limit=request_limit,
            departure_date=departure_date,
        )
        fallback_airline = fallback_ticket.airline if fallback_ticket else ""

        route_min_price = self._fetch_tutu_route_min_price(city_from, city_to, iata_from, iata_to, departure_date)
        used_fallback = False
        if route_min_price is None:
            if not fallback_ticket:
                return []
            route_min_price = fallback_ticket.price
            used_fallback = True

        dep = departure_date or datetime.now(timezone.utc).date()
        departure_at = fallback_ticket.departure_at if fallback_ticket else datetime.combine(dep, datetime.min.time(), tzinfo=timezone.utc).isoformat()
        link = self._build_tutu_hot_link(city_from, city_to, iata_from, iata_to, departure_at)

        return [
            Ticket(
                origin=iata_from,
                destination=iata_to,
                price=route_min_price,
                airline=fallback_airline or ("Нет данных Tutu (fallback Aviasales)" if used_fallback else "Найдено на Tutu"),
                departure_at=departure_at,
                transfers=fallback_ticket.transfers if fallback_ticket else 0,
                link=link,
                source="Tutu.ru",
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
        ]

    def _get_reference_ticket(
        self,
        route: str,
        request_limit: int,
        departure_date: date | None,
    ) -> Ticket | None:
        requests_limit = max(request_limit, 100)

        if departure_date:
            exact = self.aviasales_client.get_hot_tickets(
                route=route,
                limit=1,
                request_limit=requests_limit,
                departure_date=departure_date,
                strict_exact_price=False,
            )
            if exact:
                return exact[0]

            nearby = self.aviasales_client.get_hot_tickets_in_range(
                route=route,
                start_date=departure_date,
                end_date=departure_date + timedelta(days=3),
                limit=1,
                request_limit=requests_limit,
            )
            if nearby:
                return nearby[0]

        generic = self.aviasales_client.get_hot_tickets(
            route=route,
            limit=1,
            request_limit=requests_limit,
            departure_date=None,
            strict_exact_price=False,
        )
        return generic[0] if generic else None

    def get_available_departure_dates(self, route: str, request_limit: int = 100) -> list[date]:
        return self.aviasales_client.get_available_departure_dates(route=route, request_limit=request_limit)

    def build_fallback_ticket(self, reference_ticket: Ticket) -> Ticket:
        city_from = self.aviasales_client.resolve_location_name(reference_ticket.origin)
        city_to = self.aviasales_client.resolve_location_name(reference_ticket.destination)
        link = self._build_tutu_hot_link(
            city_from,
            city_to,
            reference_ticket.origin,
            reference_ticket.destination,
            reference_ticket.departure_at,
        )
        return Ticket(
            origin=reference_ticket.origin,
            destination=reference_ticket.destination,
            price=reference_ticket.price,
            airline=reference_ticket.airline,
            departure_at=reference_ticket.departure_at,
            transfers=reference_ticket.transfers,
            link=link,
            source="Tutu.ru",
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def _fetch_tutu_route_min_price(
        self,
        city_from: str,
        city_to: str,
        iata_from: str,
        iata_to: str,
        departure_date: date | None,
    ) -> int | None:
        from_slug = self.IATA_TO_TUTU_SLUG.get(iata_from.upper(), city_from)
        to_slug = self.IATA_TO_TUTU_SLUG.get(iata_to.upper(), city_to)
        route_base = f"https://avia.tutu.ru/f/{from_slug}/{to_slug}/"

        from_id = self.IATA_TO_TUTU_ID.get(iata_from.upper())
        to_id = self.IATA_TO_TUTU_ID.get(iata_to.upper())
        if from_id and to_id and departure_date:
            api_price = self._fetch_tutu_offers_api_min_price(from_id, to_id, departure_date)
            if api_price is not None:
                return api_price

        params = {"class": "Y", "passengers": 100, "travelers": 1}
        if from_id and to_id and departure_date:
            params["route[0]"] = f"{from_id}-{departure_date.strftime('%d%m%Y')}-{to_id}"

        route_url = requests.Request("GET", route_base, params=params).prepare().url
        rendered_price = extract_rendered_price(
            route_url,
            patterns=[
                r"Прямой\s+от\s*(\d{1,3}(?:[ \u00A0]\d{3})+|\d{4,6})\s*₽",
                r"Самый\s+деш[её]вый.{0,500}?(\d{1,3}(?:[ \u00A0]\d{3})+|\d{4,6})\s*₽.{0,120}?за\s+одного",
                r"от\s*(\d{1,3}(?:[ \u00A0]\d{3})+|\d{4,6})\s*₽",
            ],
            price_min=self.PRICE_MIN,
            price_max=self.PRICE_MAX,
        )
        if rendered_price is not None:
            return rendered_price

        try:
            response = self.session.get(route_base, params=params, timeout=40)
            response.raise_for_status()
        except requests.RequestException:
            return None

        return self._extract_price_from_text(response.text)

    def _fetch_tutu_offers_api_min_price(self, from_id: int, to_id: int, departure_date: date) -> int | None:
        base_payload = {
            "passengers": {"child": 0, "infant": 0, "full": 1},
            "serviceClass": "Y",
            "routes": [{"departureCityId": int(from_id), "arrivalCityId": int(to_id), "departureDate": departure_date.isoformat()}],
            "searchId": str(uuid.uuid4()),
            "sessionId": str(uuid.uuid4()),
            "pageId": "airparser",
            "userData": {"referenceToken": "", "screenSize": 1366},
            "source": "offers",
        }

        attempts = [
            ("https://offers-api.tutu.ru/avia/offers", base_payload),
            (
                "https://offers-api.tutu.ru/avia/offers/v2",
                {**base_payload, "dynamicFilters": {}, "offset": 0, "limit": 30, "isNewSearch": True},
            ),
        ]

        for url, payload in attempts:
            try:
                response = self.session.post(
                    url,
                    json=payload,
                    timeout=45,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
            except requests.RequestException:
                continue

            parsed = None
            try:
                parsed = response.json()
            except Exception:
                parsed = None

            if parsed is not None:
                candidates = self._extract_price_candidates(parsed)
                if candidates:
                    return candidates[0]

            text = response.text or ""
            for raw in re.findall(r'"amount"\s*:\s*(\d{4,6})', text, flags=re.IGNORECASE):
                numeric = int(raw)
                if self.PRICE_MIN <= numeric <= self.PRICE_MAX:
                    return numeric

        return None

    def _extract_price_candidates(self, node: object) -> list[int]:
        results: list[int] = []

        def walk(value: object, key_path: str = "") -> None:
            if isinstance(value, dict):
                for k, v in value.items():
                    walk(v, f"{key_path}.{k}".lower())
                return
            if isinstance(value, list):
                for item in value:
                    walk(item, key_path)
                return
            if not isinstance(value, (int, float)):
                return

            strict_markers = ("price", "amount", "minprice", "cheapest", "total")
            if not any(marker in key_path for marker in strict_markers):
                return

            numeric = int(value)
            if self.PRICE_MIN <= numeric <= self.PRICE_MAX:
                results.append(numeric)

        walk(node)
        return results

    def _extract_price_from_text(self, text: str) -> int | None:
        patterns = [
            r"Прямой\s+от\s*(\d{1,3}(?:[ \u00A0]\d{3})+|\d{4,6})\s*₽",
            r"от\s*(\d{1,3}(?:[ \u00A0]\d{3})+|\d{4,6})\s*₽",
            r"(\d{1,3}(?:[ \u00A0]\d{3})+|\d{4,6})\s*₽\s*за\s+одного",
            r"(\d{1,3}(?:[ \u00A0]\d{3})+|\d{4,6})\s*₽",
        ]
        for pattern in patterns:
            for raw in re.findall(pattern, text, flags=re.IGNORECASE | re.DOTALL):
                numeric = int(re.sub(r"\D", "", raw))
                if self.PRICE_MIN <= numeric <= self.PRICE_MAX:
                    return numeric
        return None

    def _build_tutu_hot_link(self, city_from: str, city_to: str, iata_from: str, iata_to: str, departure_at: str) -> str:
        from_slug = self.IATA_TO_TUTU_SLUG.get(iata_from.upper(), city_from)
        to_slug = self.IATA_TO_TUTU_SLUG.get(iata_to.upper(), city_to)
        route_base = f"https://avia.tutu.ru/f/{from_slug}/{to_slug}/"

        dep = self._extract_date(departure_at)
        from_id = self.IATA_TO_TUTU_ID.get(iata_from.upper())
        to_id = self.IATA_TO_TUTU_ID.get(iata_to.upper())
        if dep and from_id and to_id:
            return f"{route_base}?class=Y&passengers=100&route[0]={from_id}-{dep.strftime('%d%m%Y')}-{to_id}&travelers=1"
        return route_base

    @staticmethod
    def _extract_date(value: str) -> date | None:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None


class KupibiletClient:
    FILTER_PARAM = "%7B%22transportKind%22:%7B%22Airplane%22:true%7D%7D"
    PRICE_MIN = 3000
    PRICE_MAX = 500000

    def __init__(self, aviasales_client: AviasalesClient):
        self.aviasales_client = aviasales_client
        self.session = aviasales_client._build_session()

    def get_hot_tickets(
        self,
        route: str,
        limit: int = 10,
        request_limit: int = 100,
        departure_date: date | None = None,
        return_date: date | None = None,
        hot_offer: bool = False,
    ) -> list[Ticket]:
        if hot_offer and self._is_origin_only_route(route):
            origin_value = route.strip()
            if not origin_value:
                return []
            dep_date = departure_date or datetime.now(timezone.utc).date()
            return self._get_kupibilet_origin_only_hot_tickets(
                origin_value=origin_value,
                departure_date=dep_date,
                limit=limit,
            )

        iata_from, iata_to = self.aviasales_client.parse_route_to_iata(route)
        fallback_ticket = self._get_reference_ticket(
            route=route,
            request_limit=request_limit,
            departure_date=departure_date,
            return_date=return_date,
        )
        fallback_airline = fallback_ticket.airline if fallback_ticket else ""
        dep_date = departure_date or datetime.now(timezone.utc).date()
        route_link = self._build_kupibilet_search_link(iata_from.upper(), iata_to.upper(), dep_date, return_date)

        if hot_offer and departure_date and not return_date:
            sales_tickets = self._get_kupibilet_sales_offer_tickets(
                origin_code=iata_from.upper(),
                start_date=dep_date,
                end_date=return_date or dep_date,
                limit=max(1, limit),
                destination_code=iata_to.upper(),
            )
            if sales_tickets:
                return sales_tickets[: max(1, limit)]

            hot_ticket = self._get_kupibilet_hot_offer_ticket(
                route_link=route_link,
                iata_from=iata_from,
                iata_to=iata_to,
                departure_date=dep_date,
                fallback_ticket=fallback_ticket,
            )
            if hot_ticket is not None:
                return [hot_ticket]
            pass

        route_min_price = self._fetch_kupibilet_route_min_price(route_link, dep_date, return_date)
        used_fallback = False
        if route_min_price is None:
            if not fallback_ticket:
                return []
            route_min_price = fallback_ticket.price
            used_fallback = True

        departure_at = fallback_ticket.departure_at if fallback_ticket else datetime.combine(dep_date, datetime.min.time(), tzinfo=timezone.utc).isoformat()
        return [
            Ticket(
                origin=iata_from,
                destination=iata_to,
                price=route_min_price,
                airline=fallback_airline or ("Нет данных Kupibilet (fallback Aviasales)" if used_fallback else "Найдено на Kupibilet"),
                departure_at=departure_at,
                transfers=fallback_ticket.transfers if fallback_ticket else 0,
                link=route_link,
                  source="Kupibilet",
                  updated_at=datetime.now(timezone.utc).isoformat(),
              )
          ]

    def get_hot_tickets_anywhere(
        self,
        origin_value: str,
        limit: int = 10,
        departure_date: date | None = None,
        hot_offer: bool = False,
        deep_scan: bool = True,
    ) -> list[Ticket]:
        safe_limit = max(1, limit)
        if hot_offer:
            hot_tickets = self._get_kupibilet_origin_only_hot_tickets(
                origin_value=origin_value,
                departure_date=departure_date,
                limit=safe_limit,
                deep_scan=deep_scan,
            )
            if hot_tickets:
                return hot_tickets[:safe_limit]

        dep_date = departure_date or datetime.now(timezone.utc).date()

        reference_tickets = self.aviasales_client.get_hot_tickets_anywhere(
            origin_value=origin_value,
            limit=safe_limit,
            request_limit=max(100, safe_limit * 8),
            departure_date=dep_date,
            refine_exact=True,
        )
        if not reference_tickets:
            reference_tickets = self.aviasales_client.get_hot_tickets_anywhere(
                origin_value=origin_value,
                limit=safe_limit,
                request_limit=max(100, safe_limit * 8),
                departure_date=dep_date,
                refine_exact=False,
            )

        tickets: list[Ticket] = []
        seen_keys: set[tuple[str, str, int]] = set()
        for reference_ticket in reference_tickets:
            dedupe_key = (
                reference_ticket.destination,
                reference_ticket.departure_at,
                reference_ticket.price,
            )
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            fallback_ticket = self.build_fallback_ticket(reference_ticket)
            tickets.append(fallback_ticket)
            if len(tickets) >= safe_limit:
                break
        return tickets

    @staticmethod
    def _is_origin_only_route(route: str) -> bool:
        cleaned = str(route or "").strip()
        if not cleaned:
            return False
        return all(separator not in cleaned for separator in (" - ", " — ", " – "))

    def _get_kupibilet_origin_only_hot_tickets(
        self,
        origin_value: str,
        departure_date: date | None,
        limit: int,
        deep_scan: bool = True,
    ) -> list[Ticket]:
        try:
            origin_code = self.aviasales_client._resolve_location_code(origin_value).upper()
        except requests.RequestException:
            return []
        except ValueError:
            return []

        sales_tickets = self._get_kupibilet_sales_offer_tickets(
            origin_code=origin_code,
            start_date=None,
            end_date=None,
            limit=limit,
            enrich_exact_price=False,
            deep_scan=deep_scan,
        )
        if sales_tickets:
            return sales_tickets

        effective_date = datetime.now(timezone.utc).date()
        route_link = self._build_kupibilet_origin_only_link(origin_code, effective_date)
        offers = self._extract_hot_offer_payloads(route_link)
        if not offers:
            return []

        tickets: list[Ticket] = []
        seen_keys: set[tuple[str, int, str]] = set()
        updated_at = datetime.now(timezone.utc).isoformat()

        for offer in offers:
            destination_name = str(offer.get("destination_name") or "").strip()
            if not destination_name:
                continue

            try:
                destination_code = self.aviasales_client._resolve_location_code(destination_name).upper()
            except Exception:
                destination_code = destination_name.upper()

            departure_at = datetime.combine(effective_date, datetime.min.time(), tzinfo=timezone.utc).isoformat()
            link = self._normalize_kupibilet_booking_link(str(offer.get("link") or route_link))
            offer_price = self._coerce_int(offer.get("price"))
            if offer_price is None:
                continue
            ticket_key = (destination_code, offer_price, link)
            if ticket_key in seen_keys:
                continue
            seen_keys.add(ticket_key)

            original_price = self._coerce_int(offer.get("original_price"))
            discount_percent = self._coerce_int(offer.get("discount_percent"))

            tickets.append(
                Ticket(
                    origin=origin_code,
                    destination=destination_code,
                    price=offer_price,
                    airline="Горячая цена Kupibilet",
                    departure_at=departure_at,
                    transfers=0,
                    link=link,
                    source="Kupibilet",
                    updated_at=updated_at,
                    original_price=original_price,
                    hot_discount_percent=discount_percent,
                    hot_expires_at=str(offer["expires_at"]),
                    special_offer_label=str(offer.get("label") or "Горячая цена"),
                )
            )

            if len(tickets) >= max(1, limit):
                break

        tickets.sort(key=lambda item: (item.price, item.destination))
        return tickets

    def _get_kupibilet_hot_offer_ticket(
        self,
        route_link: str,
        iata_from: str,
        iata_to: str,
        departure_date: date,
        fallback_ticket: Ticket | None,
    ) -> Ticket | None:
        offer = self._extract_hot_offer_payload(route_link, iata_from=iata_from, iata_to=iata_to)
        if not offer:
            return None

        departure_at = (
            fallback_ticket.departure_at
            if fallback_ticket and fallback_ticket.departure_at
            else datetime.combine(departure_date, datetime.min.time(), tzinfo=timezone.utc).isoformat()
        )
        transfers = fallback_ticket.transfers if fallback_ticket else 0
        airline = fallback_ticket.airline if fallback_ticket and fallback_ticket.airline else "Горячая цена Kupibilet"

        offer_price = self._coerce_int(offer.get("price"))
        if offer_price is None:
            return None
        original_price = self._coerce_int(offer.get("original_price"))
        discount_percent = self._coerce_int(offer.get("discount_percent"))

        return Ticket(
            origin=iata_from,
            destination=iata_to,
            price=offer_price,
            airline=airline,
            departure_at=departure_at,
            transfers=transfers,
            link=self._normalize_kupibilet_booking_link(str(offer.get("link") or route_link)),
            source="Kupibilet",
            updated_at=datetime.now(timezone.utc).isoformat(),
            original_price=original_price,
            hot_discount_percent=discount_percent,
            hot_expires_at=str(offer["expires_at"]),
            special_offer_label="Горячая цена",
        )

    def _get_kupibilet_rendered_fallback_tickets(
        self,
        route_link: str,
        iata_from: str,
        iata_to: str,
        departure_date: date,
        limit: int,
    ) -> list[Ticket]:
        cards = extract_rendered_ticket_cards(route_link, limit=max(1, limit))
        if not cards:
            return []

        tickets: list[Ticket] = []
        seen_links: set[str] = set()
        updated_at = datetime.now(timezone.utc).isoformat()

        for card in cards:
            href = str(card.get("href") or "").strip()
            if not href or href in seen_links:
                continue
            seen_links.add(href)

            price = self._extract_first_price_number(str(card.get("price_text") or ""))
            if price is None:
                continue

            full_text = str(card.get("text") or "")
            baggage_info = self._extract_baggage_info_from_card(str(card.get("baggage_text") or ""), full_text)
            departure_at = self._extract_departure_at_from_card(full_text, departure_date)
            transfers = self._extract_transfers_from_card(full_text)

            tickets.append(
                Ticket(
                    origin=iata_from,
                    destination=iata_to,
                    price=price,
                    airline="Kupibilet",
                    departure_at=departure_at,
                    transfers=transfers,
                    link=href if href.startswith("http") else f"https://www.kupibilet.ru{href}",
                    source="Kupibilet",
                    updated_at=updated_at,
                    baggage_info=baggage_info,
                    special_offer_label="Kupibilet",
                )
            )

            if len(tickets) >= max(1, limit):
                break

        return tickets

    def _get_reference_ticket(
        self,
        route: str,
        request_limit: int,
        departure_date: date | None,
        return_date: date | None,
    ) -> Ticket | None:
        requests_limit = max(request_limit, 100)

        if departure_date and return_date and return_date >= departure_date:
            ranged = self.aviasales_client.get_hot_tickets_in_range(
                route=route,
                start_date=departure_date,
                end_date=return_date,
                limit=1,
                request_limit=requests_limit,
            )
            if ranged:
                return ranged[0]

        if departure_date:
            exact = self.aviasales_client.get_hot_tickets(
                route=route,
                limit=1,
                request_limit=requests_limit,
                departure_date=departure_date,
                strict_exact_price=False,
            )
            if exact:
                return exact[0]

            nearby = self.aviasales_client.get_hot_tickets_in_range(
                route=route,
                start_date=departure_date,
                end_date=departure_date + timedelta(days=3),
                limit=1,
                request_limit=requests_limit,
            )
            if nearby:
                return nearby[0]

        generic = self.aviasales_client.get_hot_tickets(
            route=route,
            limit=1,
            request_limit=requests_limit,
            departure_date=None,
            strict_exact_price=False,
        )
        return generic[0] if generic else None

    def get_available_departure_dates(self, route: str, request_limit: int = 100) -> list[date]:
        return self.aviasales_client.get_available_departure_dates(route=route, request_limit=request_limit)

    def build_fallback_ticket(self, reference_ticket: Ticket) -> Ticket:
        dep_date = self._extract_departure_date(reference_ticket.departure_at) or datetime.now(timezone.utc).date()
        link = self._build_kupibilet_search_link(
            reference_ticket.origin.upper(),
            reference_ticket.destination.upper(),
            dep_date,
            None,
        )
        return Ticket(
            origin=reference_ticket.origin,
            destination=reference_ticket.destination,
            price=reference_ticket.price,
            airline=reference_ticket.airline,
            departure_at=reference_ticket.departure_at,
            transfers=reference_ticket.transfers,
            link=link,
            source="Kupibilet",
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _extract_departure_date(value: str) -> date | None:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None

    def _fetch_kupibilet_route_min_price(self, url: str, departure_date: date | None, return_date: date | None) -> int | None:
        try:
            response = self.session.get(url, timeout=40, headers={"Accept-Language": "ru-RU,ru;q=0.9"})
            response.raise_for_status()
        except requests.RequestException:
            return None

        calendar_price = self._extract_kupibilet_calendar_price(response.text, departure_date, return_date)
        if calendar_price is not None:
            return calendar_price

        rendered_price = extract_rendered_price(
            url,
            patterns=[
                r"Самый\s+деш[её]вый.{0,900}?(\d{1,3}(?:[ \u00A0]\d{3})+|\d{4,6})\s*₽\s*за\s+всех\s+пассажиров",
                r"(\d{1,3}(?:[ \u00A0]\d{3})+|\d{4,6})\s*₽\s*за\s+всех\s+пассажиров",
            ],
            price_min=self.PRICE_MIN,
            price_max=self.PRICE_MAX,
        )
        if rendered_price is not None:
            return rendered_price

        for raw in re.findall(r"(\d{1,3}(?:[ \u00A0]\d{3})+|\d{4,6})\s*₽", response.text, flags=re.IGNORECASE):
            numeric = int(re.sub(r"\D", "", raw))
            if self.PRICE_MIN <= numeric <= self.PRICE_MAX:
                return numeric

        return None

    def _extract_kupibilet_calendar_price(self, text: str, departure_date: date | None, return_date: date | None) -> int | None:
        if not departure_date or not return_date:
            return None

        months = {1: "янв", 2: "фев", 3: "мар", 4: "апр", 5: "май", 6: "июн", 7: "июл", 8: "авг", 9: "сен", 10: "окт", 11: "ноя", 12: "дек"}
        dep = f"{departure_date.day}\\s*{months[departure_date.month]}"
        ret = f"{return_date.day}\\s*{months[return_date.month]}"
        pattern = rf"{dep}\\s*[—-]\\s*{ret}.{{0,80}}?(\\d{{1,3}}(?:[ \\u00A0]\\d{{3}})+|\\d{{4,6}})\\s*₽"

        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return None

        numeric = int(re.sub(r"\D", "", match.group(1)))
        if self.PRICE_MIN <= numeric <= self.PRICE_MAX:
            return numeric
        return None

    def _extract_hot_offer_payload(self, url: str, iata_from: str, iata_to: str) -> dict | None:
        offers = self._extract_hot_offer_payloads(url, iata_from=iata_from, iata_to=iata_to)
        return offers[0] if offers else None

    def _extract_hot_offer_payloads(
        self,
        url: str,
        iata_from: str = "",
        iata_to: str = "",
    ) -> list[dict]:
        page_payload = extract_rendered_page_payload(url, timeout_ms=16000)
        if not page_payload:
            return []

        text, html = page_payload
        route_patterns, route_tokens = self._build_hot_offer_route_matchers(iata_from=iata_from, iata_to=iata_to)

        normalized_text = re.sub(r"\s+", " ", text or "")
        normalized_html = re.sub(r"\s+", " ", html or "")

        payloads = self._find_hot_offer_in_payload(normalized_text, route_patterns, route_tokens)
        if payloads:
            return payloads
        return self._find_hot_offer_in_payload(normalized_html, route_patterns, route_tokens)

    def _build_hot_offer_route_matchers(self, iata_from: str, iata_to: str) -> tuple[list[str], set[str]]:
        route_patterns: list[str] = []
        route_tokens: set[str] = {iata_from.upper(), iata_to.upper()}

        origin_names = {
            self.aviasales_client.resolve_location_name(iata_from),
            iata_from.upper(),
        }
        destination_names = {
            self.aviasales_client.resolve_location_name(iata_to),
            iata_to.upper(),
        }

        for value in origin_names | destination_names:
            cleaned = re.sub(r"\s+", " ", str(value or "").strip())
            if cleaned:
                route_tokens.add(cleaned.lower())
                route_tokens.update(token.lower() for token in re.findall(r"[A-Za-zА-Яа-яЁё]+", cleaned) if len(token) >= 3)

        if iata_from and iata_to:
            for left in origin_names:
                for right in destination_names:
                    if left and right:
                        route_patterns.append(rf"{re.escape(left)}\s*[—–-]\s*{re.escape(right)}")

        return route_patterns, route_tokens

    def _find_hot_offer_in_payload(self, payload: str, route_patterns: list[str], route_tokens: set[str]) -> list[dict]:
        if not payload:
            return []

        windows: list[str] = []
        if route_patterns:
            for route_pattern in route_patterns:
                for match in re.finditer(route_pattern, payload, flags=re.IGNORECASE):
                    start = max(0, match.start() - 700)
                    end = min(len(payload), match.end() + 700)
                    windows.append(payload[start:end])
        timer_pattern = re.compile(
            r"(?:скидка\s*)?[−-]?\s*(\d{1,2})%\s*(?:[∙·•]|&middot;|\.)?\s*(\d{1,2}:\d{2}:\d{2})",
            flags=re.IGNORECASE,
        )
        for match in timer_pattern.finditer(payload):
            start = max(0, match.start() - 900)
            end = min(len(payload), match.end() + 1600)
            windows.append(payload[start:end])

        if not windows:
            windows = [payload]

        offers: list[dict] = []
        seen_chunks: set[str] = set()

        for chunk in windows:
            fingerprint = chunk[:400]
            if fingerprint in seen_chunks:
                continue
            seen_chunks.add(fingerprint)

            timer_match = timer_pattern.search(chunk)
            if not timer_match:
                continue

            unique_prices = self._extract_hot_offer_prices(chunk)
            if len(unique_prices) < 2:
                continue

            original_price = max(unique_prices[0], unique_prices[1])
            current_price = min(unique_prices[0], unique_prices[1])
            if current_price >= original_price:
                continue

            timer_text = timer_match.group(2)
            expires_at = self._build_hot_offer_expiry(timer_text)
            if not expires_at:
                continue

            offer_link = self._extract_hot_offer_link(chunk)
            discount_percent = int(timer_match.group(1))
            score = self._score_hot_offer_chunk(chunk, route_patterns, route_tokens)
            if offer_link:
                score += 2
            route_names = self._extract_hot_offer_route_names(chunk)

            candidate = {
                "price": current_price,
                "original_price": original_price,
                "discount_percent": discount_percent,
                "expires_at": expires_at,
                "link": offer_link,
                "score": score,
            }
            if route_names:
                candidate["origin_name"] = route_names[0]
                candidate["destination_name"] = route_names[1]
            if "скидка" in chunk.lower():
                candidate["label"] = "Скидка"
            offers.append(candidate)

        offers.sort(key=lambda item: (-self._safe_sort_price(item.get("score"), fallback=0), self._safe_sort_price(item.get("price"))))
        return offers

    def _extract_hot_offer_prices(self, chunk: str) -> list[int]:
        price_matches = re.findall(r"(\d{1,3}(?:[ \u00A0]\d{3})+|\d{4,6})\s*₽", chunk)
        unique_prices: list[int] = []
        for raw in price_matches:
            numeric = int(re.sub(r"\D", "", raw))
            if not (self.PRICE_MIN <= numeric <= self.PRICE_MAX):
                continue
            if numeric not in unique_prices:
                unique_prices.append(numeric)
        return unique_prices

    @staticmethod
    def _extract_first_price_number(text: str) -> int | None:
        match = re.search(r"(\d{1,3}(?:[ \u00A0]\d{3})+|\d{4,6})", text or "")
        if not match:
            return None
        value = int(re.sub(r"\D", "", match.group(1)))
        if value <= 0:
            return None
        return value

    @staticmethod
    def _coerce_int(value: object) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        digits = re.sub(r"\D", "", str(value))
        if not digits:
            return None
        try:
            return int(digits)
        except ValueError:
            return None

    @staticmethod
    def _extract_visible_card_prices(full_text: str) -> list[int]:
        values: list[int] = []
        for match in re.finditer(r"(\d{1,3}(?:[ \u00A0]\d{3})+|\d{4,6})\s*₽", full_text or ""):
            numeric = int(re.sub(r"\D", "", match.group(1)))
            if numeric <= 0:
                continue
            if numeric not in values:
                values.append(numeric)
        return values

    def _extract_kupibilet_booking_exact_price(self, link: str) -> int | None:
        if not link:
            return None

        selectors = [
            'h1[color="colorTextAccentNormal"]',
            'h1[class*="StyledTypography"]',
            'h1',
        ]
        for selector in selectors:
            price = extract_rendered_text_price(
                link,
                selector=selector,
                price_min=self.PRICE_MIN,
                price_max=self.PRICE_MAX,
                timeout_ms=7000,
            )
            if price is not None:
                return price

        return extract_rendered_price(
            link,
            patterns=[
                r'<h1[^>]*color="colorTextAccentNormal"[^>]*>(\d{1,3}(?:[ \u00A0\u202F]|&nbsp;)\d{3}|\d{4,6})\s*₽',
                r'<h1[^>]*class="[^"]*StyledTypography[^"]*"[^>]*>(\d{1,3}(?:[ \u00A0\u202F]|&nbsp;)\d{3}|\d{4,6})\s*₽',
            ],
            price_min=self.PRICE_MIN,
            price_max=self.PRICE_MAX,
            timeout_ms=7000,
            pick="first",
        )

    def get_live_ticket_snapshot(self, link: str) -> dict | None:
        normalized_link = self._normalize_kupibilet_booking_link(link)
        if not normalized_link:
            return None

        exact_price = self._extract_kupibilet_booking_exact_price(normalized_link)
        if exact_price is None:
            return None

        return {
            "link": normalized_link,
            "price": exact_price,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _extract_baggage_info_from_card(baggage_text: str, full_text: str) -> str:
        source = baggage_text or full_text
        match = re.search(r"(Багаж\s+\d+\s*кг(?:\s*[×x]\s*\d+)?)", source, flags=re.IGNORECASE)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()
        return ""

    @staticmethod
    def _extract_departure_at_from_card(full_text: str, departure_date: date) -> str:
        match = re.search(r"(\d{1,2}:\d{2})", full_text or "")
        if not match:
            return datetime.combine(departure_date, datetime.min.time(), tzinfo=timezone.utc).isoformat()
        hour, minute = [int(part) for part in match.group(1).split(":")]
        return datetime.combine(
            departure_date,
            datetime.min.time().replace(hour=hour, minute=minute),
            tzinfo=timezone.utc,
        ).isoformat()

    @staticmethod
    def _extract_transfers_from_card(full_text: str) -> int:
        lowered = (full_text or "").lower()
        if "без пересадок" in lowered:
            return 0
        match = re.search(r"(\d+)\s+пересад", lowered)
        if not match:
            return 0
        return int(match.group(1))

    @staticmethod
    def _extract_departure_at_from_special_card_text(full_text: str) -> str:
        source = re.sub(r"\s+", " ", str(full_text or "")).strip().lower()
        now = datetime.now(timezone.utc)
        if not source:
            return now.isoformat()

        month_map = {
            "янв": 1,
            "январ": 1,
            "фев": 2,
            "феврал": 2,
            "мар": 3,
            "март": 3,
            "апр": 4,
            "апрел": 4,
            "май": 5,
            "мая": 5,
            "июн": 6,
            "июл": 7,
            "авг": 8,
            "август": 8,
            "сен": 9,
            "сентябр": 9,
            "окт": 10,
            "октябр": 10,
            "ноя": 11,
            "ноябр": 11,
            "дек": 12,
            "декабр": 12,
        }

        route_time_match = re.search(r"(\d{1,2}:\d{2})\s*[—–-]\s*(\d{1,2}:\d{2})", source)
        departure_time = route_time_match.group(1) if route_time_match else ""
        date_match = re.search(r"(\d{1,2})\s+([а-яё]{3,10})", source, flags=re.IGNORECASE)
        if not departure_time or not date_match:
            return now.isoformat()

        month = None
        raw_month = date_match.group(2)
        for key, value in month_map.items():
            if raw_month.startswith(key):
                month = value
                break
        if month is None:
            return now.isoformat()

        day = int(date_match.group(1))
        hour, minute = [int(part) for part in departure_time.split(":")]
        year = now.year
        try:
            departure_dt = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
        except ValueError:
            return now.isoformat()

        if departure_dt < now - timedelta(days=45):
            try:
                departure_dt = departure_dt.replace(year=year + 1)
            except ValueError:
                pass
        return departure_dt.isoformat()

    @staticmethod
    def _extract_hot_offer_link(chunk: str) -> str:
        match = re.search(
            r"(https://www\.kupibilet\.ru/(?:mbooking|booking)/step[01]/[^\s\"'<>]+|/(?:mbooking|booking)/step[01]/[^\s\"'<>]+)",
            chunk,
            flags=re.IGNORECASE,
        )
        if not match:
            return ""
        return KupibiletClient._normalize_kupibilet_booking_link(match.group(1))

    @staticmethod
    def _extract_hot_offer_route_names(chunk: str) -> tuple[str, str] | None:
        route_match = re.search(
            r"([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\s-]{1,80}?)\s*(?:[—–-]|→)\s*([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\s-]{1,80})",
            chunk,
            flags=re.IGNORECASE,
        )
        if not route_match:
            return None

        left = re.sub(r"\s+", " ", route_match.group(1)).strip(" -—–")
        right = re.sub(r"\s+", " ", route_match.group(2)).strip(" -—–")
        if not left or not right:
            return None
        return left, right

    @staticmethod
    def _score_hot_offer_chunk(chunk: str, route_patterns: list[str], route_tokens: set[str]) -> int:
        score = 0
        lowered = chunk.lower()
        for route_pattern in route_patterns:
            if re.search(route_pattern, chunk, flags=re.IGNORECASE):
                score += 6
        for token in route_tokens:
            if token and token in lowered:
                score += 1
        if "на карте" in lowered:
            score += 1
        if "о городе" in lowered:
            score += 1
        return score

    @staticmethod
    def _build_hot_offer_expiry(timer_text: str) -> str:
        try:
            hours, minutes, seconds = [int(part) for part in timer_text.split(":")]
        except Exception:
            return ""
        if hours < 0 or minutes < 0 or seconds < 0:
            return ""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=hours, minutes=minutes, seconds=seconds)
        return expires_at.isoformat()

    @classmethod
    def _build_kupibilet_search_link(
        cls,
        origin: str,
        destination: str,
        departure_date: date | None,
        return_date: date | None,
    ) -> str:
        dep = departure_date.isoformat() if departure_date else datetime.now().date().isoformat()
        route0 = f"iatax:{origin}_{dep}_date_{dep}_iatax:{destination}"

        parts = [
            "https://www.kupibilet.ru/search?adult=1",
            "cabinClass=Y",
            "child=0",
            "childrenAges=[]",
            "infant=0",
            f"route[0]={route0}",
        ]

        if return_date:
            ret = return_date.isoformat()
            route1 = f"iatax:{destination}_{ret}_date_{ret}_iatax:{origin}"
            parts.append(f"route[1]={route1}")

        parts.append("v=2")
        parts.append(f"filter={cls.FILTER_PARAM}")
        return "&".join(parts)

    @classmethod
    def _build_kupibilet_origin_only_link(cls, origin: str, departure_date: date | None) -> str:
        dep = departure_date.isoformat() if departure_date else datetime.now().date().isoformat()
        route0 = f"iatax:{origin}_{dep}_date_{dep}"
        parts = [
            "https://www.kupibilet.ru/search?adult=1",
            "cabinClass=Y",
            "child=0",
            "childrenAges=[]",
            "infant=0",
            f"route[0]={route0}",
            "v=2",
        ]
        return "&".join(parts)

    @staticmethod
    def _normalize_kupibilet_booking_link(value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            return ""
        if normalized.startswith("/"):
            normalized = f"https://www.kupibilet.ru{normalized}"
        normalized = normalized.replace("https://www.kupibilet.ru/booking/step0/", "https://www.kupibilet.ru/mbooking/step0/")
        normalized = normalized.replace("https://www.kupibilet.ru/booking/step1/", "https://www.kupibilet.ru/mbooking/step1/")
        normalized = normalized.replace("https://www.kupibilet.ru//", "https://www.kupibilet.ru/")
        return normalized

    @staticmethod
    def _extract_discount_percent_from_label(text: str, price: int, original_price: int | None) -> int | None:
        match = re.search(r"(\d{1,2})\s*%", text or "", flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
        if original_price and original_price > price > 0:
            return max(1, round((original_price - price) * 100 / original_price))
        return None

    @staticmethod
    def _extract_timer_text_from_text(text: str) -> str:
        match = re.search(r"(\d{1,2}:\d{2}:\d{2})", str(text or ""), flags=re.IGNORECASE)
        return match.group(1) if match else ""

    @staticmethod
    def _extract_special_offer_label_from_text(text: str) -> str:
        source = re.sub(r"\s+", " ", str(text or "")).strip()
        if not source:
            return ""

        timer_match = re.search(
            r"((?:Скидка\s*)?[−-]?\s*\d{1,2}%\s*(?:[∙·•]|&middot;|\.)?\s*\d{1,2}:\d{2}:\d{2}|Скидка\s*\d{1,2}%|Выгодно|Супер\s+выгодно)",
            source,
            flags=re.IGNORECASE,
        )
        if not timer_match:
            return ""
        return re.sub(r"\s+", " ", timer_match.group(1)).strip()

    @staticmethod
    def _card_mentions_target_date(text: str, target_date: date) -> bool:
        source = re.sub(r"\s+", " ", str(text or "")).strip().lower()
        if not source:
            return False

        month_map = {
            "янв": 1,
            "январ": 1,
            "фев": 2,
            "феврал": 2,
            "мар": 3,
            "март": 3,
            "апр": 4,
            "апрел": 4,
            "мая": 5,
            "май": 5,
            "июн": 6,
            "июн": 6,
            "июл": 7,
            "июл": 7,
            "авг": 8,
            "август": 8,
            "сен": 9,
            "сентябр": 9,
            "окт": 10,
            "октябр": 10,
            "ноя": 11,
            "ноябр": 11,
            "дек": 12,
            "декабр": 12,
        }

        for match in re.finditer(r"(\d{1,2})\s+([а-яё]{3,10})", source, flags=re.IGNORECASE):
            day = int(match.group(1))
            raw_month = match.group(2)
            month = None
            for key, value in month_map.items():
                if raw_month.startswith(key):
                    month = value
                    break
            if month == target_date.month and day == target_date.day:
                return True
        return False

    def _get_kupibilet_sales_offer_tickets(
        self,
        origin_code: str,
        start_date: date | None,
        end_date: date | None,
        limit: int,
        destination_code: str = "",
        enrich_exact_price: bool = True,
        deep_scan: bool = True,
    ) -> list[Ticket]:
        sales_link = f"https://www.kupibilet.ru/sales?departureCity={origin_code}"
        destination_filter = str(destination_code or "").upper()
        cards = extract_rendered_kupibilet_special_cards(
            sales_link,
            limit=(max(18, max(1, limit) * 3) if not deep_scan else max(80, max(1, limit) * 10)),
            timeout_ms=(25000 if not deep_scan else 40000),
            deep_scan=deep_scan,
        )
        if not cards:
            return []

        # Sort: cards with timers first so they survive dedup
        cards.sort(key=lambda c: 0 if c.get("tag_text") else 1)

        tickets: list[Ticket] = []
        seen_keys: set[tuple[str, str, int, str]] = set()
        updated_at = datetime.now(timezone.utc).isoformat()

        for card in cards:
            full_text = str(card.get("text") or "")
            raw_full_text = str(card.get("raw_text") or full_text)
            try:
                payload = json.loads(str(card.get("json") or ""))
            except json.JSONDecodeError:
                payload = {}

            departure_time = str(payload.get("departureTime") or "")
            try:
                departure_dt = datetime.fromisoformat(departure_time.replace("Z", "+00:00"))
            except ValueError:
                departure_time = self._extract_departure_at_from_special_card_text(full_text)
                try:
                    departure_dt = datetime.fromisoformat(departure_time.replace("Z", "+00:00"))
                except ValueError:
                    departure_dt = datetime.now(timezone.utc)

            dep_date = departure_dt.date()
            if start_date and end_date and (dep_date < start_date or dep_date > end_date):
                if not (start_date == end_date and self._card_mentions_target_date(full_text, start_date)):
                    continue

            offers_payload = payload.get("offers") or {}
            raw_link = str(offers_payload.get("url") or card.get("link_text") or "")
            link = self._normalize_kupibilet_booking_link(raw_link)

            current_destination_code = str((payload.get("arrivalAirport") or {}).get("iataCode") or "").upper()
            current_origin_code = origin_code if not destination_filter else str((payload.get("departureAirport") or {}).get("iataCode") or origin_code).upper()
            route_names = self._extract_hot_offer_route_names(full_text)
            if route_names:
                try:
                    current_destination_code = self.aviasales_client._resolve_location_code(route_names[1]).upper()
                except Exception:
                    current_destination_code = current_destination_code or route_names[1].upper()
                if destination_filter:
                    try:
                        current_origin_code = self.aviasales_client._resolve_location_code(route_names[0]).upper()
                    except Exception:
                        current_origin_code = current_origin_code or route_names[0].upper()
                else:
                    current_origin_code = origin_code
            if not current_destination_code:
                continue
            if not link:
                link = f"https://www.kupibilet.ru/sales?departureCity={origin_code}"
            if destination_filter and current_destination_code != destination_filter:
                continue

            current_price_text = str(card.get("current_price_text") or "")
            price = self._extract_first_price_number(current_price_text)
            original_price = self._extract_first_price_number(str(card.get("original_price_text") or ""))
            visible_prices = self._extract_visible_card_prices(raw_full_text)

            if original_price is None and visible_prices:
                if price is not None:
                    higher_prices = [value for value in visible_prices if value > price]
                    if higher_prices:
                        original_price = max(higher_prices)
                elif len(visible_prices) >= 2:
                    original_price = max(visible_prices)

            if price is None:
                if visible_prices:
                    if original_price and original_price in visible_prices:
                        non_original_prices = [value for value in visible_prices if value != original_price]
                        price = non_original_prices[0] if non_original_prices else None
                    if price is None:
                        price = min(visible_prices)
            if price is None:
                price = self._extract_first_price_number(str(offers_payload.get("price") or ""))
            if price is None:
                continue

            ticket_key = (
                link,
                departure_dt.astimezone(timezone.utc).isoformat(),
                price,
                current_destination_code,
            )
            if ticket_key in seen_keys:
                continue
            seen_keys.add(ticket_key)

            if enrich_exact_price:
                exact_booking_price = self._extract_kupibilet_booking_exact_price(link) 
                if exact_booking_price is not None:
                    price = exact_booking_price

            tag_text = re.sub(r"\s+", " ", str(card.get("tag_text") or "").strip())
            if not tag_text:
                tag_text = self._extract_special_offer_label_from_text(raw_full_text)
            timer_match = re.search(r"(\d{1,2}:\d{2}:\d{2})", tag_text)
            timer_text = timer_match.group(1) if timer_match else self._extract_timer_text_from_text(raw_full_text)
            expires_at = self._build_hot_offer_expiry(timer_text) if timer_text else ""
            discount_percent = self._extract_discount_percent_from_label(tag_text, price, original_price)
            if discount_percent:
                if timer_text:
                    tag_text = f"Скидка {discount_percent}% · {timer_text}"
                else:
                    tag_text = f"Скидка {discount_percent}%"
            airline_name = str((payload.get("provider") or {}).get("name") or "Kupibilet")

            tickets.append(
                Ticket(
                    origin=current_origin_code or origin_code,
                    destination=current_destination_code,
                    price=price,
                    airline=airline_name,
                    departure_at=departure_dt.astimezone(timezone.utc).isoformat(),
                    transfers=self._extract_transfers_from_card(full_text),
                    link=link,
                    source="Kupibilet",
                    updated_at=updated_at,
                    original_price=original_price,
                    hot_discount_percent=discount_percent,
                    hot_expires_at=expires_at,
                    special_offer_label=tag_text or "Наши лазейки",
                )
            )

            if len(tickets) >= max(1, limit):
                break

        tickets.sort(key=lambda item: (item.price, item.departure_at, item.destination))
        return tickets


