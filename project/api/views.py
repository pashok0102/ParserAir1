from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from threading import Lock
from time import monotonic

import requests
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from dotenv import load_dotenv

from app.config import load_settings
from app.parsers import AviasalesClient, KupibiletClient, Ticket, TutuClient
from .models import FavoriteTicket, SearchHistory

load_dotenv()
settings = load_settings()
aviasales_client = AviasalesClient(settings)
tutu_client = TutuClient(aviasales_client)
kupibilet_client = KupibiletClient(aviasales_client)
User = get_user_model()
RESULTS_DIR = Path(__file__).resolve().parent.parent / 'parsed_results'
RESULTS_DIR.mkdir(exist_ok=True)
PERIOD_MAX_WORKERS = 6
SOURCE_MAX_WORKERS = 3
AVIASALES_POOL_WORKERS = 4
TUTU_POOL_WORKERS = 2
KUPIBILET_POOL_WORKERS = 2
LONG_RANGE_DAYS_THRESHOLD = 21
LONG_RANGE_SOURCE_TIMEOUT_SECONDS = 12
RANGE_CHUNK_DAYS = 21
RANGE_CHUNK_MAX_WORKERS = 4
LONG_RANGE_AVIASALES_TIMEOUT_SECONDS = 15
SHORT_RANGE_AVIASALES_TIMEOUT_SECONDS = 10
PARSER_EXECUTORS = {
    'aviasales': ThreadPoolExecutor(max_workers=AVIASALES_POOL_WORKERS, thread_name_prefix='aviasales'),
    'tutu': ThreadPoolExecutor(max_workers=TUTU_POOL_WORKERS, thread_name_prefix='tutu'),
    'kupibilet': ThreadPoolExecutor(max_workers=KUPIBILET_POOL_WORKERS, thread_name_prefix='kupibilet'),
}
SEARCH_CACHE_TTL_SECONDS = 180
SEARCH_CACHE_VERSION = "v22-kupibilet-moscow-city-and-old-price"
SEARCH_CACHE: dict[tuple, tuple[float, list[Ticket]]] = {}
SEARCH_CACHE_LOCK = Lock()


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def parse_optional_int(value) -> int | None:
    if value in (None, ''):
        return None
    return int(value)


def parse_optional_str(value) -> str | None:
    if value in (None, ''):
        return None
    text = str(value).strip()
    return text or None


def parse_boolish(value) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, '', 0, '0'):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return bool(value)


def parse_search_payload(request):
    if request.method == 'GET':
        return {key: value for key, value in request.GET.items()}
    return parse_json_body(request)


def date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def parse_departure_for_sort(value: str) -> str:
    return value or '9999-12-31T23:59:59+00:00'


def parse_json_body(request):
    try:
        return json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return None


def build_search_cache_key(
    *,
    source_name: str,
    route: str,
    limit: int | None,
    departure_date: date | None,
    return_date: date | None,
    anywhere: bool,
    kupibilet_hot_offer: bool = False,
    deep_scan: bool = True,
):
    return (
        SEARCH_CACHE_VERSION,
        source_name,
        route.strip().lower(),
        limit,
        departure_date.isoformat() if departure_date else None,
        return_date.isoformat() if return_date else None,
        anywhere,
        kupibilet_hot_offer,
        deep_scan,
    )


def get_cached_search_result(cache_key: tuple) -> list[Ticket] | None:
    now = monotonic()
    with SEARCH_CACHE_LOCK:
        cached = SEARCH_CACHE.get(cache_key)
        if not cached:
            return None
        expires_at, tickets = cached
        if expires_at <= now:
            SEARCH_CACHE.pop(cache_key, None)
            return None
        return list(tickets)


def set_cached_search_result(cache_key: tuple, tickets: list[Ticket]) -> None:
    with SEARCH_CACHE_LOCK:
        SEARCH_CACHE[cache_key] = (monotonic() + SEARCH_CACHE_TTL_SECONDS, list(tickets))


def run_parser_task(source_name: str, fn):
    executor = PARSER_EXECUTORS.get(source_name)
    if executor is None:
        return fn()
    try:
        return executor.submit(fn).result()
    except RuntimeError:
        return fn()


def run_with_timeout(fn, timeout_seconds: int, fallback):
    try:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(fn)
        try:
            done, _ = wait([future], timeout=timeout_seconds)
            if done:
                return future.result()
            future.cancel()
            return fallback
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
    except RuntimeError:
        return fn()


