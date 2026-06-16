import { StatusBar } from 'expo-status-bar';
import React, { Component, createElement, useEffect, useMemo, useState } from 'react';
import {
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from 'react-native';

import { api } from './src/api';
import { APP_TITLE, themes } from './src/config';

const fallbackTheme = themes.light;

const TEXT = {
  title: APP_TITLE,
  subtitle: 'Быстрый старт, результаты, избранное и история в одном экране.',
  tabs: {
    search: 'Поиск',
    results: 'Результаты',
    favorites: 'Избранное',
    history: 'История',
    account: 'Аккаунт',
  },
  popup: {
    badge: 'Быстрый старт',
    title: 'Горячая временная цена Kupibilet',
    body:
      'Это отдельный сценарий поиска, как на веб-сайте: можно ввести город и сразу получить горячие билеты Kupibilet. Без аккаунта работает только это окно.',
    city: 'Город вылета',
    cityPlaceholder: 'Например, Москва',
    skip: 'Позже',
    submit: 'Показать горячие билеты',
  },
  search: {
    guestNote: 'Без аккаунта основной парсер заблокирован. Доступен только быстрый старт через всплывающее окно.',
    from: 'Откуда',
    fromPlaceholder: 'Например, Санкт-Петербург',
    to: 'Куда',
    toPlaceholder: 'Например, Сочи',
    routeTitle: 'Логика направления',
    exactRoute: 'Точный маршрут',
    anywhere: 'Хоть куда',
    dateTitle: 'Дата вылета',
    singleDay: 'Один день',
    range: 'Диапазон дат',
    date: 'Дата',
    dateFrom: 'Дата с',
    dateTo: 'Дата по',
    sourceTitle: 'Источник',
    sourceBoth: 'Все источники',
    sourceAviasales: 'Aviasales',
    sourceTutu: 'Tutu',
    sourceKupibilet: 'Kupibilet',
    hotTitle: 'Горячая временная цена Kupibilet',
    hotDescription:
      'Отдельный hot-сценарий Kupibilet. Работает как на веб-сайте и использует тот же backend-скрипт горячих билетов.',
    submit: 'Найти билеты',
    blocked: 'Войдите в аккаунт, чтобы использовать основной парсер.',
  },
  auth: {
    loginTitle: 'Вход',
    registerTitle: 'Регистрация',
    username: 'Имя пользователя',
    password: 'Пароль',
    submitLogin: 'Войти',
    submitRegister: 'Создать аккаунт',
    switchLogin: 'Уже есть аккаунт? Войти',
    switchRegister: 'Нет аккаунта? Зарегистрироваться',
    logout: 'Выйти',
    current: 'Вы вошли как',
  },
  resultsEmpty: 'Пока нет результатов. Запусти поиск через окно выше.',
  favoritesEmpty: 'Пока нет сохранённых билетов.',
  historyEmpty: 'История пока пустая.',
  favoriteAdd: 'В избранное',
  favoriteRemove: 'Убрать из избранного',
  favoriteLogin: 'Войдите для избранного',
  openTicket: 'Открыть билет',
  repeatSearch: 'Повторить поиск',
  transfers: {
    zero: 'Прямой рейс',
    one: '1 пересадка',
    many: (count) => `${count} пересадки`,
  },
  hotFallback: 'Kupibilet не передал таймер для этой карточки.',
  hotExpired: 'Время истекло. Показываем обычную цену.',
};

const defaultForm = {
  from: 'Москва',
  to: 'Сочи',
  routeMode: 'anywhere',
  searchMode: 'single',
  date: '',
  rangeStart: '',
  rangeEnd: '',
  source: 'aviasales',
  kupibiletHotOffer: false,
};

const CITY_TO_IATA = {
  москва: 'MOW',
  moscow: 'MOW',
  мск: 'MOW',
  'санкт петербург': 'LED',
  'saint petersburg': 'LED',
  petersburg: 'LED',
  спб: 'LED',
  сочи: 'AER',
  sochi: 'AER',
  оренбург: 'REN',
  orenburg: 'REN',
  уфа: 'UFA',
  ufa: 'UFA',
  казань: 'KZN',
  kazan: 'KZN',
  самара: 'KUF',
  samara: 'KUF',
  екатеринбург: 'SVX',
  yekaterinburg: 'SVX',
  новосибирск: 'OVB',
  novosibirsk: 'OVB',
  краснодар: 'KRR',
  krasnodar: 'KRR',
  минск: 'MSQ',
  minsk: 'MSQ',
  гомель: 'GME',
  gomel: 'GME',
  брест: 'BQT',
  brest: 'BQT',
  гродно: 'GNA',
  grodno: 'GNA',
  витебск: 'VTB',
  vitebsk: 'VTB',
  стамбул: 'IST',
  istanbul: 'IST',
  анталья: 'AYT',
  antalya: 'AYT',
  дубай: 'DXB',
  dubai: 'DXB',
  тбилиси: 'TBS',
  tbilisi: 'TBS',
  ереван: 'EVN',
  yerevan: 'EVN',
  баку: 'GYD',
  baku: 'GYD',
  алматы: 'ALA',
  almaty: 'ALA',
  астана: 'NQZ',
  astana: 'NQZ',
  ташкент: 'TAS',
  tashkent: 'TAS',
  бишкек: 'FRU',
  bishkek: 'FRU',
};

const CITY_OPTIONS = [
  { name: 'Москва', iata: 'MOW', aliases: ['москва', 'moscow', 'мск', 'mow'] },
  { name: 'Санкт-Петербург', iata: 'LED', aliases: ['санкт петербург', 'санкт-петербург', 'saint petersburg', 'st petersburg', 'petersburg', 'спб', 'led'] },
  { name: 'Сочи', iata: 'AER', aliases: ['сочи', 'sochi', 'aer'] },
  { name: 'Оренбург', iata: 'REN', aliases: ['оренбург', 'orenburg', 'ren'] },
  { name: 'Орел', iata: 'OEL', aliases: ['орел', 'орёл', 'orel', 'oryol', 'oel'] },
  { name: 'Уфа', iata: 'UFA', aliases: ['уфа', 'ufa'] },
  { name: 'Казань', iata: 'KZN', aliases: ['казань', 'kazan', 'kzn'] },
  { name: 'Самара', iata: 'KUF', aliases: ['самара', 'samara', 'kuf'] },
  { name: 'Екатеринбург', iata: 'SVX', aliases: ['екатеринбург', 'yekaterinburg', 'ekaterinburg', 'svx'] },
  { name: 'Новосибирск', iata: 'OVB', aliases: ['новосибирск', 'novosibirsk', 'ovb'] },
  { name: 'Краснодар', iata: 'KRR', aliases: ['краснодар', 'krasnodar', 'krr'] },
  { name: 'Минск', iata: 'MSQ', aliases: ['минск', 'minsk', 'msq'] },
  { name: 'Гомель', iata: 'GME', aliases: ['гомель', 'gomel', 'gme'] },
  { name: 'Брест', iata: 'BQT', aliases: ['брест', 'brest', 'bqt'] },
  { name: 'Гродно', iata: 'GNA', aliases: ['гродно', 'grodno', 'gna'] },
  { name: 'Витебск', iata: 'VTB', aliases: ['витебск', 'vitebsk', 'vtb'] },
  { name: 'Стамбул', iata: 'IST', aliases: ['стамбул', 'istanbul', 'ist'] },
  { name: 'Анталья', iata: 'AYT', aliases: ['анталья', 'antalya', 'ayt'] },
  { name: 'Дубай', iata: 'DXB', aliases: ['дубай', 'dubai', 'dxb'] },
  { name: 'Тбилиси', iata: 'TBS', aliases: ['тбилиси', 'tbilisi', 'tbs'] },
  { name: 'Ереван', iata: 'EVN', aliases: ['ереван', 'yerevan', 'evn'] },
  { name: 'Баку', iata: 'GYD', aliases: ['баку', 'baku', 'gyd'] },
  { name: 'Алматы', iata: 'ALA', aliases: ['алматы', 'almaty', 'alma ata', 'ala'] },
  { name: 'Астана', iata: 'NQZ', aliases: ['астана', 'astana', 'nur sultan', 'nqz'] },
  { name: 'Ташкент', iata: 'TAS', aliases: ['ташкент', 'tashkent', 'tas'] },
  { name: 'Бишкек', iata: 'FRU', aliases: ['бишкек', 'bishkek', 'fru'] },
  { name: 'Душанбе', iata: 'DYU', aliases: ['душанбе', 'dushanbe', 'dyu'] },
  { name: 'Тель-Авив', iata: 'TLV', aliases: ['тель авив', 'тель-авив', 'tel aviv', 'tlv'] },
  { name: 'Каир', iata: 'CAI', aliases: ['каир', 'cairo', 'cai'] },
  { name: 'Белград', iata: 'BEG', aliases: ['белград', 'belgrade', 'beg'] },
  { name: 'Будапешт', iata: 'BUD', aliases: ['будапешт', 'budapest', 'bud'] },
  { name: 'Нижневартовск', iata: 'NJC', aliases: ['нижневартовск', 'nizhnevartovsk', 'njc'] },
  { name: 'Мурманск', iata: 'MMK', aliases: ['мурманск', 'murmansk', 'mmk'] },
  { name: 'Магадан', iata: 'GDX', aliases: ['магадан', 'magadan', 'gdx'] },
  { name: 'Хабаровск', iata: 'KHV', aliases: ['хабаровск', 'khabarovsk', 'khv'] },
  { name: 'Владивосток', iata: 'VVO', aliases: ['владивосток', 'vladivostok', 'vvo'] },
  { name: 'Новокузнецк', iata: 'NOZ', aliases: ['новокузнецк', 'novokuznetsk', 'noz'] },
  { name: 'Красноярск', iata: 'KJA', aliases: ['красноярск', 'krasnoyarsk', 'kja'] },
  { name: 'Иркутск', iata: 'IKT', aliases: ['иркутск', 'irkutsk', 'ikt'] },
  { name: 'Пермь', iata: 'PEE', aliases: ['пермь', 'perm', 'pee'] },
  { name: 'Калининград', iata: 'KGD', aliases: ['калининград', 'kaliningrad', 'kgd'] },
];

function normalizeLocationKey(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/ё/g, 'е')
    .replace(/[.,]/g, ' ')
    .replace(/[-–—]/g, ' ')
    .replace(/\s+/g, ' ');
}

