export function formatPrice(value) {
  const amount = Number(value || 0);
  if (!Number.isFinite(amount) || amount <= 0) {
    return 'Цена не указана';
  }
  return `${new Intl.NumberFormat('ru-RU').format(amount)} RUB`;
}

export function formatDateTime(value) {
  if (!value) {
    return 'Дата не указана';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat('ru-RU', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(parsed);
}

export function normalizeLocation(value) {
  return String(value || '').trim();
}

export function buildRoute({ from, to, anywhere }) {
  const safeFrom = normalizeLocation(from);
  const safeTo = normalizeLocation(to);
  return anywhere ? safeFrom : `${safeFrom} - ${safeTo}`;
}

export function sourceLabel(value) {
  switch (value) {
    case 'aviasales':
      return 'Aviasales';
    case 'tutu':
      return 'Tutu.ru';
    case 'kupibilet':
      return 'Kupibilet';
    default:
      return 'Все источники';
  }
}

export function transfersLabel(count) {
  if (count === 0) return 'Прямой рейс';
  if (count === 1) return '1 пересадка';
  return `${count} пересадки`;
}
