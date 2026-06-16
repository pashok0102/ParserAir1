# AirParser Mobile

Отдельный мобильный клиент на React Native + Expo. Веб-версия проекта не меняется.

## Что уже готово

- вход и регистрация
- поиск билетов
- результаты
- история поиска
- избранное
- светлая и тёмная тема

## Запуск на телефоне

### 1. Подними backend

Из папки, где лежит `manage.py`:

```powershell
& .\venv\Scripts\Activate.ps1
python manage.py runserver 0.0.0.0:8000
```

Для телефона backend нужно запускать именно на `0.0.0.0:8000`.

### 2. Узнай IP компьютера

```powershell
ipconfig
```

Нужен IPv4-адрес, например `192.168.0.15`.

### 3. Запусти Expo-клиент

Из папки `mobile`:

```powershell
$env:EXPO_PUBLIC_API_BASE_URL="http://192.168.0.15:8000/api"
npm install
npx expo start
```

Потом открой `Expo Go` на телефоне и отсканируй QR-код.

## Android-эмулятор

```powershell
$env:EXPO_PUBLIC_API_BASE_URL="http://10.0.2.2:8000/api"
npm install
npx expo start --android
```

## Важно

Телефон и компьютер должны быть в одной Wi-Fi сети.

Текущая мобильная версия использует те же Django API-роуты, что и веб-клиент. Если в конкретной среде сессионные cookie будут вести себя нестабильно, следующим шагом лучше перевести мобильную авторизацию на токены.