def user_payload(user):
    return {
        'id': user.id,
        'username': user.username,
    }


def build_ticket_key(*, source: str, origin: str, destination: str, departure_at: str, price: int, link: str) -> str:
    safe_link = link or ''
    return f'{source}|{origin}|{destination}|{departure_at}|{price}|{safe_link}'


def normalize_ticket_link(link: str) -> str:
    if not link:
        return ''
    return link if link.startswith('http') else f'https://www.aviasales.ru{link}'


def serialize_favorite(favorite: FavoriteTicket) -> dict:
    origin_code = favorite.origin
    destination_code = favorite.destination
    return {
        'ticket_key': favorite.ticket_key,
        'origin': aviasales_client.resolve_location_name(origin_code),
        'destination': aviasales_client.resolve_location_name(destination_code),
        'origin_airport': aviasales_client.resolve_airport_name(origin_code),
        'destination_airport': aviasales_client.resolve_airport_name(destination_code),
        'origin_code': origin_code,
        'destination_code': destination_code,
        'price': favorite.price,
        'airline': favorite.airline,
        'departure_at': favorite.departure_at,
        'transfers': favorite.transfers,
        'link': favorite.link,
        'source': favorite.source,
        'updated_at': favorite.updated_at,
        'is_favorite': True,
        'estimated_price': bool(favorite.estimated_price),
        'baggage_info': str(favorite.baggage_info or ''),
        'original_price': favorite.original_price,
        'hot_discount_percent': favorite.hot_discount_percent,
        'hot_expires_at': str(favorite.hot_expires_at or ''),
        'special_offer_label': str(favorite.special_offer_label or ''),
    }


def serialize_search_history(item: SearchHistory) -> dict:
    kupibilet_hot_offer = item.source == 'kupibilet' and item.anywhere
    return {
        'id': item.id,
        'route': item.route,
        'anywhere': item.anywhere,
        'date': item.date,
        'return_date': item.return_date,
        'price_from': item.price_from,
        'price_to': item.price_to,
        'airline_code': item.airline_code,
        'source': item.source,
        'kupibilet_hot_offer': kupibilet_hot_offer,
        'result_count': item.result_count,
        'saved_to': item.saved_to,
        'server_time': item.server_time,
        'created_at': item.created_at.isoformat(),
    }


@csrf_exempt
@require_POST
def live_prices(request):
    payload = parse_json_body(request)
    if payload is None:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    raw_tickets = payload.get('tickets')
    if not isinstance(raw_tickets, list):
        return JsonResponse({'updates': []})

    updates: list[dict] = []
    for raw_ticket in raw_tickets[:8]:
        if not isinstance(raw_ticket, dict):
            continue

        source = str(raw_ticket.get('source') or '').strip().lower()
        link = str(raw_ticket.get('link') or '').strip()
        if source != 'kupibilet' or not link:
            continue

        try:
            snapshot = kupibilet_client.get_live_ticket_snapshot(link)
        except Exception:
            continue
        if not snapshot:
            continue

        updates.append(
            {
                'ticket_key': str(raw_ticket.get('ticket_key') or ''),
                'link': snapshot['link'],
                'price': snapshot['price'],
                'updated_at': snapshot['updated_at'],
            }
        )

    return JsonResponse({'updates': updates})


