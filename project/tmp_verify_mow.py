from playwright.sync_api import sync_playwright
import json
from pathlib import Path
url = 'https://www.kupibilet.ru/sales?departureCity=MOW'
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page(viewport={'width': 1600, 'height': 2200}, locale='ru-RU')
    page.goto(url, wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(7000)

    seen = []
    seen_keys = set()

    def collect(label):
        cards = page.locator('.TicketCard_card__yyKN7')
        for i in range(cards.count()):
            card = cards.nth(i)
            try:
                text = card.inner_text(timeout=2000) or ''
            except Exception:
                text = ''
            if not text or text in seen_keys:
                continue
            seen_keys.add(text)
            seen.append({'phase': label, 'text': text})

    def scroll_collect(label):
        for _ in range(8):
            collect(label)
            page.mouse.wheel(0, 2600)
            page.wait_for_timeout(450)

    scroll_collect('initial')

    category_buttons = page.locator("button[class*='_tag_']")
    category_count = category_buttons.count()
    for idx in range(category_count):
        try:
            btn = category_buttons.nth(idx)
            title = (btn.inner_text(timeout=1200) or '').strip()
            btn.click(timeout=2500)
            page.wait_for_timeout(500)
            scroll_collect(f'cat:{title}')
        except Exception:
            pass

    next_buttons = page.locator("button[class*='_rightBtn_']")
    next_count = next_buttons.count()
    for idx in range(next_count):
        for step in range(5):
            try:
                btn = next_buttons.nth(idx)
                if btn.is_disabled():
                    break
                btn.click(timeout=2500)
                page.wait_for_timeout(500)
                scroll_collect(f'next:{idx}:{step}')
            except Exception:
                break

    target_hits = []
    for item in seen:
        text = item['text'].lower()
        if ('16 апр' in text) or ('16.04' in text):
            target_hits.append(item)

    Path('kupi_verify_mow_20260416.json').write_text(json.dumps({
        'total_unique_cards': len(seen),
        'target_hits_count': len(target_hits),
        'target_hits': target_hits,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    b.close()
print('ok')