function normalizeCitySearchKey(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/ё/g, 'е')
    .replace(/[.,]/g, ' ')
    .replace(/[-–—]/g, ' ')
    .replace(/\s+/g, ' ');
}

function getCitySuggestions(value, limit = 6) {
  const query = normalizeCitySearchKey(value);
  if (query.length < 2) {
    return [];
  }
  return CITY_OPTIONS
    .filter((city) => {
      const nameKey = normalizeCitySearchKey(city.name);
      return (
        nameKey.startsWith(query) ||
        city.iata.toLowerCase().startsWith(query) ||
        city.aliases.some((alias) => normalizeCitySearchKey(alias).startsWith(query))
      );
    })
    .slice(0, limit);
}

function normalizeLocation(value) {
  const cleaned = String(value || '').trim();
  const upper = cleaned.toUpperCase();
  if (/^[A-Z]{3}$/.test(upper)) {
    return upper;
  }
  const city = CITY_OPTIONS.find((option) => {
    const key = normalizeCitySearchKey(cleaned);
    return normalizeCitySearchKey(option.name) === key || option.aliases.some((alias) => normalizeCitySearchKey(alias) === key);
  });
  if (city) {
    return city.iata;
  }
  return CITY_TO_IATA[normalizeLocationKey(cleaned)] || cleaned;
}

function formatPrice(value) {
  const numeric = Number(value || 0);
  if (!numeric) {
    return '0 RUB';
  }
  return `${new Intl.NumberFormat('ru-RU').format(numeric)} RUB`;
}

function formatDateTime(value) {
  if (!value) {
    return 'Дата не указана';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function parseHotTimestamp(value) {
  if (!value) {
    return null;
  }
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? null : parsed;
}

function formatCountdown(expiresAt, nowMs) {
  if (!expiresAt) {
    return null;
  }
  const diff = expiresAt - nowMs;
  if (diff <= 0) {
    return null;
  }
  const hours = Math.floor(diff / 3600000);
  const minutes = Math.floor((diff % 3600000) / 60000);
  const seconds = Math.floor((diff % 60000) / 1000);
  return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function transfersLabel(count) {
  const numeric = Number(count || 0);
  if (numeric <= 0) {
    return TEXT.transfers.zero;
  }
  if (numeric === 1) {
    return TEXT.transfers.one;
  }
  return TEXT.transfers.many(numeric);
}

function getTicketKey(ticket) {
  return (
    ticket.ticket_key ||
    ticket.ticketKey ||
    ticket.link ||
    `${ticket.source || 'ticket'}:${ticket.route || ''}:${ticket.departure_at || ''}:${ticket.price || ''}`
  );
}

function normalizeTicket(ticket) {
  const price = Number(ticket.price || 0);
  const originalPrice = Number(ticket.original_price || 0) || null;
  return {
    ...ticket,
    price,
    original_price: originalPrice,
    hot_discount_percent: ticket.hot_discount_percent ? Number(ticket.hot_discount_percent) : null,
    hot_expires_at: ticket.hot_expires_at || null,
    special_offer_label: String(ticket.special_offer_label || '').trim(),
    ticket_key: getTicketKey(ticket),
  };
}

function sortTicketItems(items, nowMs = Date.now()) {
  return [...(items || [])].sort((left, right) => {
    const leftExpires = parseHotTimestamp(left?.hot_expires_at);
    const rightExpires = parseHotTimestamp(right?.hot_expires_at);
    const leftHot = leftExpires && leftExpires > nowMs && left?.price ? Number(left.price) : Number(left?.price || 0);
    const rightHot = rightExpires && rightExpires > nowMs && right?.price ? Number(right.price) : Number(right?.price || 0);
    if (leftHot !== rightHot) {
      return leftHot - rightHot;
    }
    return String(left?.departure_at || '').localeCompare(String(right?.departure_at || ''));
  });
}

function mergeUniqueTickets(currentItems, incomingItems) {
  const byKey = new Map();

  for (const item of currentItems || []) {
    byKey.set(getTicketKey(item), item);
  }

  for (const item of incomingItems || []) {
    byKey.set(getTicketKey(item), normalizeTicket(item));
  }

  return Array.from(byKey.values());
}

function buildTicketRoute(ticket) {
  const route = String(ticket.route || '').trim();
  if (route) {
    return route;
  }

  const origin = String(ticket.origin || ticket.origin_airport || ticket.origin_code || '').trim();
  const destination = String(ticket.destination || ticket.destination_airport || ticket.destination_code || '').trim();

  if (origin && destination) {
    return `${origin} → ${destination}`;
  }

  return 'Маршрут не указан';
}

function DateInput({ value, onChange, disabled, theme = fallbackTheme }) {
  if (typeof document !== 'undefined') {
    return createElement('input', {
      type: 'date',
      value: value || '',
      disabled,
      onChange: (event) => onChange(event.target.value),
      style: {
        width: '100%',
        border: '1px solid #bdd3f1',
        borderRadius: '18px',
        padding: '14px 16px',
        fontSize: '16px',
        color: disabled ? '#86a0c0' : '#173057',
        backgroundColor: disabled ? '#eef4ff' : '#ffffff',
        outline: 'none',
        boxSizing: 'border-box',
        opacity: disabled ? 0.7 : 1,
        cursor: disabled ? 'not-allowed' : 'pointer',
      },
    });
  }

  return (
    <TextInput
      value={value}
      onChangeText={onChange}
      editable={!disabled}
      placeholder="YYYY-MM-DD"
      placeholderTextColor={theme.muted}
      style={[
        styles.input,
        {
          backgroundColor: disabled ? theme.inputDisabled : theme.input,
          borderColor: theme.border,
          color: disabled ? theme.muted : theme.text,
        },
        disabled && styles.inputDisabled,
      ]}
    />
  );
}

class AppErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <SafeAreaView style={styles.errorBoundary}>
          <Text style={styles.errorBoundaryTitle}>Mobile client упал в рантайме</Text>
          <Text style={styles.errorBoundaryText}>{String(this.state.error?.message || this.state.error)}</Text>
        </SafeAreaView>
      );
    }
    return this.props.children;
  }
}