def get_tickets_by_source(
    source_name: str,
    route: str,
    limit: int | None,
    departure_date: date | None,
    return_date: date | None,
    anywhere: bool = False,
    anywhere_refine_exact: bool = True,
    kupibilet_hot_offer: bool = False,
    deep_scan: bool = True,
) -> list[Ticket]:
    request_limit = 100 if limit is None else max(min(limit, 200), 100)

    if anywhere and source_name == 'kupibilet' and kupibilet_hot_offer:
        origin_value = route.strip()
        return run_parser_task(
            'kupibilet',
            lambda: kupibilet_client.get_hot_tickets_anywhere(
                origin_value=origin_value,
                limit=limit or request_limit,
                departure_date=departure_date,
                hot_offer=True,
                deep_scan=deep_scan,
            ),
        )

    if anywhere:
        origin_value = route.strip()
        return run_parser_task(
            'aviasales',
            lambda: aviasales_client.get_hot_tickets_anywhere(
                origin_value=origin_value,
                limit=limit or request_limit,
                request_limit=request_limit,
                departure_date=departure_date,
                refine_exact=anywhere_refine_exact,
            ),
        )

    if source_name == 'aviasales':
        strict_results = run_parser_task(
            'aviasales',
            lambda: aviasales_client.get_hot_tickets(
                route=route,
                limit=limit or request_limit,
                request_limit=request_limit,
                departure_date=departure_date,
            ),
        )
        if strict_results:
            return strict_results
        return run_parser_task(
            'aviasales',
            lambda: aviasales_client.get_hot_tickets(
                route=route,
                limit=limit or request_limit,
                request_limit=request_limit,
                departure_date=departure_date,
                strict_exact_price=False,
            ),
        )

    if source_name == 'tutu':
        return run_parser_task(
            'tutu',
            lambda: tutu_client.get_hot_tickets(
                route=route,
                limit=limit or request_limit,
                request_limit=request_limit,
                departure_date=departure_date,
                return_date=return_date,
            ),
        )

    if source_name == 'kupibilet':
        return run_parser_task(
            'kupibilet',
            lambda: kupibilet_client.get_hot_tickets(
                route=route,
                limit=limit or request_limit,
                request_limit=request_limit,
                departure_date=departure_date,
                return_date=return_date,
                hot_offer=kupibilet_hot_offer,
            ),
        )

    tasks = [
        (
            'aviasales',
            lambda: aviasales_client.get_hot_tickets(
                route=route,
                limit=limit or request_limit,
                request_limit=request_limit,
                departure_date=departure_date,
                strict_exact_price=False,
            ),
        ),
        (
            'tutu',
            lambda: tutu_client.get_hot_tickets(
                route=route,
                limit=limit or request_limit,
                request_limit=request_limit,
                departure_date=departure_date,
                return_date=return_date,
            ),
        ),
        (
            'kupibilet',
            lambda: kupibilet_client.get_hot_tickets(
                route=route,
                limit=limit or request_limit,
                request_limit=request_limit,
                departure_date=departure_date,
                return_date=return_date,
                hot_offer=kupibilet_hot_offer,
            ),
        ),
    ]

    merged: list[Ticket] = []
    try:
        with ThreadPoolExecutor(max_workers=SOURCE_MAX_WORKERS) as executor:
            futures = [executor.submit(run_parser_task, parser_name, task) for parser_name, task in tasks]
            for future in as_completed(futures):
                merged.extend(future.result())
    except RuntimeError:
        for parser_name, task in tasks:
            merged.extend(run_parser_task(parser_name, task))
    merged.sort(key=lambda t: (t.price, parse_departure_for_sort(t.departure_at), t.source, t.airline))
    return merged if limit is None else merged[: limit * 3]


