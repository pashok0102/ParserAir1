# ParserAir

Проект состоит из:

- `api` и Django backend в корне проекта
- `project` и React + Vite frontend

## Что нужно установить на другом компьютере

- Python 3.11+
- Node.js 18+
- npm

## Первый запуск

### 1. Скачать проект

```powershell
git clone <URL_РЕПОЗИТОРИЯ>
cd ParserAir\project
```

### 2. Настроить backend

Создать `.env` по примеру:

```powershell
Copy-Item .env.example .env
```

Создать виртуальное окружение и установить зависимости:

```powershell
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Применить миграции:

```powershell
python manage.py migrate
```

### 3. Настроить frontend

```powershell
cd project
npm install
```

## Команды запуска

### Backend

Из корня проекта:

```powershell
cd C:\Users\kavik\Documents\GitHub\ParserAir\project
.\venv\Scripts\Activate.ps1
python manage.py runserver
```

Если `python` не работает:

```powershell
.\venv\Scripts\python.exe manage.py runserver
```

### Frontend

В отдельном терминале:

```powershell
cd C:\Users\kavik\Documents\GitHub\ParserAir\project\project
npm run dev
```

## Адреса

- frontend: `http://localhost:5173`
- backend: `http://127.0.0.1:8000`

## Полезно

Если PowerShell блокирует активацию venv:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```




Если после изменений не видно новый результат поиска, запусти новый поиск, а не старую запись из истории.

cd C:\Users\kavik\Documents\GitHub\ParserAir\project
& .\venv\Scripts\Activate.ps1
python manage.py migrate
python manage.py runserver



cd C:\Users\kavik\Documents\GitHub\ParserAir\project\project
npm run dev





## Mobile React Native

В проект добавлен отдельный мобильный клиент:

- папка: `mobile`
- стек: React Native + Expo

Быстрый запуск мобильной версии:

```powershell
cd mobile
$env:EXPO_PUBLIC_API_BASE_URL="http://95.78.208.42:8000/api"
npm install
npx expo start
```

Backend для телефона нужно поднимать так:

```powershell
& .\venv\Scripts\Activate.ps1
python manage.py runserver 0.0.0.0:8000
```

Подробная инструкция лежит в `mobile\README.md`.

PC

cd C:\Users\kavik\Desktop\ParserAir-main\project
python manage.py runserver

cd C:\Users\kavik\Desktop\ParserAir-main\project\project
npm run dev

MOBILE 

cd C:\Users\kavik\Desktop\ParserAir-main\project\mobile
$env:EXPO_PUBLIC_API_BASE_URL="http://192.168.0.103:8000/api"
npx expo start