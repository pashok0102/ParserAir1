import { API_BASE_URL } from './config';

async function readJson(response) {
  const text = await response.text();
  if (!text) {
    return {};
  }
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

export async function apiRequest(path, options = {}) {
  const hasBody = typeof options.body !== 'undefined'
  const baseHeaders = hasBody
    ? { 'Content-Type': 'text/plain;charset=UTF-8' }
    : {}

  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      ...baseHeaders,
      ...(options.headers || {}),
    },
    credentials: 'include',
    ...options,
  });

  const payload = await readJson(response);
  if (!response.ok) {
    throw new Error(payload.error || 'Ошибка запроса');
  }
  return payload;
}

export const api = {
  health: () => apiRequest('/health', { method: 'GET' }),
  authMe: () => apiRequest('/auth/me', { method: 'GET' }),
  login: (form) => apiRequest('/auth/login', { method: 'POST', body: JSON.stringify(form) }),
  register: (form) => apiRequest('/auth/register', { method: 'POST', body: JSON.stringify(form) }),
  logout: () => apiRequest('/auth/logout', { method: 'POST' }),
  search: (payload) => {
    return apiRequest('/find-tickets', { method: 'POST', body: JSON.stringify(payload || {}) });
  },
  favorites: () => apiRequest('/favorites', { method: 'GET' }),
  addFavorite: (ticket) => apiRequest('/favorites/add', { method: 'POST', body: JSON.stringify(ticket) }),
  removeFavorite: (ticketKey) =>
    apiRequest('/favorites/remove', { method: 'POST', body: JSON.stringify({ ticket_key: ticketKey }) }),
  history: () => apiRequest('/history', { method: 'GET' }),
  historyTickets: (id) => apiRequest('/history/tickets', { method: 'POST', body: JSON.stringify({ id }) }),
  removeHistory: (id) => apiRequest('/history/remove', { method: 'POST', body: JSON.stringify({ id }) }),
};