def get_tickets_for_period(
    source_name: str,
    route: str,
    limit: int | None,
    departure_date: date | None,
    return_date: date | None,
    anywhere: bool = False,
    kupibilet_hot_offer: bool = False,
    deep_scan: bool = True,
) -> list[Ticket]:
    if not departure_date:
        return get_tickets_by_source(
            source_name,
            route,
            limit,
            None,
            None,
            anywhere=anywhere,
            kupibilet_hot_offer=kupibilet_hot_offer,
            deep_scan=deep_scan,
        )

    if not return_date or return_date <= departure_date:
        return get_tickets_by_source(
            source_name,
            route,
            limit,
            departure_date,
            None,
            anywhere=anywhere,
            kupibilet_hot_offer=kupibilet_hot_offer,
            deep_scan=deep_scan,
        )

    days_count = (return_date - departure_date).days + 1

    def build_fast_reference_range() -> list[Ticket]:
        tickets = get_tickets_for_period(
            source_name='aviasales',
            route=route,
            limit=(limit or 30),
            departure_date=departure_date,
            return_date=return_date,
            anywhere=False,
        )
        if tickets:
            return tickets

        fallback_limit = limit or 30
        fallback_days = min(days_count, 5)
        merged: list[Ticket] = []
        seen: set[tuple] = set()
        for offset in range(fallback_days):
            current_date = departure_date + timedelta(days=offset)
            for ticket in get_tickets_by_source(
                source_name='aviasales',
                route=route,
                limit=min(fallback_limit, 12),
                departure_date=current_date,
                return_date=None,
                anywhere=False,
                kupibilet_hot_offer=kupibilet_hot_offer,
            ):
                dedupe_key = (
                    ticket.source,
                    ticket.origin,
                    ticket.destination,
                    ticket.departure_at,
                    ticket.price,
                    ticket.link,
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                merged.append(ticket)
        merged.sort(key=lambda t: (parse_departure_for_sort(t.departure_at), t.price, t.source, t.airline))
        return merged

    if source_name == 'both':
        if not anywhere:
            aviasales_range = build_fast_reference_range()
            merged: list[Ticket] = []
            for ticket in aviasales_range:
                merged.append(ticket)
                merged.append(tutu_client.build_fallback_ticket(ticket))
                merged.append(kupibilet_client.build_fallback_ticket(ticket))
            merged.sort(key=lambda t: (parse_departure_for_sort(t.departure_at), t.price, t.source, t.airline))
            if limit is None:
                return merged
            return merged[: max(limit * days_count, limit)]

    if source_name == 'aviasales' and not anywhere:
        def fetch_aviasales_range_chunk(chunk_start: date, chunk_end: date) -> list[Ticket]:
            request_limit = 120 if limit is None else max(min(limit * 6, 160), 60)
            range_limit = None if limit is None else max(limit * 2, 20)
            return aviasales_client.get_hot_tickets_in_range(
                route=route,
                start_date=chunk_start,
                end_date=chunk_end,
                limit=range_limit,
                request_limit=request_limit,
            )

        if days_count > RANGE_CHUNK_DAYS:
            chunks: list[tuple[date, date]] = []
            chunk_start = departure_date
            while chunk_start <= return_date:
                chunk_end = min(chunk_start + timedelta(days=RANGE_CHUNK_DAYS - 1), return_date)
                chunks.append((chunk_start, chunk_end))
                chunk_start = chunk_end + timedelta(days=1)

            merged: list[Ticket] = []
            seen: set[tuple] = set()

            def collect_chunk(chunk: tuple[date, date]) -> list[Ticket]:
                return fetch_aviasales_range_chunk(chunk[0], chunk[1])

            max_workers = min(RANGE_CHUNK_MAX_WORKERS, max(1, len(chunks)))
            try:
                executor = ThreadPoolExecutor(max_workers=max_workers)
                futures = [executor.submit(collect_chunk, chunk) for chunk in chunks]
                try:
                    done, not_done = wait(futures, timeout=LONG_RANGE_AVIASALES_TIMEOUT_SECONDS)
                    for future in done:
                        for ticket in future.result():
                            dedupe_key = (
                                ticket.source,
                                ticket.origin,
                                ticket.destination,
                                ticket.departure_at,
                                ticket.price,
                                ticket.link,
                            )
                            if dedupe_key in seen:
                                continue
                            seen.add(dedupe_key)
                            merged.append(ticket)
                    for future in not_done:
                        future.cancel()
                finally:
                    executor.shutdown(wait=False, cancel_futures=True)
            except RuntimeError:
                for chunk in chunks:
                    for ticket in collect_chunk(chunk):
                        dedupe_key = (
                            ticket.source,
                            ticket.origin,
                            ticket.destination,
                            ticket.departure_at,
                            ticket.price,
                            ticket.link,
                        )
                        if dedupe_key in seen:
                            continue
                        seen.add(dedupe_key)
                        merged.append(ticket)

            if not merged and chunks:
                for ticket in collect_chunk(chunks[0]):
                    dedupe_key = (
                        ticket.source,
                        ticket.origin,
                        ticket.destination,
                        ticket.departure_at,
                        ticket.price,
                        ticket.link,
                    )
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    merged.append(ticket)

            merged.sort(key=lambda t: (parse_departure_for_sort(t.departure_at), t.price, t.source, t.airline))
            if limit is None:
                return merged
            return merged[: max(limit * days_count, limit)]

        return run_with_timeout(
            lambda: fetch_aviasales_range_chunk(departure_date, return_date),
            SHORT_RANGE_AVIASALES_TIMEOUT_SECONDS,
            [],
        )

    if source_name == 'tutu' and not anywhere:
        aviasales_range = build_fast_reference_range()
        tickets = [tutu_client.build_fallback_ticket(ticket) for ticket in aviasales_range]
        if limit is None:
            return tickets
        return tickets[: max(limit * days_count, limit)]

    if source_name == 'kupibilet' and not anywhere and not kupibilet_hot_offer:
        aviasales_range = build_fast_reference_range()
        tickets = [kupibilet_client.build_fallback_ticket(ticket) for ticket in aviasales_range]
        if limit is None:
            return tickets
        return tickets[: max(limit * days_count, limit)]

    all_dates = list(date_range(departure_date, return_date))
    merged: list[Ticket] = []
    seen: set[tuple] = set()
    daily_results: dict[date, list[Ticket]] = {}

    def fetch_daily(current_date: date) -> tuple[date, list[Ticket]]:
        daily_limit = limit
        anywhere_refine_exact = True
        if kupibilet_hot_offer and source_name == 'kupibilet':
            daily_limit = min(limit or 30, 30)
        elif anywhere:
            daily_limit = min(limit or 12, 12)
        elif source_name in {'tutu', 'kupibilet', 'both'}:
            daily_limit = min(limit or 3, 3)
        return (
            current_date,
            get_tickets_by_source(
                source_name=source_name,
                route=route,
                limit=daily_limit,
                departure_date=current_date,
                return_date=None,
                anywhere=anywhere,
                anywhere_refine_exact=anywhere_refine_exact,
                kupibilet_hot_offer=kupibilet_hot_offer,
                deep_scan=deep_scan,
            ),
        )

    max_workers = min(PERIOD_MAX_WORKERS, max(1, len(all_dates)))
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(fetch_daily, current_date) for current_date in all_dates]
            for future in as_completed(futures):
                current_date, daily_tickets = future.result()
                daily_results[current_date] = daily_tickets
    except RuntimeError:
        for current_date in all_dates:
            day, daily_tickets = fetch_daily(current_date)
            daily_results[day] = daily_tickets

    for current_date in all_dates:
        for ticket in daily_results.get(current_date, []):
            dedupe_key = (
                ticket.source,
                ticket.origin,
                ticket.destination,
                ticket.departure_at,
                ticket.price,
                ticket.link,
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            merged.append(ticket)

    merged.sort(key=lambda t: (parse_departure_for_sort(t.departure_at), t.price, t.source, t.airline))
    if limit is None:
        return merged
    return merged[: max(limit * days_count, limit)]


def get_tickets_with_nearest_fallback(
    source_name: str,
    route: str,
    limit: int | None,
    departure_date: date | None,
    return_date: date | None,
    anywhere: bool = False,
    kupibilet_hot_offer: bool = False,
    deep_scan: bool = True,
) -> list[Ticket]:
    cache_key = build_search_cache_key(
        source_name=source_name,
        route=route,
        limit=limit,
        departure_date=departure_date,
        return_date=return_date,
        anywhere=anywhere,
        kupibilet_hot_offer=kupibilet_hot_offer,
        deep_scan=deep_scan,
    )
    cached_tickets = get_cached_search_result(cache_key)
    if cached_tickets is not None:
        return cached_tickets

    tickets = get_tickets_for_period(
        source_name=source_name,
        route=route,
        limit=limit,
        departure_date=departure_date,
        return_date=return_date,
        anywhere=anywhere,
        kupibilet_hot_offer=kupibilet_hot_offer,
        deep_scan=deep_scan,
    )
    if tickets or anywhere or not departure_date or return_date or kupibilet_hot_offer:
        set_cached_search_result(cache_key, tickets)
        return tickets

    today_utc = datetime.now(timezone.utc).date()
    if departure_date > today_utc:
        set_cached_search_result(cache_key, tickets)
        return tickets

    for offset in range(1, 4):
        fallback_date = departure_date + timedelta(days=offset)
        fallback_tickets = get_tickets_by_source(
            source_name=source_name,
            route=route,
            limit=limit,
            departure_date=fallback_date,
            return_date=None,
            anywhere=False,
            kupibilet_hot_offer=kupibilet_hot_offer,
            deep_scan=deep_scan,
        )
        if fallback_tickets:
            set_cached_search_result(cache_key, fallback_tickets)
            return fallback_tickets

    set_cached_search_result(cache_key, tickets)
    return tickets


def save_search_results(*, user_id: int, search_payload: dict, tickets_payload: list[dict], server_time: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    filename = f'search_{user_id}_{timestamp}.json'
    file_path = RESULTS_DIR / filename
    file_path.write_text(
        json.dumps(
            {
                'server_time': server_time,
                'user_id': user_id,
                'search': search_payload,
                'tickets': tickets_payload,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    return str(file_path)


def filter_tickets_by_price(tickets: list[Ticket], price_from: int | None, price_to: int | None) -> list[Ticket]:
    if price_from is None and price_to is None:
        return tickets

    filtered: list[Ticket] = []
    for ticket in tickets:
        if price_from is not None and ticket.price < price_from:
            continue
        if price_to is not None and ticket.price > price_to:
            continue
        filtered.append(ticket)
    return filtered


def filter_tickets_by_airline(tickets: list[Ticket], airline_code: str | None) -> list[Ticket]:
    if not airline_code:
        return tickets

    upper_code = airline_code.upper()
    filtered: list[Ticket] = []
    for ticket in tickets:
        if str(ticket.airline or '').upper() == upper_code:
            filtered.append(ticket)
    return filtered


def tickets_to_dicts(tickets: list[Ticket], favorite_keys: set[str] | None = None) -> list[dict]:
    favorite_keys = favorite_keys or set()
    result = []
    for ticket in tickets:
        normalized_link = normalize_ticket_link(ticket.link)
        origin_code = ticket.origin
        destination_code = ticket.destination
        origin_label = aviasales_client.resolve_location_name(origin_code)
        destination_label = aviasales_client.resolve_location_name(destination_code)
        origin_airport = aviasales_client.resolve_airport_name(origin_code)
        destination_airport = aviasales_client.resolve_airport_name(destination_code)
        ticket_key = build_ticket_key(
            source=ticket.source,
            origin=origin_code,
            destination=destination_code,
            departure_at=ticket.departure_at,
            price=ticket.price,
            link=normalized_link,
        )
        result.append(
            {
                'ticket_key': ticket_key,
                'origin': origin_label,
                'destination': destination_label,
                'origin_airport': origin_airport,
                'destination_airport': destination_airport,
                'origin_code': origin_code,
                'destination_code': destination_code,
                'price': ticket.price,
                'airline': ticket.airline,
                'departure_at': ticket.departure_at,
                'transfers': ticket.transfers,
                'link': normalized_link,
                'source': ticket.source,
                'updated_at': ticket.updated_at,
                'is_favorite': ticket_key in favorite_keys,
                'estimated_price': bool(getattr(ticket, 'estimated_price', False)),
                'baggage_info': str(getattr(ticket, 'baggage_info', '') or ''),
                'original_price': getattr(ticket, 'original_price', None),
                'hot_discount_percent': getattr(ticket, 'hot_discount_percent', None),
                'hot_expires_at': str(getattr(ticket, 'hot_expires_at', '') or ''),
                'special_offer_label': str(getattr(ticket, 'special_offer_label', '') or ''),
            }
        )
    return result


@require_GET
def health(request):
    return JsonResponse({'ok': True, 'time': datetime.now(timezone.utc).isoformat()})


@require_GET
def auth_me(request):
    if not request.user.is_authenticated:
        return JsonResponse({'authenticated': False, 'user': None})
    return JsonResponse({'authenticated': True, 'user': user_payload(request.user)})


@csrf_exempt
@require_POST
def auth_register(request):
    payload = parse_json_body(request)
    if payload is None:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    username = str(payload.get('username', '')).strip()
    password = str(payload.get('password', '')).strip()

    if len(username) < 3:
        return JsonResponse({'error': 'Логин должен быть не короче 3 символов'}, status=400)
    if len(password) < 6:
        return JsonResponse({'error': 'Пароль должен быть не короче 6 символов'}, status=400)
    if User.objects.filter(username=username).exists():
        return JsonResponse({'error': 'Такой логин уже существует'}, status=400)

    user = User.objects.create_user(username=username, password=password, last_login=datetime.now(timezone.utc))
    login(request, user)
    return JsonResponse({'authenticated': True, 'user': user_payload(user)})


@csrf_exempt
@require_POST
def auth_login(request):
    payload = parse_json_body(request)
    if payload is None:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    username = str(payload.get('username', '')).strip()
    password = str(payload.get('password', '')).strip()
    user = authenticate(request, username=username, password=password)

    if user is None:
        return JsonResponse({'error': 'Неверный логин или пароль'}, status=400)

    login(request, user)
    return JsonResponse({'authenticated': True, 'user': user_payload(user)})


@csrf_exempt
@require_POST
def auth_logout(request):
    logout(request)
    return JsonResponse({'authenticated': False, 'user': None})


@require_GET
def favorites_list(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Нужна авторизация'}, status=401)

    favorites = FavoriteTicket.objects.filter(user=request.user)
    return JsonResponse({'favorites': [serialize_favorite(item) for item in favorites]})


@require_GET
def history_list(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Нужна авторизация'}, status=401)

    items = SearchHistory.objects.filter(user=request.user)[:30]
    return JsonResponse({'history': [serialize_search_history(item) for item in items]})


@csrf_exempt
@require_POST
def history_tickets(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Нужна авторизация'}, status=401)

    payload = parse_json_body(request)
    if payload is None:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    history_id = payload.get('id')
    try:
        history_id = int(history_id)
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Не указан id записи'}, status=400)

    item = SearchHistory.objects.filter(user=request.user, id=history_id).first()
    if item is None:
        return JsonResponse({'error': 'Запись истории не найдена'}, status=404)
    if not item.saved_to:
        return JsonResponse({'tickets': [], 'server_time': item.server_time})

    file_path = Path(item.saved_to)
    if not file_path.exists():
        return JsonResponse({'tickets': [], 'server_time': item.server_time})

    try:
        raw_payload = json.loads(file_path.read_text(encoding='utf-8'))
    except Exception:
        return JsonResponse({'error': 'Не удалось прочитать сохраненную выдачу'}, status=400)

    favorite_keys = set(FavoriteTicket.objects.filter(user=request.user).values_list('ticket_key', flat=True))
    tickets = raw_payload.get('tickets', [])
    if isinstance(tickets, list):
        for ticket in tickets:
            if isinstance(ticket, dict):
                ticket['is_favorite'] = str(ticket.get('ticket_key', '')) in favorite_keys

    return JsonResponse({'tickets': tickets if isinstance(tickets, list) else [], 'server_time': raw_payload.get('server_time') or item.server_time})


@csrf_exempt
@require_POST
def history_remove(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Нужна авторизация'}, status=401)

    payload = parse_json_body(request)
    if payload is None:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    history_id = payload.get('id')
    try:
        history_id = int(history_id)
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Не указан id записи'}, status=400)

    SearchHistory.objects.filter(user=request.user, id=history_id).delete()
    return JsonResponse({'removed': True, 'id': history_id})


@csrf_exempt
@require_POST
def favorites_add(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Нужна авторизация'}, status=401)

    payload = parse_json_body(request)
    if payload is None:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    source = str(payload.get('source', '')).strip()
    origin = str(payload.get('origin_code') or payload.get('origin', '')).strip()
    destination = str(payload.get('destination_code') or payload.get('destination', '')).strip()
    departure_at = str(payload.get('departure_at', '')).strip()
    link = normalize_ticket_link(str(payload.get('link', '')).strip())

    try:
        price = int(payload.get('price', 0))
        transfers = int(payload.get('transfers', 0))
        original_price = parse_optional_int(payload.get('original_price'))
        hot_discount_percent = parse_optional_int(payload.get('hot_discount_percent'))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Некорректные данные билета'}, status=400)

    if not source or not origin or not destination or price <= 0:
        return JsonResponse({'error': 'Не хватает данных билета'}, status=400)

    ticket_key = str(payload.get('ticket_key', '')).strip() or build_ticket_key(
        source=source,
        origin=origin,
        destination=destination,
        departure_at=departure_at,
        price=price,
        link=link,
    )

    favorite, _ = FavoriteTicket.objects.update_or_create(
        user=request.user,
        ticket_key=ticket_key,
        defaults={
            'source': source,
            'origin': origin,
            'destination': destination,
            'price': price,
            'airline': str(payload.get('airline', '')).strip(),
            'departure_at': departure_at,
            'transfers': transfers,
            'link': link,
            'updated_at': str(payload.get('updated_at', '')).strip(),
            'original_price': original_price,
            'hot_discount_percent': hot_discount_percent,
            'hot_expires_at': str(payload.get('hot_expires_at', '') or '').strip(),
            'special_offer_label': str(payload.get('special_offer_label', '') or '').strip(),
            'estimated_price': bool(payload.get('estimated_price', False)),
            'baggage_info': str(payload.get('baggage_info', '') or '').strip(),
        },
    )

    return JsonResponse({'favorite': serialize_favorite(favorite)})


@csrf_exempt
@require_POST
def favorites_remove(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Нужна авторизация'}, status=401)

    payload = parse_json_body(request)
    if payload is None:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    ticket_key = str(payload.get('ticket_key', '')).strip()
    if not ticket_key:
        return JsonResponse({'error': 'Не указан ticket_key'}, status=400)

    FavoriteTicket.objects.filter(user=request.user, ticket_key=ticket_key).delete()
    return JsonResponse({'removed': True, 'ticket_key': ticket_key})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def search(request):
    payload = parse_search_payload(request)
    if payload is None:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    route = str(payload.get('route', '')).strip()
    if not route:
        return JsonResponse({'error': 'Маршрут обязателен'}, status=400)

    anywhere = parse_boolish(payload.get('anywhere'))
    kupibilet_hot_offer = parse_boolish(payload.get('kupibilet_hot_offer'))
    deep_scan = parse_boolish(payload.get('deep_scan', True))

    source = str(payload.get('source', 'both')).strip().lower() or 'both'
    if source not in {'aviasales', 'tutu', 'kupibilet', 'both'}:
        return JsonResponse({'error': 'Неверный источник'}, status=400)
    if anywhere and not kupibilet_hot_offer:
        source = 'aviasales'

    raw_limit = payload.get('limit')
    if raw_limit in (None, ''):
        limit = None
    else:
        try:
            limit = max(1, int(raw_limit))
        except (TypeError, ValueError):
            return JsonResponse({'error': 'Некорректный limit'}, status=400)

    try:
        departure_date = parse_date(payload.get('date'))
        return_date = parse_date(payload.get('return_date'))
        price_from = parse_optional_int(payload.get('price_from'))
        price_to = parse_optional_int(payload.get('price_to'))
        airline_code = parse_optional_str(payload.get('airline_code'))
    except ValueError:
        return JsonResponse({'error': 'Некорректные дата или цена. Используйте YYYY-MM-DD и целые числа.'}, status=400)

    if price_from is None and price_to is not None:
        price_from = 0

    if departure_date and return_date and return_date < departure_date:
        return JsonResponse({'error': 'Дата по не может быть раньше даты с'}, status=400)
    if price_from is not None and price_to is not None and price_to < price_from:
        return JsonResponse({'error': 'Цена до не может быть меньше цены от'}, status=400)
    if kupibilet_hot_offer:
        if source != 'kupibilet':
            return JsonResponse({'error': 'Горячая временная цена доступна только для Kupibilet'}, status=400)
        if not departure_date and not anywhere:
            return JsonResponse({'error': 'Для горячей временной цены нужна дата вылета'}, status=400)

    fetch_limit = limit
    if limit is not None and (price_from is not None or price_to is not None):
        fetch_limit = min(max(limit * 5, 60), 200)

    try:
        tickets = get_tickets_with_nearest_fallback(
            source_name=source,
            route=route,
            limit=fetch_limit,
            departure_date=departure_date,
            return_date=return_date,
            anywhere=anywhere,
            kupibilet_hot_offer=kupibilet_hot_offer,
            deep_scan=deep_scan,
        )
        tickets = filter_tickets_by_price(tickets, price_from, price_to)
        tickets = filter_tickets_by_airline(tickets, airline_code)
        if limit is not None:
            tickets = tickets[:limit]
    except requests.exceptions.Timeout:
        return JsonResponse({'error': 'Источник цен временно не отвечает. Попробуйте еще раз позже.'}, status=504)
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    favorite_keys = (
        set(FavoriteTicket.objects.filter(user=request.user).values_list('ticket_key', flat=True))
        if request.user.is_authenticated
        else set()
    )
    server_time = datetime.now(timezone.utc).isoformat()
    tickets_payload = tickets_to_dicts(tickets, favorite_keys=favorite_keys)

    saved_to = ''
    history_entry = None
    if tickets_payload and request.user.is_authenticated:
        saved_to = save_search_results(
            user_id=request.user.id,
            search_payload={
                'route': route,
                'anywhere': anywhere,
                'date': payload.get('date'),
                'return_date': payload.get('return_date'),
                'price_from': price_from,
                'price_to': price_to,
                'airline_code': airline_code,
                'source': source,
                'limit': limit,
                'kupibilet_hot_offer': kupibilet_hot_offer,
            },
            tickets_payload=tickets_payload,
            server_time=server_time,
        )
        history_entry = SearchHistory.objects.create(
            user=request.user,
            route=route,
            anywhere=anywhere,
            date=str(payload.get('date') or ''),
            return_date=str(payload.get('return_date') or ''),
            price_from=price_from,
            price_to=price_to,
            airline_code=airline_code or '',
            source=source,
            result_count=len(tickets_payload),
            saved_to=saved_to,
            server_time=server_time,
        )
    return JsonResponse(
        {
            'tickets': tickets_payload,
            'server_time': server_time,
            'saved_to': saved_to,
            'history_id': history_entry.id if history_entry else None,
        }
    )

