import json, re
from pathlib import Path
obj = json.loads(Path('C:/Users/kavik/Documents/GitHub/ParserAir/project/kupi_verify_mow_20260416.json').read_text(encoding='utf-8'))
unique = {}
for item in obj['target_hits']:
    text = item['text']
    normalized = re.sub(r'\d{1,2}:\d{2}:\d{2}', '<timer>', text)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    unique.setdefault(normalized, item)
print('unique_target_cards=', len(unique))
for idx, item in enumerate(list(unique.values())[:20], start=1):
    print('---', idx)
    print(item['text'])