function SectionLabel({ children, theme = fallbackTheme }) {
  return <Text style={[styles.sectionLabel, { color: theme.text }]}>{children}</Text>;
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
  disabled,
  dimmed = false,
  theme = fallbackTheme,
  suggestions = false,
}) {
  const citySuggestions = suggestions && !disabled ? getCitySuggestions(value) : [];

  return (
    <View style={[styles.fieldBlock, dimmed && styles.fieldBlockDimmed]}>
      <SectionLabel theme={theme}>{label}</SectionLabel>
      <TextInput
        value={value}
        onChangeText={onChange}
        editable={!disabled}
        placeholder={placeholder}
        placeholderTextColor={theme.muted}
        style={[
          styles.input,
          {
            backgroundColor: disabled ? theme.inputDisabled : theme.input,
            borderColor: theme.border,
            color: disabled ? theme.muted : theme.text,
          },
          disabled && styles.inputDisabled,
        ]}
      />
      {citySuggestions.length ? (
        <View style={[styles.citySuggestions, { backgroundColor: theme.surface, borderColor: theme.border }]}>
          {citySuggestions.map((city) => (
            <Pressable
              key={city.iata}
              onPress={() => onChange(city.name)}
              style={({ pressed }) => [
                styles.citySuggestionItem,
                pressed && styles.citySuggestionItemPressed,
              ]}
            >
              <Text style={[styles.citySuggestionName, { color: theme.text }]}>{city.name}</Text>
              <Text style={[styles.citySuggestionMeta, { color: theme.muted }]}>{city.iata}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}
    </View>
  );
}

function ActionButton({ label, onPress, variant = 'primary', disabled = false, theme = fallbackTheme }) {
  return (
    <Pressable
      onPress={disabled ? undefined : onPress}
      style={({ pressed }) => [
        styles.button,
        variant === 'secondary'
          ? [styles.buttonSecondary, { backgroundColor: theme.surface, borderColor: theme.border }]
          : [styles.buttonPrimary, { backgroundColor: theme.primary }],
        disabled && styles.buttonDisabled,
        pressed && !disabled && styles.buttonPressed,
      ]}
    >
      <Text
        style={[
          styles.buttonText,
          variant === 'secondary'
            ? [styles.buttonSecondaryText, { color: theme.secondaryText }]
            : { color: theme.primaryText },
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

function ToggleChip({ label, active, onPress, disabled = false, theme = fallbackTheme }) {
  return (
    <Pressable
      onPress={disabled ? undefined : onPress}
      style={[
        styles.toggleChip,
        {
          backgroundColor: active ? theme.chipActive : theme.chip,
          borderColor: active ? theme.primary : theme.border,
        },
        active && styles.toggleChipActive,
        disabled && styles.toggleChipDisabled,
      ]}
    >
      <Text
        style={[
          styles.toggleChipText,
          { color: active ? theme.chipTextActive : theme.chipText },
          active && styles.toggleChipTextActive,
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

function AccountStatusBadge({ authenticated }) {
  return (
    <View style={[styles.accountStatusBadge, authenticated ? styles.accountStatusBadgeOn : styles.accountStatusBadgeOff]}>
      <View style={[styles.accountStatusDot, authenticated ? styles.accountStatusDotOn : styles.accountStatusDotOff]} />
      <Text style={[styles.accountStatusText, authenticated ? styles.accountStatusTextOn : styles.accountStatusTextOff]}>
        {authenticated ? 'Аккаунт подключён' : 'Гость'}
      </Text>
    </View>
  );
}

function AccountStatusBadgeThemed({ authenticated, theme = fallbackTheme }) {
  return (
    <View
      style={[
        styles.accountStatusBadge,
        {
          backgroundColor: authenticated ? 'rgba(34, 115, 71, 0.18)' : 'rgba(181, 60, 60, 0.16)',
          borderColor: authenticated ? 'rgba(78, 194, 124, 0.28)' : 'rgba(215, 97, 97, 0.24)',
        },
      ]}
    >
      <View style={[styles.accountStatusDot, authenticated ? styles.accountStatusDotOn : styles.accountStatusDotOff]} />
      <Text
        style={[
          styles.accountStatusText,
          { color: authenticated ? '#bff3cf' : '#ffd1d1' },
        ]}
      >
        {authenticated ? 'Аккаунт подключён' : 'Гость'}
      </Text>
    </View>
  );
}

function StartupModal({ visible, city, onCityChange, onSkip, onSubmit, loading, theme = fallbackTheme }) {
  if (!visible) {
    return null;
  }

  return (
    <View style={[styles.modalOverlay, { backgroundColor: theme.overlay }]}>
      <View style={[styles.modalCard, { backgroundColor: theme.surfaceMuted, borderColor: theme.border }]}>
        <Text style={styles.modalBadge}>{TEXT.popup.badge}</Text>
        <Text style={[styles.modalTitle, { color: theme.text }]}>{TEXT.popup.title}</Text>
        <Text style={[styles.modalBody, { color: theme.muted }]}>{TEXT.popup.body}</Text>
        <TextField
          label={TEXT.popup.city}
          value={city}
          onChange={onCityChange}
          placeholder={TEXT.popup.cityPlaceholder}
          disabled={loading}
          theme={theme}
          suggestions
        />
        <View style={styles.modalActions}>
          <ActionButton label={TEXT.popup.skip} onPress={onSkip} variant="secondary" disabled={loading} theme={theme} />
          <ActionButton
            label={loading ? 'Ищем...' : TEXT.popup.submit}
            onPress={onSubmit}
            disabled={loading || !city.trim()}
            theme={theme}
          />
        </View>
      </View>
    </View>
  );
}

function TicketCard({ ticket, isFavorite, canToggleFavorite, onToggleFavorite, loading = false, nowMs = Date.now(), theme = fallbackTheme }) {
  const expiresAt = parseHotTimestamp(ticket.hot_expires_at);
  const countdown = formatCountdown(expiresAt, nowMs);
  const hotActive = Boolean(ticket.hot_discount_percent) && Boolean(countdown);
  const hotExpired = Boolean(ticket.hot_discount_percent) && !countdown && Boolean(expiresAt);
  const displayPrice = hotExpired && ticket.original_price ? ticket.original_price : ticket.price;
  const routeLabel = buildTicketRoute(ticket);
  const specialLabel = String(ticket.special_offer_label || '').trim();
  const badgeText = hotActive
    ? `Горячая цена: -${ticket.hot_discount_percent}% · ${countdown}`
    : specialLabel
      ? specialLabel
      : ticket.hot_discount_percent
      ? `Скидка ${ticket.hot_discount_percent}%`
      : null;
  const noteText = hotActive
    ? 'Пока таймер активен, показываем временную цену из Kupibilet. После окончания вернётся обычная цена.'
    : hotExpired
      ? TEXT.hotExpired
      : badgeText
        ? `${badgeText}. ${TEXT.hotFallback}`
        : 'Цена может отличаться на 300-400 RUB из-за обновления выдачи и изменения тарифа в момент перехода.';

  return (
    <View style={[styles.ticketCard, { backgroundColor: theme.surface, borderColor: theme.border }]}>
      <View style={styles.ticketHeader}>
        <Text style={[styles.ticketSource, { backgroundColor: theme.note, color: theme.secondaryText }]}>{ticket.source || 'Kupibilet'}</Text>
        <View style={styles.ticketPriceBlock}>
          {ticket.original_price && !hotExpired ? (
            <Text style={styles.ticketOldPrice}>{formatPrice(ticket.original_price)}</Text>
          ) : null}
          <Text style={[styles.ticketPrice, { color: theme.text }]}>{formatPrice(displayPrice)}</Text>
        </View>
      </View>

      <Text style={[styles.ticketRoute, { color: theme.text }]}>{routeLabel}</Text>
      <Text style={[styles.ticketSubroute, { color: theme.secondaryText }]}>{routeLabel}</Text>
      <Text style={[styles.ticketMeta, { color: theme.secondaryText }]}>Авиакомпания: {ticket.airline || 'Не указана'}</Text>

      {badgeText ? (
        <View style={[styles.hotBadge, { backgroundColor: hotExpired ? theme.note : theme.hotBadge, borderColor: hotExpired ? theme.noteBorder : theme.hotBadgeBorder }, hotActive && styles.hotBadgeActive, hotExpired && styles.hotBadgeExpired]}>
          <Text style={[styles.hotBadgeText, { color: hotExpired ? theme.secondaryText : theme.hotBadgeText }, hotActive && styles.hotBadgeTextActive]}>{badgeText}</Text>
        </View>
      ) : null}

      <Text style={[styles.ticketInfo, { color: theme.muted }]}>{transfersLabel(ticket.transfers)}</Text>
      <Text style={[styles.ticketInfo, { color: theme.muted }]}>Вылет: {formatDateTime(ticket.departure_at)}</Text>

      <View style={[styles.ticketNote, { backgroundColor: theme.note, borderColor: theme.noteBorder }]}>
        <Text style={[styles.ticketNoteText, { color: theme.secondaryText }]}>{noteText}</Text>
      </View>

      <View style={styles.ticketActions}>
        <ActionButton
          label={
            canToggleFavorite
              ? isFavorite
                ? TEXT.favoriteRemove
                : TEXT.favoriteAdd
              : TEXT.favoriteLogin
          }
          onPress={() => onToggleFavorite(ticket)}
          variant="secondary"
          disabled={!canToggleFavorite || loading}
          theme={theme}
        />
        <ActionButton
          label={TEXT.openTicket}
          onPress={() => {
            if (typeof window !== 'undefined' && ticket.link) {
              window.open(ticket.link, '_blank', 'noopener,noreferrer');
            }
          }}
          disabled={!ticket.link || loading}
          theme={theme}
        />
      </View>
    </View>
  );
}

function AppInner() {
  const [authUser, setAuthUser] = useState(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('search');
  const [themeMode, setThemeMode] = useState(() => {
    if (typeof window === 'undefined') {
      return 'light';
    }
    return window.localStorage.getItem('airparser-mobile-theme') || 'light';
  });
  const [form, setForm] = useState(defaultForm);
  const [results, setResults] = useState([]);
  const [favorites, setFavorites] = useState([]);
  const [history, setHistory] = useState([]);
  const [historyTickets, setHistoryTickets] = useState([]);
  const [historyTicketsTitle, setHistoryTicketsTitle] = useState('');
  const [openHistoryId, setOpenHistoryId] = useState(null);
  const [startupModalOpen, setStartupModalOpen] = useState(false);
  const [startupCity, setStartupCity] = useState('');
  const [registerMode, setRegisterMode] = useState(false);
  const [authForm, setAuthForm] = useState({ username: '', password: '' });
  const [nowTick, setNowTick] = useState(() => Date.now());
  const [parserInfoOpen, setParserInfoOpen] = useState(false);
  const theme = themes[themeMode] || fallbackTheme;
  const darkTheme = themeMode === 'dark';

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('airparser-mobile-theme', themeMode);
    }
  }, [themeMode]);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        const me = await api.authMe();
        if (!cancelled) {
          setAuthUser(me.authenticated ? me.user : null);
        }
      } catch {
        if (!cancelled) {
          setAuthUser(null);
        }
      } finally {
        if (!cancelled) {
          setCheckingSession(false);
          setStartupModalOpen(true);
        }
      }
    }

    bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadPrivateData() {
      if (!authUser) {
        setFavorites([]);
        setHistory([]);
        return;
      }

      try {
        const [favoritePayload, historyPayload] = await Promise.all([api.favorites(), api.history()]);
        if (!cancelled) {
          const favoriteItems = Array.isArray(favoritePayload.favorites)
            ? favoritePayload.favorites
            : Array.isArray(favoritePayload.tickets)
              ? favoritePayload.tickets
              : [];
          const historyItems = Array.isArray(historyPayload.history)
            ? historyPayload.history
            : Array.isArray(historyPayload.items)
              ? historyPayload.items
              : [];
          setFavorites(favoriteItems.map(normalizeTicket));
          setHistory(historyItems);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError.message || 'Не удалось загрузить данные аккаунта.');
        }
      }
    }

    loadPrivateData();
    return () => {
      cancelled = true;
    };
  }, [authUser]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNowTick(Date.now());
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const favoriteKeys = useMemo(() => new Set(favorites.map(getTicketKey)), [favorites]);
  const interactionLocked = loading || startupModalOpen;
  const displayedResults = useMemo(() => sortTicketItems(results, nowTick), [results, nowTick]);
  const displayedFavorites = useMemo(() => sortTicketItems(favorites, nowTick), [favorites, nowTick]);
  const displayedHistoryTickets = useMemo(() => sortTicketItems(historyTickets, nowTick), [historyTickets, nowTick]);

  const visibleSourceOptions = useMemo(() => {
    if (form.routeMode === 'anywhere') {
      return [{ key: 'aviasales', label: TEXT.search.sourceAviasales }];
    }
    return [
      { key: 'both', label: TEXT.search.sourceBoth },
      { key: 'aviasales', label: TEXT.search.sourceAviasales },
      { key: 'tutu', label: TEXT.search.sourceTutu },
      { key: 'kupibilet', label: TEXT.search.sourceKupibilet },
    ];
  }, [form.routeMode]);

  const canUseMainParser = Boolean(authUser);
  const hasSearchResults = results.length > 0;
  const hotAnywhereDateLocked = form.routeMode === 'anywhere' && form.kupibiletHotOffer;
  const canSearch = useMemo(() => {
    if (!canUseMainParser) {
      return false;
    }
    if (!form.from.trim()) {
      return false;
    }
    if (form.routeMode === 'destination' && !form.kupibiletHotOffer && !form.to.trim()) {
      return false;
    }
    if (!hotAnywhereDateLocked && form.searchMode === 'single' && !form.date) {
      return false;
    }
    if (!hotAnywhereDateLocked && form.searchMode === 'range' && (!form.rangeStart || !form.rangeEnd)) {
      return false;
    }
    return true;
  }, [canUseMainParser, form, hotAnywhereDateLocked]);

  async function runSearch(activeForm, allowGuest = false, options = {}) {
    const { switchTab = true } = options;
    if (!allowGuest && !authUser) {
      setError(TEXT.search.blocked);
      return;
    }

    const anywhere = activeForm.routeMode === 'anywhere';
    const source = activeForm.kupibiletHotOffer
      ? 'kupibilet'
      : anywhere
        ? 'aviasales'
        : activeForm.source;

    const route = activeForm.kupibiletHotOffer
      ? normalizeLocation(activeForm.from)
      : anywhere
        ? normalizeLocation(activeForm.from)
        : `${normalizeLocation(activeForm.from)} - ${normalizeLocation(activeForm.to)}`;
    const hotAnywhereRequest = activeForm.routeMode === 'anywhere' && activeForm.kupibiletHotOffer;
    const dateValue = hotAnywhereRequest ? null : activeForm.searchMode === 'range' ? activeForm.rangeStart : activeForm.date;
    const returnDateValue = hotAnywhereRequest ? null : activeForm.searchMode === 'range' ? activeForm.rangeEnd : null;
    const useFastKupibiletPass = Boolean(activeForm.kupibiletHotOffer && (anywhere || !activeForm.to.trim()));
    const basePayload = {
      route,
      anywhere,
      source,
      kupibilet_hot_offer: Boolean(activeForm.kupibiletHotOffer),
      date: dateValue || null,
      return_date: returnDateValue || null,
    };

    setLoading(true);
    setError('');
    try {
      const response = await api.search({
        ...basePayload,
        deep_scan: useFastKupibiletPass ? false : true,
        limit: useFastKupibiletPass ? 10 : null,
      });
      const normalized = Array.isArray(response.tickets) ? response.tickets.map(normalizeTicket) : [];
      setResults(normalized);
      if (switchTab) {
        setTab('results');
      } else {
        setTab('search');
      }
      if (activeForm.kupibiletHotOffer && normalized.length === 0 && !useFastKupibiletPass) {
        setError('Горячие билеты Kupibilet не найдены для этого запроса.');
      }
      if (useFastKupibiletPass) {
        void (async () => {
          try {
            const deepResponse = await api.search({
              ...basePayload,
              deep_scan: true,
              limit: 40,
            });
            const deepTickets = Array.isArray(deepResponse.tickets) ? deepResponse.tickets : [];
            if (!deepTickets.length) {
              setResults((current) => {
                if (!current.length) {
                  setError('Горячие билеты Kupibilet не найдены для этого запроса.');
                }
                return current;
              });
              return;
            }
            setError('');
            setResults((current) => mergeUniqueTickets(current, deepTickets));
          } catch {
            setResults((current) => {
              setError(
                current.length
                  ? 'Первые билеты показаны, но полная догрузка Kupibilet не завершилась. Попробуйте обновить поиск.'
                  : 'Не удалось догрузить горячие билеты Kupibilet. Попробуйте ещё раз.'
              );
              return current;
            });
          }
        })();
      }
      if (authUser) {
        try {
          const historyPayload = await api.history();
          setHistory(Array.isArray(historyPayload.items || historyPayload.history) ? (historyPayload.items || historyPayload.history) : []);
        } catch {
          // Keep current history snapshot when refresh fails.
        }
      }
    } catch (searchError) {
      setError(searchError.message || 'Поисковый запрос не выполнился.');
    } finally {
      setLoading(false);
    }
  }

  async function handleQuickSearch() {
    const quickForm = {
      ...defaultForm,
      from: startupCity.trim(),
      routeMode: 'anywhere',
      source: 'kupibilet',
      kupibiletHotOffer: true,
      date: '',
      rangeStart: '',
      rangeEnd: '',
    };
    setForm(quickForm);
    setTab('search');
    setStartupModalOpen(false);
    await runSearch(quickForm, true, { switchTab: false });
  }

  async function handleAuthSubmit() {
    setLoading(true);
    setError('');
    try {
      const payload = registerMode ? await api.register(authForm) : await api.login(authForm);
      setAuthUser(payload.user || null);
      setAuthForm({ username: '', password: '' });
      setTab('search');
    } catch (authError) {
      setError(authError.message || 'Не удалось выполнить вход.');
    } finally {
      setLoading(false);
    }
  }

  async function handleLogout() {
    await api.logout();
    setAuthUser(null);
    setTab('search');
  }

  async function handleToggleFavorite(ticket) {
    if (!authUser) {
      return;
    }
    const key = getTicketKey(ticket);
    const exists = favoriteKeys.has(key);
    try {
      if (exists) {
        await api.removeFavorite(key);
        setFavorites((current) => current.filter((item) => getTicketKey(item) !== key));
      } else {
        await api.addFavorite(ticket);
        setFavorites((current) => [normalizeTicket(ticket), ...current]);
      }
    } catch (favoriteError) {
      setError(favoriteError.message || 'Не удалось обновить избранное.');
    }
  }

  function handleRepeatHistory(item) {
    const route = String(item.route || '');
    const anywhere = route.includes('Хоть куда');
    const [fromPart, toPart] = route.split('→').map((part) => (part || '').trim());
    const nextForm = {
      ...defaultForm,
      from: fromPart || defaultForm.from,
      to: anywhere ? '' : toPart || '',
      routeMode: anywhere ? 'anywhere' : 'destination',
      searchMode: item.return_date ? 'range' : 'single',
      date: item.date || '',
      rangeStart: item.date || '',
      rangeEnd: item.return_date || '',
      source: item.source === 'kupibilet' ? 'kupibilet' : item.source || 'aviasales',
      kupibiletHotOffer: Boolean(item.kupibilet_hot_offer),
    };
    setForm(nextForm);
    setTab('search');
  }

  async function handleOpenHistoryTickets(item) {
    if (openHistoryId === item.id) {
      setOpenHistoryId(null);
      setHistoryTickets([]);
      setHistoryTicketsTitle('');
      return;
    }

    setLoading(true);
    setError('');
    try {
      const payload = await api.historyTickets(item.id);
      const nextTickets = Array.isArray(payload.tickets) ? payload.tickets.map(normalizeTicket) : [];
      setHistoryTickets(nextTickets);
      setHistoryTicketsTitle(item.route || 'Билеты из истории');
      setOpenHistoryId(item.id);
    } catch (historyError) {
      setError(historyError.message || 'Не удалось загрузить билеты из истории.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <SafeAreaView style={[styles.safeArea, { backgroundColor: theme.background }]}>
      <StatusBar style={darkTheme ? 'light' : 'dark'} />
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        <Text style={[styles.title, { color: theme.text }]}>{TEXT.title}</Text>
        <Text style={[styles.subtitle, { color: theme.muted }]}>{TEXT.subtitle}</Text>
        <AccountStatusBadgeThemed authenticated={Boolean(authUser)} theme={theme} />

        <View style={styles.topBarRow}>
          <View style={styles.tabs}>
            {Object.entries(TEXT.tabs).map(([key, label]) => (
              <ToggleChip key={key} label={label} active={tab === key} onPress={() => setTab(key)} disabled={interactionLocked} theme={theme} />
            ))}
          </View>
          <Pressable
            onPress={() => setThemeMode((current) => (current === 'dark' ? 'light' : 'dark'))}
            style={[styles.themeToggle, { backgroundColor: theme.surface, borderColor: theme.border }]}
          >
            <Text style={[styles.themeToggleLabel, { color: theme.muted }]}>ТЕМА</Text>
            <Text style={[styles.themeToggleValue, { color: theme.text }]}>{darkTheme ? 'Dark' : 'Light'}</Text>
          </Pressable>
        </View>

        {error ? <Text style={styles.errorText}>{error}</Text> : null}
        {checkingSession ? <Text style={[styles.infoText, { color: theme.muted }]}>Проверяем сессию...</Text> : null}

        {tab === 'search' ? (
          <View style={[styles.card, { backgroundColor: theme.surfaceMuted, borderColor: theme.border }]}>
            {!authUser ? <Text style={[styles.infoText, { color: theme.muted }]}>{TEXT.search.guestNote}</Text> : null}

            <ActionButton
              label={parserInfoOpen ? 'Скрыть описание парсера' : 'Что делает парсер'}
              onPress={() => setParserInfoOpen((current) => !current)}
              variant="secondary"
              disabled={interactionLocked}
              theme={theme}
            />

            {parserInfoOpen ? (
              <View style={styles.ticketNote}>
                <Text style={styles.ticketNoteText}>
                  Парсер собирает билеты из подключенных источников в одну выдачу. В обычном режиме можно искать по
                  маршруту, дате и источнику. Отдельно доступен сценарий горячих билетов Kupibilet с временной скидкой
                  и таймером, если источник передаёт эти данные.
                </Text>
              </View>
            ) : null}

            <TextField
              label={TEXT.search.from}
              value={form.from}
              onChange={(value) => setForm((current) => ({ ...current, from: value }))}
              placeholder={TEXT.search.fromPlaceholder}
              disabled={!canUseMainParser || interactionLocked}
              theme={theme}
              suggestions
            />

            <TextField
              label={TEXT.search.to}
              value={form.to}
              onChange={(value) => setForm((current) => ({ ...current, to: value }))}
              placeholder={TEXT.search.toPlaceholder}
              disabled={!canUseMainParser || interactionLocked || form.routeMode === 'anywhere' || form.kupibiletHotOffer}
              dimmed={form.routeMode === 'anywhere'}
              theme={theme}
              suggestions
            />

            <SectionLabel theme={theme}>{TEXT.search.routeTitle}</SectionLabel>
            <View style={styles.inlineRow}>
              <ToggleChip
                label={TEXT.search.exactRoute}
                active={form.routeMode === 'destination'}
                onPress={() => setForm((current) => ({ ...current, routeMode: 'destination' }))}
                disabled={!canUseMainParser || interactionLocked || form.kupibiletHotOffer}
                theme={theme}
              />
              <ToggleChip
                label={TEXT.search.anywhere}
                active={form.routeMode === 'anywhere'}
                onPress={() =>
                  setForm((current) => ({
                    ...current,
                    routeMode: 'anywhere',
                    ...(current.kupibiletHotOffer
                      ? {
                          date: '',
                          rangeStart: '',
                          rangeEnd: '',
                          searchMode: 'single',
                        }
                      : null),
                  }))
                }
                disabled={!canUseMainParser || interactionLocked}
                theme={theme}
              />
            </View>

            <SectionLabel theme={theme}>{TEXT.search.dateTitle}</SectionLabel>
            <View style={styles.inlineRow}>
              <ToggleChip
                label={TEXT.search.singleDay}
                active={form.searchMode === 'single'}
                onPress={() => setForm((current) => ({ ...current, searchMode: 'single' }))}
                disabled={!canUseMainParser || interactionLocked || hotAnywhereDateLocked}
                theme={theme}
              />
              <ToggleChip
                label={TEXT.search.range}
                active={form.searchMode === 'range'}
                onPress={() => setForm((current) => ({ ...current, searchMode: 'range' }))}
                disabled={!canUseMainParser || interactionLocked || hotAnywhereDateLocked}
                theme={theme}
              />
            </View>

            {form.searchMode === 'single' ? (
              <View style={[styles.fieldBlock, hotAnywhereDateLocked ? styles.fieldBlockDimmed : null]}>
                <SectionLabel theme={theme}>{TEXT.search.date}</SectionLabel>
                <DateInput
                  value={form.date}
                  onChange={(value) => setForm((current) => ({ ...current, date: value }))}
                  disabled={!canUseMainParser || interactionLocked || hotAnywhereDateLocked}
                  theme={theme}
                />
              </View>
            ) : (
              <View style={styles.rangeGrid}>
                <View style={[styles.fieldBlockRange, hotAnywhereDateLocked ? styles.fieldBlockDimmed : null]}>
                  <SectionLabel theme={theme}>{TEXT.search.dateFrom}</SectionLabel>
                  <DateInput
                    value={form.rangeStart}
                    onChange={(value) => setForm((current) => ({ ...current, rangeStart: value }))}
                      disabled={!canUseMainParser || interactionLocked || hotAnywhereDateLocked}
                    theme={theme}
                  />
                </View>
                <View style={[styles.fieldBlockRange, hotAnywhereDateLocked ? styles.fieldBlockDimmed : null]}>
                  <SectionLabel theme={theme}>{TEXT.search.dateTo}</SectionLabel>
                  <DateInput
                    value={form.rangeEnd}
                    onChange={(value) => setForm((current) => ({ ...current, rangeEnd: value }))}
                      disabled={!canUseMainParser || interactionLocked || hotAnywhereDateLocked}
                    theme={theme}
                  />
                </View>
              </View>
            )}

            <SectionLabel theme={theme}>{TEXT.search.sourceTitle}</SectionLabel>
            <View style={styles.inlineRow}>
              {visibleSourceOptions.map((option) => (
                <ToggleChip
                  key={option.key}
                  label={option.label}
                  active={form.source === option.key}
                  onPress={() => setForm((current) => ({ ...current, source: option.key }))}
                  disabled={!canUseMainParser || interactionLocked || form.kupibiletHotOffer}
                  theme={theme}
                />
              ))}
            </View>

            {(form.source === 'kupibilet' || form.routeMode === 'anywhere') ? (
              <View style={[styles.hotToggleBox, { backgroundColor: theme.surface, borderColor: theme.border }]}>
                <View style={styles.hotToggleText}>
                  <Text style={[styles.hotToggleTitle, { color: theme.text }]}>{TEXT.search.hotTitle}</Text>
                  <Text style={[styles.hotToggleDescription, { color: theme.muted }]}>{TEXT.search.hotDescription}</Text>
                </View>
                <Switch
                  value={form.kupibiletHotOffer}
                  onValueChange={(value) =>
                    setForm((current) => ({
                      ...current,
                      kupibiletHotOffer: value,
                      source: value ? 'kupibilet' : current.routeMode === 'anywhere' ? 'aviasales' : current.source,
                      routeMode: value ? 'anywhere' : current.routeMode,
                      ...(value
                        ? {
                            date: '',
                            rangeStart: '',
                            rangeEnd: '',
                            searchMode: 'single',
                          }
                        : null),
                    }))
                  }
                  disabled={!canUseMainParser || interactionLocked}
                />
              </View>
            ) : null}

            {!authUser ? <Text style={[styles.infoText, { color: theme.muted }]}>{TEXT.search.blocked}</Text> : null}
            {hasSearchResults && !loading ? (
              <Text style={[styles.infoText, { color: theme.muted }]}>Билеты уже загружены. Можно обновить поиск с новыми параметрами.</Text>
            ) : null}
            <ActionButton
              label={loading ? 'Ищем...' : TEXT.search.submit}
              onPress={() => runSearch(form)}
              disabled={!canSearch || interactionLocked}
              theme={theme}
            />
          </View>
        ) : null}

        {tab === 'search' && results.length ? (
          <View style={[styles.card, { backgroundColor: theme.surfaceMuted, borderColor: theme.border }]}>
            {displayedResults.map((ticket) => (
              <TicketCard
                key={getTicketKey(ticket)}
                ticket={ticket}
                isFavorite={favoriteKeys.has(getTicketKey(ticket))}
                canToggleFavorite={Boolean(authUser)}
                onToggleFavorite={handleToggleFavorite}
                loading={loading}
                nowMs={nowTick}
                theme={theme}
              />
            ))}
          </View>
        ) : null}

        {tab === 'results' ? (
          <View style={[styles.card, { backgroundColor: theme.surfaceMuted, borderColor: theme.border }]}>
            {displayedResults.length ? (
              displayedResults.map((ticket) => (
                <TicketCard
                  key={getTicketKey(ticket)}
                  ticket={ticket}
                  isFavorite={favoriteKeys.has(getTicketKey(ticket))}
                  canToggleFavorite={Boolean(authUser)}
                  onToggleFavorite={handleToggleFavorite}
                  loading={loading}
                  nowMs={nowTick}
                  theme={theme}
                />
              ))
            ) : (
              <Text style={[styles.infoText, { color: theme.muted }]}>{TEXT.resultsEmpty}</Text>
            )}
          </View>
        ) : null}

        {tab === 'favorites' ? (
          <View style={[styles.card, { backgroundColor: theme.surfaceMuted, borderColor: theme.border }]}>
            {displayedFavorites.length ? (
              displayedFavorites.map((ticket) => (
                <TicketCard
                  key={getTicketKey(ticket)}
                  ticket={ticket}
                  isFavorite
                  canToggleFavorite={Boolean(authUser)}
                  onToggleFavorite={handleToggleFavorite}
                  loading={loading}
                  nowMs={nowTick}
                  theme={theme}
                />
              ))
            ) : (
              <Text style={[styles.infoText, { color: theme.muted }]}>{TEXT.favoritesEmpty}</Text>
            )}
          </View>
        ) : null}

        {tab === 'history' ? (
          <View style={[styles.card, { backgroundColor: theme.surfaceMuted, borderColor: theme.border }]}>
            {history.length ? (
              history.map((item) => (
                <View key={String(item.id)} style={[styles.historyItem, { backgroundColor: theme.surface, borderColor: theme.border }]}>
                  <Text style={[styles.historyRoute, { color: theme.text }]}>{item.route}</Text>
                  <Text style={[styles.historyMeta, { color: theme.muted }]}>{item.date || 'Дата не указана'}</Text>
                  <Text style={[styles.historyMeta, { color: theme.muted }]}>{item.source}</Text>
                  <Text style={[styles.historyMeta, { color: theme.muted }]}>
                    Найдено билетов: {Number(item.result_count || 0)}
                  </Text>
                  <Text style={[styles.historyMeta, { color: theme.muted }]}>
                    Запрос выполнен: {formatDateTime(item.created_at)}
                  </Text>
                  <View style={styles.ticketActions}>
                    <ActionButton
                      label={openHistoryId === item.id ? 'Свернуть билеты' : 'Посмотреть билеты'}
                      onPress={() => handleOpenHistoryTickets(item)}
                      variant="secondary"
                      disabled={interactionLocked}
                      theme={theme}
                    />
                    <ActionButton label={TEXT.repeatSearch} onPress={() => handleRepeatHistory(item)} disabled={interactionLocked} theme={theme} />
                  </View>

                  {openHistoryId === item.id && historyTickets.length > 0 ? (
                    <View style={styles.historyTicketsInline}>
                      <Text style={[styles.historyRoute, { color: theme.text }]}>Билеты запроса</Text>
                      <Text style={[styles.historyMeta, { color: theme.muted }]}>{historyTicketsTitle}</Text>
                      {displayedHistoryTickets.map((ticket) => (
                        <TicketCard
                          key={`history-${item.id}-${getTicketKey(ticket)}`}
                          ticket={ticket}
                          isFavorite={favoriteKeys.has(getTicketKey(ticket))}
                          canToggleFavorite={Boolean(authUser)}
                          onToggleFavorite={handleToggleFavorite}
                          loading={loading}
                          nowMs={nowTick}
                          theme={theme}
                        />
                      ))}
                    </View>
                  ) : null}
                </View>
              ))
            ) : (
              <Text style={[styles.infoText, { color: theme.muted }]}>{TEXT.historyEmpty}</Text>
            )}
          </View>
        ) : null}

        {tab === 'account' ? (
          <View style={[styles.card, { backgroundColor: theme.surfaceMuted, borderColor: theme.border }]}>
            {authUser ? (
              <>
                <AccountStatusBadgeThemed authenticated theme={theme} />
                <Text style={[styles.accountText, { color: theme.text }]}>
                  {TEXT.auth.current} {authUser.username}
                </Text>
                <ActionButton label={TEXT.auth.logout} onPress={handleLogout} theme={theme} />
              </>
            ) : (
              <>
                <AccountStatusBadgeThemed authenticated={false} theme={theme} />
                <Text style={[styles.accountTitle, { color: theme.text }]}>
                  {registerMode ? TEXT.auth.registerTitle : TEXT.auth.loginTitle}
                </Text>
                <TextField
                  label={TEXT.auth.username}
                  value={authForm.username}
                  onChange={(value) => setAuthForm((current) => ({ ...current, username: value }))}
                  placeholder="username"
                  theme={theme}
                />
                <TextField
                  label={TEXT.auth.password}
                  value={authForm.password}
                  onChange={(value) => setAuthForm((current) => ({ ...current, password: value }))}
                  placeholder="password"
                  theme={theme}
                />
                <ActionButton
                  label={loading ? 'Подождите...' : registerMode ? TEXT.auth.submitRegister : TEXT.auth.submitLogin}
                  onPress={handleAuthSubmit}
                  disabled={loading || !authForm.username || !authForm.password}
                  theme={theme}
                />
                <Pressable onPress={() => setRegisterMode((value) => !value)}>
                  <Text style={[styles.switchAuthText, { color: theme.primary }]}>
                    {registerMode ? TEXT.auth.switchLogin : TEXT.auth.switchRegister}
                  </Text>
                </Pressable>
              </>
            )}
          </View>
        ) : null}
      </ScrollView>

      <StartupModal
        visible={startupModalOpen}
        city={startupCity}
        onCityChange={setStartupCity}
        onSkip={() => setStartupModalOpen(false)}
        onSubmit={handleQuickSearch}
        loading={loading}
        theme={theme}
      />
    </SafeAreaView>
  );
}

export default function App() {
  return (
    <AppErrorBoundary>
      <AppInner />
    </AppErrorBoundary>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#dfeaf8',
  },
  container: {
    flex: 1,
  },
  content: {
    padding: 18,
    paddingBottom: 48,
    gap: 14,
  },
  title: {
    fontSize: 22,
    fontWeight: '800',
    color: '#173057',
  },
  subtitle: {
    color: '#6482ad',
    fontSize: 14,
    marginBottom: 4,
  },
  accountStatusBadge: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 999,
    borderWidth: 1,
  },
  accountStatusBadgeOn: {
    backgroundColor: '#ecfff3',
    borderColor: '#92ddb0',
  },
  accountStatusBadgeOff: {
    backgroundColor: '#fff0f0',
    borderColor: '#efb1b1',
  },
  accountStatusDot: {
    width: 10,
    height: 10,
    borderRadius: 999,
  },
  accountStatusDotOn: {
    backgroundColor: '#2db35f',
  },
  accountStatusDotOff: {
    backgroundColor: '#df4545',
  },
  accountStatusText: {
    fontWeight: '800',
  },
  accountStatusTextOn: {
    color: '#1e7f46',
  },
  accountStatusTextOff: {
    color: '#b53c3c',
  },
  tabs: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    flex: 1,
  },
  topBarRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
    alignItems: 'flex-start',
  },
  themeToggle: {
    minWidth: 118,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 18,
    borderWidth: 1,
    gap: 2,
  },
  themeToggleLabel: {
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.8,
  },
  themeToggleValue: {
    fontSize: 18,
    fontWeight: '900',
  },
  card: {
    backgroundColor: '#f9fbff',
    borderRadius: 24,
    borderWidth: 1,
    borderColor: '#bdd3f1',
    padding: 16,
    gap: 12,
  },
  fieldBlock: {
    gap: 8,
  },
  fieldBlockDimmed: {
    opacity: 0.72,
  },
  fieldBlockRange: {
    flex: 1,
    gap: 8,
    minWidth: 220,
  },
  rangeGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  sectionLabel: {
    fontSize: 15,
    fontWeight: '700',
    color: '#203c67',
  },
  input: {
    borderWidth: 1,
    borderColor: '#bdd3f1',
    borderRadius: 18,
    paddingHorizontal: 16,
    paddingVertical: 14,
    backgroundColor: '#ffffff',
    color: '#173057',
    fontSize: 16,
  },
  inputDisabled: {
    backgroundColor: '#eef4ff',
    color: '#86a0c0',
  },
  citySuggestions: {
    borderWidth: 1,
    borderRadius: 18,
    overflow: 'hidden',
  },
  citySuggestionItem: {
    minHeight: 46,
    paddingHorizontal: 14,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  citySuggestionItemPressed: {
    opacity: 0.72,
  },
  citySuggestionName: {
    fontSize: 15,
    fontWeight: '800',
  },
  citySuggestionMeta: {
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 0.8,
  },
  button: {
    minHeight: 50,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 18,
  },
  buttonPrimary: {
    backgroundColor: '#2f72d7',
  },
  buttonSecondary: {
    backgroundColor: '#ffffff',
    borderWidth: 1,
    borderColor: '#bdd3f1',
  },
  buttonDisabled: {
    opacity: 0.55,
  },
  buttonPressed: {
    transform: [{ scale: 0.99 }],
  },
  buttonText: {
    color: '#ffffff',
    fontWeight: '800',
    fontSize: 16,
  },
  buttonSecondaryText: {
    color: '#234a81',
  },
  toggleChip: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#bdd3f1',
    backgroundColor: '#ffffff',
  },
  toggleChipActive: {
    backgroundColor: '#dcebff',
    borderColor: '#3a7ae0',
  },
  toggleChipDisabled: {
    opacity: 0.55,
  },
  toggleChipText: {
    color: '#2f4e7b',
    fontWeight: '700',
  },
  toggleChipTextActive: {
    color: '#2f72d7',
  },
  inlineRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  errorText: {
    color: '#b93131',
    fontWeight: '700',
  },
  infoText: {
    color: '#5f7da7',
    fontSize: 14,
    lineHeight: 22,
  },
  hotToggleBox: {
    borderWidth: 1,
    borderColor: '#bdd3f1',
    borderRadius: 20,
    padding: 14,
    backgroundColor: '#ffffff',
    flexDirection: 'row',
    gap: 12,
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  hotToggleText: {
    flex: 1,
    gap: 6,
  },
  hotToggleTitle: {
    color: '#173057',
    fontWeight: '800',
    fontSize: 15,
  },
  hotToggleDescription: {
    color: '#5f7da7',
    fontSize: 13,
    lineHeight: 20,
  },
  modalOverlay: {
    position: 'fixed',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    backgroundColor: 'rgba(13, 28, 53, 0.48)',
    zIndex: 50,
    elevation: 50,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 18,
  },
  modalCard: {
    pointerEvents: 'auto',
    width: '100%',
    maxWidth: 680,
    backgroundColor: '#f9fbff',
    borderRadius: 28,
    borderWidth: 1,
    borderColor: '#bdd3f1',
    padding: 20,
    gap: 14,
  },
  modalBadge: {
    alignSelf: 'flex-start',
    backgroundColor: '#2f72d7',
    color: '#ffffff',
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 999,
    fontWeight: '800',
  },
  modalTitle: {
    fontSize: 24,
    fontWeight: '800',
    color: '#173057',
  },
  modalBody: {
    color: '#5f7da7',
    fontSize: 15,
    lineHeight: 24,
  },
  modalActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
    justifyContent: 'flex-end',
  },
  ticketCard: {
    borderWidth: 1,
    borderColor: '#d6e2f7',
    borderRadius: 24,
    padding: 16,
    backgroundColor: '#ffffff',
    gap: 12,
  },
  ticketHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 10,
  },
  ticketSource: {
    alignSelf: 'flex-start',
    backgroundColor: '#dff0ff',
    color: '#2d5687',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 999,
    fontWeight: '800',
  },
  ticketPriceBlock: {
    alignItems: 'flex-end',
    gap: 2,
  },
  ticketOldPrice: {
    color: '#8c9fbe',
    textDecorationLine: 'line-through',
    fontWeight: '700',
  },
  ticketPrice: {
    color: '#173057',
    fontWeight: '900',
    fontSize: 18,
  },
  ticketRoute: {
    color: '#173057',
    fontSize: 18,
    fontWeight: '900',
    lineHeight: 28,
  },
  ticketSubroute: {
    color: '#315889',
    fontWeight: '700',
  },
  ticketMeta: {
    color: '#315889',
    fontWeight: '700',
  },
  hotBadge: {
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderColor: '#f2b79d',
    backgroundColor: '#fff1ea',
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  hotBadgeActive: {
    backgroundColor: '#ffe9dd',
  },
  hotBadgeExpired: {
    backgroundColor: '#eef4ff',
    borderColor: '#c5d8f3',
  },
  hotBadgeText: {
    color: '#e25f28',
    fontWeight: '800',
  },
  hotBadgeTextActive: {
    color: '#d45a23',
  },
  ticketInfo: {
    color: '#5a769f',
    fontSize: 15,
  },
  ticketNote: {
    backgroundColor: '#edf5ff',
    borderRadius: 18,
    borderWidth: 1,
    borderColor: '#c6daf6',
    padding: 14,
  },
  ticketNoteText: {
    color: '#52739f',
    lineHeight: 24,
  },
  ticketActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  historyItem: {
    borderWidth: 1,
    borderColor: '#d6e2f7',
    borderRadius: 18,
    padding: 14,
    gap: 8,
    backgroundColor: '#ffffff',
  },
  historyRoute: {
    color: '#173057',
    fontWeight: '800',
    fontSize: 17,
  },
  historyMeta: {
    color: '#5f7da7',
  },
  historyTicketsInline: {
    marginTop: 10,
    gap: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#dbe6f7',
  },
  accountTitle: {
    color: '#173057',
    fontSize: 22,
    fontWeight: '800',
  },
  accountText: {
    color: '#173057',
    fontSize: 16,
    fontWeight: '700',
  },
  switchAuthText: {
    color: '#2f72d7',
    fontWeight: '700',
    textAlign: 'center',
  },
  errorBoundary: {
    flex: 1,
    justifyContent: 'center',
    padding: 24,
    backgroundColor: '#f7fbff',
  },
  errorBoundaryTitle: {
    fontSize: 22,
    fontWeight: '800',
    color: '#b93131',
    marginBottom: 12,
  },
  errorBoundaryText: {
    color: '#173057',
    lineHeight: 24,
  },
});
