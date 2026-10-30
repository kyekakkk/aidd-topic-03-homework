# Технический отчёт по проекту Investing Demo (Django)

> Документ подготовлен по результатам анализа исходного кода проекта.
> Все выводы опираются на фактические файлы репозитория (модели, представления, URL, настройки, зависимости).

---

## 1. Назначение приложения и технологический стек

### 1.1 Назначение

**Investing Demo** — веб-приложение для просмотра и обслуживания справочника биржевых инструментов (акций), построенное на основе данных **Tinkoff Invest API**.

Основные возможности (фактически реализованные в коде):

- Хранение справочника акций в базе данных (тикер, наименование, ISIN, FIGI, валюта, UID).
- Автоматическая загрузка перечня акций из Tinkoff Invest API в БД (management-команда `add_shares`).
- Периодическое обновление текущей цены акции фоновой задачей Celery (`update_last_price`) и определение признака роста/падения цены (`is_trend_high`).
- Отображение списка акций с пагинацией и цветовой индикацией роста/падения цены.
- Просмотр детальной карточки акции с графиком исторических цен за 180 дней (Plotly).
- CRUD-операции над акциями через веб-интерфейс (только для авторизованных пользователей).
- REST API для работы с акциями (список, детали, создание, изменение, удаление).
- Регистрация, авторизация и выход пользователей (на базе встроенной модели `django.contrib.auth.User`).

### 1.2 Технологический стек

| Уровень | Технология | Подтверждение |
|---|---|---|
| Язык | Python | `manage.py`, весь код |
| Web-фреймворк | Django 4.1.7 | `requirements.txt`, `config/settings.py` |
| REST API | Django REST Framework 3.14.0 | `dashboard/api/**`, `settings.REST_FRAMEWORK` |
| Фильтрация API | django-filter 22.1 | `dashboard/api/v1/views.py`, `INSTALLED_APPS` |
| Формы | django-crispy-forms 2.0 + crispy-bootstrap3 | `settings`, `dashboard/templates/dashboard/create.html` |
| БД | PostgreSQL (драйвер psycopg2-binary) | `settings.DATABASES`, `docker-compose.yml` |
| Асинхронные задачи | Celery 5.2.7 + Redis (broker) | `config/celery.py`, `settings` (CELERY_*) |
| Внешний источник данных | Tinkoff Invest API | `tinkoff`, `tinkoff-investments` в `requirements.txt` |
| Визуализация | Plotly 5.13.1 | `dashboard/services/graph.py` |
| Frontend | HTML-шаблоны Django + Bootstrap (CDN/static) | `*/templates/**`, `*/static/**` |
| Инфраструктура | Docker Compose (PostgreSQL + Redis) | `docker-compose.yml` |
| Инструменты качества кода | black, isort | `requirements.txt` |

Дополнительные (транзитивные) зависимости, необходимые SDK Tinkoff и Celery: `protobuf`, `grpcio`, `pydantic`, `cachetools`, `tenacity`, `kombu`, `amqp`, `redis`, `billiard` и др.

---

## 2. Структура проекта, основные компоненты и их назначение

Проект состоит из конфигурационного пакета `config` и двух приложений Django: `dashboard` и `user`.

```
aidd-topic-03-homework/
├── config/                # Конфигурация проекта
│   ├── settings.py        # Настройки Django, БД, Celery, DRF, логирование
│   ├── urls.py            # Корневой URL-конфиг
│   ├── celery.py          # Инициализация Celery + расписание beat
│   ├── wsgi.py / asgi.py  # Точки входа WSGI/ASGI
│   └── __init__.py        # Экспорт celery_app
├── dashboard/             # Основное приложение (акции, API, задачи)
│   ├── models.py          # Модели Share, Portfolio, PortfolioPosition
│   ├── views.py           # CBV: список/детали/CRUD акций, портфель, торговля
│   ├── forms.py           # ShareModelForm, TradeForm
│   ├── urls.py            # Маршруты приложения (app_name="dashboard")
│   ├── admin.py           # Регистрация Share в админке
│   ├── tasks.py           # Celery-задача update_last_price
│   ├── services/          # Слой бизнес-логики
│   │   ├── market_data.py # Получение последней цены через Tinkoff API
│   │   └── graph.py       # Построение графика котировок (Plotly)
│   ├── management/commands/add_shares.py  # Загрузка списка акций
│   ├── api/               # REST API
│   │   └── v1/            # Версия 1: router, views (ViewSet), serializer
│   ├── migrations/        # 8 миграций (эволюция Share + Portfolio/PortfolioPosition)
│   ├── templates/dashboard/  # base/create/delete/detail/list/portfolio.html
│   └── static/dashboard/     # bootstrap.min.css, sticky-footer-navbar.css
├── user/                  # Приложение аутентификации
│   ├── forms.py           # RegistrationForm, AuthForm
│   ├── views.py           # AuthView, RegistrationView, LogoutView
│   ├── urls.py            # login/registration/logout
│   ├── models.py          # Только реэкспорт get_user_model()
│   ├── templates/user/    # base/auth/registration.html
│   └── static/user/       # bootstrap.min.css, signin.css
├── docker-compose.yml     # PostgreSQL + Redis
├── manage.py              # Точка входа CLI Django
├── requirements.txt       # Список зависимостей
└── README.md / HOMEWORK.md
```

### Назначение ключевых компонентов

- **config** — единая конфигурация: подключение БД (`investing` в PostgreSQL на `localhost:5432`), настройки DRF (пагинация `LimitOffsetPagination`, размер страницы 100, фильтр `DjangoFilterBackend`), настройки Celery (broker Redis `redis://127.0.0.1:6379/0`, timezone `Europe/Moscow`), логирование в консоль и файл `app.logs`.
- **dashboard/models.py** — единственная доменная модель `Share`.
- **dashboard/views.py** — веб-контроллеры (HTML-интерфейс) на базе generic-классов Django.
- **dashboard/services/** — изоляция интеграции с внешним API (`market_data.py`) и визуализации (`graph.py`).
- **dashboard/tasks.py** — единственная фоновая задача обновления цен.
- **dashboard/api/v1/** — REST-слой: `ShareViewSet` (полный CRUD), `ShareSerializer`, `ShareFilter`, маршрутизация через `DefaultRouter` (`/api/v1/shares/`).
- **dashboard/management/commands/add_shares.py** — команда первичной загрузки акций (`python manage.py add_shares`).
- **user/** — аутентификация на базе стандартного `django.contrib.auth`; собственных моделей не содержит.

---

## 3. Архитектура приложения и взаимодействие компонентов

### 3.1 Общий характер архитектуры

Приложение построено по шаблону **MVT (Model–View–Template)** Django с элементами слоистой организации (выделен слой `services`) и дополнено:

- REST-слоем на Django REST Framework;
- асинхронным слоем на Celery (worker + beat);
- интеграционным слоем к внешнему сервису Tinkoff Invest API.

Условно архитектуру можно представить так:

```
Пользователь / клиент
        │
        ▼
┌───────────────────────────┐
│  Точка входа: WSGI / ASGI  │  config/wsgi.py, config/asgi.py
└─────────────┬─────────────┘
              ▼
┌───────────────────────────┐
│  URL-маршрутизация         │  config/urls.py → dashboard/urls.py, user/urls.py
└─────────────┬─────────────┘
              ▼
┌───────────────────────────┐        ┌────────────────────────┐
│  Представления (контроллеры)│       │  REST API (DRF)         │
│  dashboard/views.py        │       │  api/v1/views.py        │
│  user/views.py             │       │  (ModelViewSet + router)│
└─────────────┬─────────────┘        └───────────┬────────────┘
              ▼                                   ▼
┌───────────────────────────┐        ┌────────────────────────┐
│  Формы / Шаблоны           │        │  Сериализаторы          │
│  forms.py, templates/**    │        │  serializer.py          │
└─────────────┬─────────────┘        └───────────┬────────────┘
              └──────────────┬────────────────────┘
                             ▼
                ┌────────────────────────────┐
                │  Слой бизнес-логики          │  services/market_data.py, graph.py
                │  (обращение к Tinkoff API)   │  tasks.py (Celery)
                └───────────┬────────────────┘
                            ▼
                ┌────────────────────────────┐
                │  ORM Django → PostgreSQL     │  Share.objects...
                └────────────────────────────┘

Параллельно: Celery Beat (расписание) → Celery Worker (update_last_price) → Tinkoff API → БД
```

### 3.2 Взаимодействие компонентов по сценариям

**A. Просмотр списка акций (HTML).**
`GET /` → `config.urls` → `dashboard.urls` → `ShareListView` (ListView) → ORM-запрос `Share` (сортировка по `name`, пагинация 100) → шаблон `dashboard/list.html`. Шаблон цветом подсвечивает цену в зависимости от `is_trend_high`; кнопки создания/редактирования/удаления выводятся только для аутентифицированных пользователей.

**B. Просмотр карточки акции (HTML + график).**
`GET /<pk>` → `ShareDetailView.get()` → `Share.objects.get(id=pk)` → вызов `services.graph.get_graph(share)`, которая через Tinkoff SDK (`Client`, `get_all_candles`, интервал `CANDLE_INTERVAL_DAY`) получает дневные свечи за 180 дней и формирует HTML-разметку графика Plotly (`plot(..., output_type="div")`) → рендер `dashboard/detail.html` (`plot_div` вставляется с `autoescape off`).

**C. CRUD акций (HTML).**
- Создание: `GET/POST /create` → `ShareCreateView(CreateView)` + `ShareModelForm` (`fields = "__all__"`) → сохранение в БД.
- Редактирование: `GET/POST /update/<pk>` → `ShareUpdateView(UpdateView)`.
- Удаление: `GET/POST /delete/<pk>` → `ShareDeleteView(DeleteView)`.

Все три представления наследуют `IsUserAuthenticatedMixin` (на базе `UserPassesTestMixin`); при отсутствии авторизации выполняется редирект на главную (`dashboard:index`).

**D. Аутентификация (HTML, session-based).**
- `GET/POST /user/login/` → `AuthView`: `authenticate(username=email.lower(), password=...)` → при успехе `login(request, user)` и редирект на главную; при ошибке — возврат формы с сообщением об ошибке.
- `GET/POST /user/registration/` → `RegistrationView`: валидация `RegistrationForm`, `form.save()` (создаёт пользователя через `User.objects.create_user(email, email, password)`), затем автоматический вход.
- `GET /user/logout/` → `LogoutView`: `logout(request)` и редирект на главную.

**E. REST API.**
`/api/v1/shares/` → `dashboard.api.v1.router` (`DefaultRouter`) → `ShareViewSet(ModelViewSet)` → `ShareSerializer`. Поддерживаются фильтрация (`ShareFilter` по `name`, `ticker`), поиск (`SearchFilter`, `search_fields = ["$name"]`), сортировка (`OrderingFilter` по `name`, `ticker`), пагинация `LimitOffsetPagination` (100).

**F. Фоновая обработка (Celery).**
- `config/celery.py` создаёт Celery-приложение, читает настройки из `django.conf:settings` с префиксом `CELERY`, выполняет `autodiscover_tasks()` и задаёт расписание `beat_schedule`.
- Расписание `add-every-5-min` (фактически `schedule = 10.0` секунд) вызывает задачу `dashboard.tasks.update_last_price`.
- Задача перебирает все `Share`, для каждой получает последнюю цену через `services.market_data.get_last_data` (Tinkoff SDK, `market_data.get_last_prices`), сравнивает с сохранённой `last_price`, вычисляет `is_trend_high` и обновляет запись через `Share.objects.filter(id=...).update(...)`.

**G. Первичное наполнение БД.**
`python manage.py add_shares` → `Command.handle()` → перебор `client.instruments.shares()` из Tinkoff API → `Share.objects.get_or_create(...)`.

### 3.3 Точки интеграции

- **Внешний сервис:** Tinkoff Invest API, доступ через SDK `tinkoff.invest` (токен `TINKOFF_TOKEN` в `config/settings.py`).
- **Брокер сообщений:** Redis (`redis://127.0.0.1:6379/0`) для Celery.
- **БД:** PostgreSQL (`investing`).

---

## 4. Используемые библиотеки и внешние зависимости

Зависимости зафиксированы в `requirements.txt`. Ключевые (прямые) зависимости и их назначение:

| Библиотека | Версия | Назначение |
|---|---|---|
| Django | 4.1.7 | Web-фреймворк, ORM, админка, аутентификация |
| djangorestframework | 3.14.0 | REST API (ViewSet, Serializer, Router) |
| django-filter | 22.1 | Фильтрация в API и веб-формах |
| django-crispy-forms | 2.0 | Отрисовка форм (`as_crispy_field`) |
| crispy-bootstrap3 | 2022.1 | Тема Bootstrap 3 для crispy-forms |
| psycopg2-binary | 2.9.5 | Драйвер PostgreSQL |
| celery | 5.2.7 | Фоновая обработка задач и расписание |
| redis | 4.5.1 | Клиент Redis (broker Celery) |
| tinkoff | 0.1.1 | SDK Tinkoff Invest API (старый пакет) |
| tinkoff-investments | 0.2.0b50 | SDK Tinkoff Invest API (используется в коде) |
| plotly | 5.13.1 | Построение графиков котировок |
| black | 23.1.0 | Форматирование кода (dev) |
| isort | 5.12.0 | Сортировка импортов (dev) |

Транзитивные зависимости, видимые в списке: `protobuf`, `grpcio`, `pydantic`, `cachetools`, `tenacity`, `python-dateutil`, `pytz`, `kombu`, `amqp`, `billiard`, `vine`, `click`, `click-didyoumean`, `click-plugins`, `click-repl`, `prompt-toolkit`, `wcwidth`, `asgiref`, `async-timeout`, `sqlparse`, `packaging`, `pathspec`, `platformdirs`, `tomli`, `typing_extensions`, `mypy-extensions`, `six`. Большинство из них — зависимости SDK Tinkoff (gRPC/protobuf/pydantic) и Celery (kombu/amqp/billiard).

### Импорты по слоям (фактическое использование)

- **Ext-источник данных:** `from tinkoff.invest import Client, CandleInterval`; `from tinkoff.invest.utils import now` — используются в `services/market_data.py`, `services/graph.py`, `management/commands/add_shares.py`.
- **REST:** `rest_framework.viewsets`, `rest_framework.serializers`, `rest_framework.routers`, `rest_framework.filters`, `django_filters.rest_framework` — в `dashboard/api/v1/**`.
- **Celery:** `from celery import Celery` (`config/celery.py`); декоратор `@app.task` (`dashboard/tasks.py`).
- **Визуализация:** `plotly.graph_objs.Scatter`, `plotly.offline.plot` (`services/graph.py`).
- **Django-стандарт:** `django.views.generic`, `django.contrib.auth`, `django.core.management.base`, `django.urls` — повсеместно в представлениях, формах, URL, командах.
- **Инфраструктурные импорты конфигурации:** `from config.settings import TINKOFF_TOKEN, logger` (например, в `market_data.py`, `graph.py`, `tasks.py`).

### Инфраструктурные зависимости (вне Python)

- **PostgreSQL** и **Redis** поднимаются через `docker-compose.yml`.
- **CDN-ресурсы** в шаблонах: Plotly (`cdn.plot.ly`), jQuery 3.3.1, Popper 1.14.6, Font Awesome 4.7.0, Moment.js 2.23.0, Tempus Dominus Bootstrap 4 5.1.2.

---

## 5. Модель данных: сущности, атрибуты и связи

### 5.1 Сущность `Share` (Акция)

Определена в `dashboard/models.py`. Таблица в БД соответствует имени приложения и модели (`dashboard_share`).

| Поле | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `BigAutoField` | PK, auto | Первичный ключ |
| `figi` | `CharField(max_length=255)` | unique | Идентификатор инструмента FIGI |
| `isin` | `CharField(max_length=255)` | — | Международный идентификационный код ISIN |
| `name` | `CharField(max_length=255)` | verbose_name="Наименование компании" | Название компании/инструмента |
| `ticker` | `CharField(max_length=10)` | unique, verbose_name="Тикер" | Биржевой тикер |
| `currency` | `CharField(max_length=20)` | verbose_name="Валюта" | Валюта котировки |
| `uid` | `CharField(max_length=255)` | unique | Уникальный идентификатор инструмента (Tinkoff) |
| `last_price` | `FloatField` | null=True, blank=True, verbose_name="Текущая цена" | Последняя сохранённая цена |
| `is_trend_high` | `BooleanField` | null=True, blank=True, verbose_name="Растет цена" | Признак роста цены (иначе — падение) |
| `updated_at` | `DateTimeField` | auto_now=True, null=True, blank=True | Время последнего обновления записи |

Метаданные: `verbose_name = "Акция"`, `verbose_name_plural = "Акции"`.

### 5.2 Сущность `User` (Пользователь)

Приложение `user` **не определяет собственную модель**. Файл `user/models.py` лишь реэкспортирует встроенную модель:

```python
from django.contrib.auth import get_user_model
User = get_user_model()
```

Используется стандартная модель `django.contrib.auth.User` со стандартным набором полей (`username`, `email`, `password`, `is_active`, `is_staff`, `is_superuser` и т. д.). Пользователи создаются через `User.objects.create_user(email, email, password)`, то есть e-mail используется и как `username`, и как `email` (см. `user/forms.py`).

### 5.3 Связи

- Явных связей (`ForeignKey`, `OneToOne`, `ManyToMany`) в модели данных **нет**.
- `Share` — самостоятельная сущность без владельца; связь «пользователь ↔ акция» отсутствует.
- С `User` модель `Share` напрямую не связана; аутентификация влияет только на доступность CRUD-операций в интерфейсе (миксин `IsUserAuthenticatedMixin`), но не на принадлежность данных.

### 5.4 Эволюция схемы (миграции)

Схема развивалась последовательно (папка `dashboard/migrations/`):

1. `0001_add_share` — создание модели `Share` (поля `figi`, `isin`, `name`, `ticker`, `currency`).
2. `0002_update_share` — изменения модели.
3. `0003_add_uuid` — добавление поля `uid`.
4. `0004_add_last_price` — добавление `last_price`.
5. `0005_add_verbose_name`, `0006_add_verbose_name` — добавление человекочитаемых названий.
6. `0007_add_updated_at` — добавление `updated_at`.

Итоговая схема соответствует текущему `dashboard/models.py`.

---

## 6. Механизмы обработки пользовательских запросов и взаимодействия с БД

### 6.1 Путь обработки HTTP-запроса

1. **Вход:** запрос принимается WSGI- (`config/wsgi.py`) или ASGI- (`config/asgi.py`) приложением; `DJANGO_SETTINGS_MODULE = "config.settings"`.
2. **Middleware:** стандартный набор Django (`SecurityMiddleware`, `SessionMiddleware`, `CommonMiddleware`, `CsrfMiddleware`, `AuthenticationMiddleware`, `MessageMiddleware`, `XFrameOptionsMiddleware`).
3. **Маршрутизация:** корневой `config/urls.py` распределяет запросы:
   - `/admin/` → админка Django;
   - `/` (корень) → `dashboard.urls` (`app_name="dashboard"`);
   - `/user` → `user.urls` (`app_name="user"`).
4. **Представление:** HTML-запросы обрабатываются generic-классами в `dashboard/views.py` и `user/views.py`; API-запросы (`/api/v1/shares/...`) — `ShareViewSet` в `dashboard/api/v1/views.py`.
5. **Шаблон/сериализация:** для HTML — рендер шаблонов из `templates/<app>/`; для API — сериализация `ShareSerializer`.
6. **Ответ:** HTML-страница (Bootstrap-вёрстка) либо JSON (`LimitOffsetPagination`).

### 6.2 Обработка запросов в HTML-интерфейсе

| Маршрут | URL | Класс | Тип |
|---|---|---|---|
| Главная (список) | `/` | `ShareListView` | `ListView` |
| Детали акции | `/<int:pk>` | `ShareDetailView` | `View` |
| Создание | `/create` | `ShareCreateView` | `CreateView` + миксин |
| Редактирование | `/update/<int:pk>` | `ShareUpdateView` | `UpdateView` + миксин |
| Удаление | `/delete/<int:pk>` | `ShareDeleteView` | `DeleteView` + миксин |
| Логин | `/user/login/` | `AuthView` | `View` |
| Регистрация | `/user/registration/` | `RegistrationView` | `View` |
| Выход | `/user/logout/` | `LogoutView` | `View` |

Особенности:
- `ShareListView` сортирует по `name` и разбивает результат на страницы по 100 записей; в шаблоне реализован блок пагинации.
- `ShareDetailView` — не generic-класс, а базовый `View` со статическим методом `get(request, pk)`; использует `Share.objects.get(id=pk)` (без обработки `DoesNotExist` → возможен `500` при несуществующем `pk`).
- CRUD-представления защищены `IsUserAuthenticatedMixin` (`UserPassesTestMixin`), который при отсутствии авторизации перенаправляет на `dashboard:index`.

### 6.3 Обработка API-запросов (DRF)

- Маршрутизация: `/api/` → `dashboard.api.urls` → `/v1/` → `dashboard.api.v1.urls` → `DefaultRouter` → `/api/v1/shares/`.
- `ShareViewSet` (наследник `ModelViewSet`) автоматически предоставляет полный CRUD: `list`, `retrieve`, `create`, `update`, `partial_update`, `destroy`.
- Настроены бэкенды:
  - `OrderingFilter` (`ordering_fields = ["name", "ticker"]`);
  - `DjangoFilterBackend` с `ShareFilter` (`fields = ("name", "ticker")`);
  - `SearchFilter` (`search_fields = ["$name"]`).
- Пагинация: глобальная `LimitOffsetPagination` со `PAGE_SIZE = 100` (в `settings.REST_FRAMEWORK`).
- Сериализатор `ShareSerializer` отдаёт поля `id, figi, isin, name, ticker, currency, last_price, is_trend_high, updated_at`.

### 6.4 Взаимодействие с БД (Django ORM)

Все операции с БД выполняются через Django ORM (SQL генерируется автоматически, драйвер — `psycopg2`, СУБД — PostgreSQL):

- **Чтение списка:** `Share.objects.all()` (в `ListView` — с сортировкой и пагинацией).
- **Чтение одной записи:** `Share.objects.get(id=pk)` (детальная страница).
- **Создание/обновление через формы:** `CreateView`/`UpdateView` вызывают `ShareModelForm.save()` → ORM `INSERT`/`UPDATE`.
- **Удаление:** `DeleteView` → ORM `DELETE`.
- **Массовое обновление цен (Celery):** `Share.objects.all()` в цикле + `Share.objects.filter(id=share.id).update(last_price=..., is_trend_high=...)` — точечные `UPDATE` без вызова `save()`.
- **Первичное наполнение:** `Share.objects.get_or_create(figi=..., ...)` в команде `add_shares`.
- **API CRUD:** `ModelViewSet` использует `queryset = Share.objects.all()` и сериализатор для чтения/записи.

### 6.5 Управление сессиями и аутентификацией

- Аутентификация — **session-based** (стандартный механизм Django): `authenticate()` → `login()` устанавливает сессионную cookie; `logout()` её очищает.
- E-mail используется в качестве логина: при входе `authenticate(username=email.lower(), ...)`, при регистрации `create_user(email, email, password)`.
- Формы `RegistrationForm` (поля `email`, `password1`, `password2`) и `AuthForm` (`email`, `password`) реализуют серверную валидацию: совпадение паролей и уникальность e-mail.

### 6.6 Фоновая обработка запросов к внешнему API

- **Планировщик:** Celery Beat по расписанию (`config/celery.py`, `beat_schedule`) запускает задачу `dashboard.tasks.update_last_price`.
- **Выполнение:** Celery Worker (`celery -A config worker`) выполняет задачу: для каждой акции синхронно вызывается Tinkoff API (`get_last_prices`) внутри контекстного менеджера `Client(...)`, результат сравнивается с текущей ценой и записывается в БД.
- **Обработка ошибок:** ошибки получения/сравнения цен перехватываются и логируются через логгер `main` (`config.settings.logger`), запись в консоль и файл `app.logs`; при ошибке сравнения `is_trend_high` по умолчанию выставляется `True`.
- **Дополнение к интеграции:** график исторических котировок строится синхронно в момент запроса детальной страницы (`services/graph.py`), то есть зависит от доступности Tinkoff API в реальном времени.

### 6.7 Замечания по конфигурации (влияют на механику запросов)

- `SECRET_KEY` и `TINKOFF_TOKEN` в `config/settings.py` пустые — значения должны быть подставлены перед запуском; при пустом токене обращения к Tinkoff API не будут работать.
- `DEBUG = True`, `ALLOWED_HOSTS = []` — конфигурация ориентирована на локальную разработку.
- Расписание Celery названо `add-every-5-min`, но фактический интервал — `10.0` секунд (несоответствие имени и значения).
- Активная СУБД — PostgreSQL; конфигурация SQLite присутствует, но закомментирована.

---

## 7. Функциональные требования и дефекты реализации

> В разделе описаны **фактически реализованные** возможности (а не желаемые), основные сценарии работы пользователя, бизнес-правила и выявленные дефекты кода.

### 7.1 Фактические функциональные возможности (реализовано в коде)

1. **Просмотр списка акций** — страница `/` (`ShareListView`) выводит таблицу акций с полями «Тикер», «Название», «ISIN», «Текущая цена»; сортировка по `name`, пагинация по 100 записей.
2. **Цветовая индикация тренда цены** — в списке цена подсвечивается зелёным, если `is_trend_high` истинно, и розовым — в остальных случаях (`list.html`).
3. **Просмотр детальной карточки акции** — страница `/<pk>` (`ShareDetailView`) с наименованием, текущей ценой, валютой и временем последнего обновления (`updated_at`).
4. **Построение графика исторических котировок** — на карточке отображается линейный график дневных цен закрытия за последние 180 дней (`services/graph.py`, Plotly).
5. **Создание акции через веб-форму** — `/create` (`ShareCreateView`) для авторизованных пользователей, форма `ShareModelForm`.
6. **Редактирование акции через веб-форму** — `/update/<pk>` (`ShareUpdateView`) для авторизованных пользователей.
7. **Удаление акции** — `/delete/<pk>` (`ShareDeleteView`) с экраном подтверждения, для авторизованных пользователей.
8. **Регистрация пользователя** — `/user/registration/` (`RegistrationView`), поля «email», «пароль», «повтор пароля»; после успешной регистрации выполняется автоматический вход.
9. **Авторизация пользователя** — `/user/login/` (`AuthView`) по e-mail и паролю (сессионная аутентификация).
10. **Выход пользователя** — `/user/logout/` (`LogoutView`), очистка сессии и переход на главную.
11. **Первичная загрузка справочника акций из Tinkoff Invest API** — management-команда `python manage.py add_shares` (`Share.objects.get_or_create`).
12. **Автоматическое обновление текущих цен** — фоновая Celery-задача `update_last_price` (`dashboard/tasks.py`) по расписанию Celery Beat.
13. **Автоматическое определение признака роста/падения цены** — задача сравнивает новую цену с сохранённой и записывает `is_trend_high`.
14. **REST API для акций (v1)** — `/api/v1/shares/` (`ShareViewSet`, `ModelViewSet`) с полным CRUD (`list`, `retrieve`, `create`, `update`, `partial_update`, `destroy`).
15. **Фильтрация, поиск и сортировка в API** — `ShareFilter` по `name`/`ticker`, `SearchFilter` по `name`, `OrderingFilter` по `name`/`ticker`.
16. **Пагинация API** — глобальная `LimitOffsetPagination` со `PAGE_SIZE = 100`.
17. **Администрирование модели `Share`** — регистрация в Django-админке (`admin.py`): список, поиск и набор редактируемых полей.
18. **Серверная валидация форм регистрации** — совпадение паролей и проверка уникальности e-mail.
19. **Логирование** — логгер `main` пишет в консоль и в файл `app.logs` (используется в задаче обновления цен и при получении данных).
20. **Автотесты REST API** — `dashboard/tests.py` (`APITestCase`) покрывает список, детали, создание, обновление и удаление акций.

### 7.2 Основные сценарии взаимодействия пользователя

**Сценарий 1. Просмотр списка акций (неавторизованный/авторизованный пользователь).**
Пользователь открывает `/` → `ShareListView` выполняет запрос к БД (сортировка по `name`, пагинация) → рендер `list.html`. Управляющие кнопки («Добавить», «Редактировать», «Удалить») видны только авторизованным. Переход по тикеру ведёт на детальную страницу.

**Сценарий 2. Просмотр карточки с графиком.**
Клик по тикеру → `GET /<pk>` → `ShareDetailView.get()` получает акцию из БД, вызывает `get_graph(share)`, который синхронно обращается к Tinkoff API за дневными свечами за 180 дней и возвращает HTML-разметку Plotly → рендер `detail.html` (график вставляется с `autoescape off`).

**Сценарий 3. Добавление акции через форму.**
Авторизованный пользователь нажимает «Добавить» → `GET /create` (пустая форма) → `POST /create` с данными → `ShareCreateView` сохраняет запись → редирект на главную. Неавторизованный пользователь перенаправляется на главную (`IsUserAuthenticatedMixin`).

**Сценарий 4. Редактирование акции через форму.**
Клик «Редактировать» → `GET /update/<pk>` (форма с текущими данными) → `POST /update/<pk>` → `ShareUpdateView` (`fields = "__all__"`) сохраняет изменения → редирект на главную.

**Сценарий 5. Удаление акции.**
Клик «Удалить» → `GET /delete/<pk>` (экран подтверждения с названием акции) → `POST /delete/<pk>` → `ShareDeleteView` удаляет запись → редирект на главную.

**Сценарий 6. Регистрация.**
`GET /user/registration/` → ввод e-mail и пароля дважды → `POST` → `RegistrationForm.is_valid()` проверяет совпадение паролей и уникальность e-mail → `form.save()` создаёт пользователя (`create_user(email, email, password)`) → автоматический `login()` → редирект на главную. При ошибке форма возвращается с сообщением.

**Сценарий 7. Авторизация.**
`GET /user/login/` → ввод e-mail и пароля → `POST` → `AuthView` вызывает `authenticate(username=email.lower(), password=...)` → при успехе `login()` и редирект на главную; иначе — сообщение «Неверный логин или пароль».

**Сценарий 8. Выход.**
`GET /user/logout/` → `logout(request)` → редирект на главную.

**Сценарий 9. Работа через REST API.**
Внешний клиент отправляет запросы на `/api/v1/shares/` — получение списка (с фильтрами/поиском/сортировкой), деталей, создание, изменение и удаление акций. Аутентификация в API не требуется.

**Сценарий 10. Фоновое обновление цен (без участия пользователя).**
Celery Beat по расписанию запускает `update_last_price` → Celery Worker перебирает все акции, для каждой вызывает Tinkoff API, сравнивает цену, вычисляет `is_trend_high` и обновляет запись в БД. Пользователь видит результат в списке и карточке.

### 7.3 Бизнес-правила, проверки и ограничения

1. **Уникальность ключевых полей акции** — `figi`, `ticker`, `uid` объявлены `unique=True` (на уровне БД и модели).
2. **Обязательность полей акции** — `figi`, `isin`, `name`, `ticker`, `currency`, `uid` не допускают пустых значений; `last_price`, `is_trend_high`, `updated_at` — допускают `NULL`/пусто.
3. **Ограничение длины строк** — `ticker` ≤ 10 символов, `currency` ≤ 20, `figi`/`isin`/`name`/`uid` ≤ 255.
4. **Совпадение паролей при регистрации** — `RegistrationForm.clean()` проверяет `password1 == password2`, иначе `ValidationError` («Введенные пароли не совпадают»).
5. **Уникальность e-mail при регистрации** — проверка `User.objects.filter(email=email)`; при наличии — ошибка «Данный e-mail уже зарегистрирован!».
6. **Автозаполнение `updated_at`** — поле `DateTimeField(auto_now=True)` автоматически обновляется при сохранении через ORM (`save()`).
7. **Разграничение доступа к веб-CRUD** — создание, редактирование и удаление акций доступны только аутентифицированным пользователям (`IsUserAuthenticatedMixin`, наследник `UserPassesTestMixin`); иначе — редирект на главную.
8. **Отображение элементов управления по роли** — кнопки «Добавить»/«Редактировать»/«Удалить» рендерятся в шаблоне только при `user.is_authenticated`.
9. **Проверка паролей Django** — настроены стандартные `AUTH_PASSWORD_VALIDATORS`, но применяются только через стандартные механизмы Django (см. замечание в дефектах).
10. **Пагинация** — список HTML и API ограничены 100 записями на страницу.
11. **Сортировка по умолчанию** — HTML-список сортируется по `name`; API — по параметрам `ordering` (`name`, `ticker`).
12. **Направление тренда** — `is_trend_high = True`, если новая цена не меньше сохранённой (`share.last_price > last_price` — ложь), иначе `False`; при ошибке сравнения — `True`.
13. **Фильтрация API** — доступна по полям `name` и `ticker`; полнотекстовый поиск — по `name`.
14. **Первичная загрузка без дублей** — команда `add_shares` использует `get_or_create` по `figi`.

### 7.4 Выявленные дефекты реализации, неоднозначности и противоречия

**1. REST API полностью открыт (критично).**
`ShareViewSet` не задаёт `permission_classes` и не использует `IsAuthenticated`; любой неавторизованный клиент может создавать, изменять и удалять акции через `/api/v1/shares/`. Это противоречит веб-интерфейсу, где CRUD защищён авторизацией.

**2. Отсутствие разграничения владения данными.**
Модель `Share` не связана с `User`. Любой авторизованный пользователь может редактировать/удалять **любые** акции; персональных данных и изоляции нет.

**3. `ShareDetailView` не обрабатывает отсутствующую запись.**
`Share.objects.get(id=pk)` вызывается без `try/except` и без `get_object_or_404` → при несуществующем `pk` возникает `Share.DoesNotExist` и ответ `500` вместо `404`.

**4. `AuthView` не выполняет валидацию формы.**
В `post()` форма не проверяется через `is_valid()`; данные читаются напрямую из `form.data["email"]`/`form.data["password"]` → при отсутствии поля возникает `KeyError` (500), а некорректный e-mail не отлавливается формой.

**5. Несогласованность регистра и e-mail как логина.**
При регистрации e-mail сохраняется «как введён» (`create_user(email, email, password)`), а при входе применяется `email.lower()` (`authenticate(username=email.lower(), ...)`). Если пользователь зарегистрировался с заглавными буквами, вход может не сработать — противоречие между регистрацией и авторизацией.

**6. Пароли не проходят валидаторы Django.**
Регистрация использует собственную форму `RegistrationForm` и `create_user()` без вызова `validate_password()`, поэтому настроенные `AUTH_PASSWORD_VALIDATORS` (минимальная длина, распространённые пароли и т. д.) фактически не применяются.

**7. `RegistrationView` может упасть на выводе ошибки.**
Обращение `form.errors["__all__"].data[0].message` предполагает ошибку уровня формы; при ошибке конкретного поля (например, «email обязателен») ключа `__all__` может не быть → `KeyError` вместо показа ошибки.

**8. `Settings`: пустые секреты и токен.**
`SECRET_KEY = ""` и `TINKOFF_TOKEN = ""` — приложение неработоспособно без ручной подстановки значений; обращения к Tinkoff API при пустом токене завершатся ошибкой.

**9. Несоответствие имени и интервала расписания Celery.**
Ключ расписания `add-every-5-min` задаёт `schedule = 10.0` (секунды). Имя противоречит значению; интервал 10 секунд по всем акциям создаёт высокую нагрузку на Tinkoff API (вероятны ограничения по частоте запросов).

**10. Неэффективная работа с внешним API в задаче.**
`get_last_data()` открывает новый `Client(TINKOFF_TOKEN)` (новое соединение) на **каждую** акцию внутри цикла, а не один клиент на весь проход — избыточные подключения и замедление.

**11. `None` при сравнении цены в задаче.**
При первом запуске (когда `last_price is None`) выражение `share.last_price > last_price` вызывает `TypeError`, который перехватывается внутренним `except`: ошибка логируется, а `is_trend_high` принудительно становится `True`. Это искажает тренд и засоряет лог.

**12. `updated_at` не обновляется при обновлении цены.**
Задача использует `Share.objects.filter(...).update(...)`, который **не** вызывает `auto_now`. В результате время последнего обновления цены, отображаемое на карточке, остаётся устаревшим.

**13. `ShareModelForm` открывает все поля (`fields = "__all__"`).**
Через веб-форму можно вручную менять технические и вычисляемые поля (`figi`, `uid`, `last_price`, `is_trend_high`, `updated_at`), что противоречит их «служебному» назначению и позволяет вносить несогласованные данные.

**14. Неоднозначность состояния `is_trend_high = NULL`.**
Значение по умолчанию `NULL` в шаблоне трактуется как ложное (розовая подсветка «падение»), хотя фактический тренд ещё не определён — неверная трактовка неинициализированного состояния.

**15. Несогласованность версий Bootstrap.**
Подключены `bootstrap.min.css` и `crispy-bootstrap3` (Bootstrap 3), но разметка шаблонов и ресурсы используют классы/библиотеки Bootstrap 4–5 (`col-md-3`, `form-control`, Tempus Dominus Bootstrap 4). Возможны визуальные дефекты.

**16. `logout` по GET.**
`LogoutView` выполняет выход при `GET`-запросе (без CSRF-токена), что допускает нежелательный выход по внешней ссылке.

**17. `AuthView.get` передаёт класс формы вместо экземпляра.**
В контекст передаётся `{"form": AuthForm}` (класс, а не инстанс); при определённых условиях отрисовка формы может вести себя некорректно/непредсказуемо.

**18. Вероятно неработоспособные тесты обновления.**
`test_share_update` отправляет `PUT` без обязательного уникального поля `uid`; `ModelSerializer` считает `uid` обязательным, поэтому ожидаемый `200` может фактически не достигаться (возврат `400`). Тест отражает противоречие между требованиями сериализатора и данными теста.

**19. Тестовое покрытие одностороннее.**
Автотесты покрывают только REST API и не проверяют HTML-представления, формы, авторизацию/регистрацию и Celery-задачу.

**20. Конфигурация ориентирована на разработку.**
`DEBUG = True`, `ALLOWED_HOSTS = []`, БД `localhost` с паролем по умолчанию, пароль и секреты в открытом виде в `settings.py` — не готово к промышленной эксплуатации.

**21. Мелочи и «следы» переименования проекта.**
`manage.py` содержит строку «DjangoOld's command-line utility», миграции сгенерированы «DjangoOld 4.1.7»; лог-файл назван `app.logs` (расширение не `.log`); ключ `CELERY_BEAT_SCHEDULE` задан в коде (`celery.py`), а не в настройках.

---

## 8. Разработка новой функциональности (Виртуальный портфель)

> В разделе описана функциональность, добавленная поверх базовой версии приложения: виртуальный портфель пользователя и генерация моковых исторических данных для графика. Приводятся требования, изменения архитектуры и модели данных, новые маршруты/представления/шаблоны, а также подтверждение исправления дефекта с `tinkoff-investments` и отсутствия регрессий.

### 8.1 Функциональные требования

#### 8.1.1 Требования к разделу портфеля

| № | Требование | Реализация |
|---|---|---|
| FR-P1 | Пользователь имеет персональный портфель, создаваемый автоматически при первом обращении к операциям | Модель `Portfolio` + `Portfolio.objects.get_or_create(user=...)` |
| FR-P2 | Портфель хранит позиции: акция, количество, цена покупки, дата | Модель `PortfolioPosition` (`share`, `quantity`, `purchase_price`, `purchased_at`) |
| FR-P3 | Покупка акции с заданным количеством | `ShareTradeView` (`action="buy"`) → `buy_share()` |
| FR-P4 | Продажа акции с заданным количеством | `ShareTradeView` (`action="sell"`) → `sell_share()` |
| FR-P5 | Форма и кнопки «Купить»/«Продать» на странице акции | `TradeForm` + блок в `dashboard/detail.html` |
| FR-P6 | Отдельная страница `/portfolio/` со составом портфеля | `PortfolioView` + `dashboard/portfolio.html` |
| FR-P7 | Расчёт общей стоимости портфеля | `Portfolio.total_value` (сумма `current_value` позиций) |
| FR-P8 | Расчёт прибыли/убытка (P&L) — абсолютного и в процентах | `PortfolioPosition.profit`, `PortfolioPosition.profit_percent`, `Portfolio.total_profit` |
| FR-P9 | Ссылка «Мой портфель» в навигационном меню | `dashboard/templates/dashboard/base.html` (шапка и футер) |
| FR-P10 | Операции с портфелем доступны только авторизованным пользователям | `ShareTradeView` и `PortfolioView` наследуют `IsUserAuthenticatedMixin` |
| FR-P11 | При покупке пересчитывается средняя цена покупки (взвешенная) | `buy_share()`: `(старая_стоимость + новая_стоимость) / новое_количество` |
| FR-P12 | Продажа не может превысить остаток; при обнулении позиция удаляется | `sell_share()` с проверкой `quantity > position.quantity` |
| FR-P13 | Пользователь видит подтверждение/ошибку операции | Flash-сообщения Django (`messages`) и их вывод в `base.html` |
| FR-P14 | Портфель изолирован по пользователю | `Portfolio.user` — `OneToOneField` к `AUTH_USER_MODEL`; выборки фильтруются по `request.user` |

#### 8.1.2 Требования к генерации моковых исторических данных

| № | Требование | Реализация |
|---|---|---|
| FR-G1 | График на карточке акции отображается **всегда**, независимо от наличия `tinkoff-investments` | `services/graph.py`: `get_graph()` возвращает разметку Plotly при любых условиях |
| FR-G2 | При отсутствии SDK генерируется синтетический (моковый) ряд цен | `_mock_candles(share)` |
| FR-G3 | Ряд должен быть детерминирован для акции (график не «прыгает» при перезагрузке) | Сид генератора: `sum(ord(c) for c in (share.figi or ticker or pk))` |
| FR-G4 | Ряд должен быть правдоподобным (~180 дней, будни, небольшой тренд и волатильность, без плоской линии) | Логарифмическое случайное блуждание с мягким возвратом к линейному тренду; дневная волатильность 1–2.8 %, редкие «новостные» всплески, пропуск субботы/воскресенья |
| FR-G5 | Точка старта ряда привязана к текущей цене акции | Начальная цена = `share.last_price` (иначе `100.0`) |
| FR-G6 | При наличии SDK и доступности API используются реальные свечи; при ошибке — плавная деградация к моковым данным | `_tinkoff_candles()` в `try/except`, fallback при ошибке или пустом ответе |
| FR-G7 | График встраивается в страницу без повторной загрузки библиотеки Plotly | `plot(..., include_plotlyjs=False)` (plotly.js подключён в `base.html` через CDN) |

### 8.2 Изменения в архитектуре и модели данных

#### 8.2.1 Архитектурные изменения

Добавлена прикладная функция «виртуальный портфель», встроенная в существующий слой `dashboard` (без введения нового Django-приложения):

```
Пользователь (HTML)
        │
        ▼
dashboard/urls.py
  ├── /portfolio/        → PortfolioView        (GET)      ──┐
  └── /trade/<pk>        → ShareTradeView       (POST)     ──┤
                                                             │
dashboard/views.py                                           │
  ├── buy_share()   ── PortfolioPosition (средняя цена)      │
  ├── sell_share()  ── PortfolioPosition (проверка остатка)  │
  └── PortfolioView ── Portfolio.total_* (агрегаты P&L)  ◄───┘
                                                             │
dashboard/models.py                                          │
  ├── Portfolio          (OneToOne → User)                   │
  └── PortfolioPosition  (FK → Portfolio, FK → Share)  ◄─────┘
                             │
                             ▼
                     ORM Django → БД
```

Ключевые архитектурные решения:

- функциональность размещена в приложении `dashboard` (единая предметная область «инвестиции»), новых приложений не создавалось;
- расчёты P&L инкапсулированы в `@property` моделей, поэтому представления и шаблоны оперируют готовыми значениями;
- операции покупки/продажи вынесены в отдельные функции `buy_share()` / `sell_share()`, вызываемые из одного представления `ShareTradeView` (единая точка торговли для страницы акции и страницы портфеля);
- визуализация (`services/graph.py`) переведена в режим «всегда доступна»: наличие внешнего SDK перестало быть обязательным условием отображения графика.

#### 8.2.2 Модель `Portfolio`

Определена в `dashboard/models.py`. Таблица — `dashboard_portfolio`.

| Поле | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `BigAutoField` | PK, auto | Первичный ключ |
| `user` | `OneToOneField(AUTH_USER_MODEL)` | CASCADE, related_name="portfolio", verbose_name="Пользователь" | Владелец портфеля (один портфель на пользователя) |
| `created_at` | `DateTimeField` | auto_now_add=True, verbose_name="Дата создания" | Дата создания портфеля |

Вычисляемые свойства (не сохраняются в БД):

| Свойство | Формула | Назначение |
|---|---|---|
| `total_value` | `Σ position.current_value` | Текущая рыночная стоимость портфеля |
| `total_cost` | `Σ position.cost` | Суммарные вложения |
| `total_profit` | `total_value − total_cost` | Итоговый P&L |

#### 8.2.3 Модель `PortfolioPosition`

Определена в `dashboard/models.py`. Таблица — `dashboard_portfolioposition`.

| Поле | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | `BigAutoField` | PK, auto | Первичный ключ |
| `portfolio` | `ForeignKey(Portfolio)` | CASCADE, related_name="positions", verbose_name="Портфель" | Портфель-владелец позиции |
| `share` | `ForeignKey(Share)` | CASCADE, related_name="positions", verbose_name="Акция" | Инструмент |
| `quantity` | `PositiveIntegerField` | default=0, verbose_name="Количество" | Количество акций в позиции |
| `purchase_price` | `FloatField` | default=0.0, verbose_name="Средняя цена покупки" | Средневзвешенная цена покупки |
| `purchased_at` | `DateTimeField` | default=timezone.now, verbose_name="Дата покупки" | Дата последней покупки |

Метаданные: `unique_together = ("portfolio", "share")` (одна позиция на акцию в портфеле), `ordering = ["share__name"]`, `verbose_name = "Позиция портфеля"`.

Вычисляемые свойства (не сохраняются в БД):

| Свойство | Формула | Назначение |
|---|---|---|
| `current_price` | `share.last_price или 0.0` | Текущая цена акции |
| `cost` | `quantity × purchase_price` | Стоимость по цене покупки (вложения) |
| `current_value` | `quantity × current_price` | Текущая рыночная стоимость позиции |
| `profit` | `current_value − cost` | P&L позиции (абсолютный) |
| `profit_percent` | `profit / cost × 100` (0 при `cost = 0`) | P&L позиции в процентах |

#### 8.2.4 Связи модели данных (обновление к разделу 5.3)

Ранее (раздел 5.3) модель данных не содержала связей. После доработки:

```
User (django.contrib.auth)
  └── 1:1 ── Portfolio
                 └── 1:N ── PortfolioPosition
                                  └── N:1 ── Share
```

- `User` **1:1** `Portfolio` — у каждого пользователя не более одного портфеля;
- `Portfolio` **1:N** `PortfolioPosition` — состав портфеля;
- `PortfolioPosition` **N:1** `Share` — позиция ссылается на акцию из справочника.

Модель `Share` по-прежнему не содержит ссылки на владельца: портфели разных пользователей разделяются через `Portfolio.user`.

#### 8.2.5 Эволюция схемы (дополнение к разделу 5.4)

7. `0008_portfolio_portfolioposition` — создание моделей `Portfolio` и `PortfolioPosition`. Зависимости: `dashboard.0007_add_updated_at` и `swappable_dependency(AUTH_USER_MODEL)`.

Итоговое количество миграций приложения `dashboard` — **8**; все применены.

### 8.3 Новые маршруты, представления и шаблоны

#### 8.3.1 Маршруты (URLs)

Добавлены в `dashboard/urls.py` (`app_name = "dashboard"`):

| URL | Имя маршрута | Представление | Метод | Доступ |
|---|---|---|---|---|
| `/portfolio/` | `dashboard:portfolio` | `PortfolioView` | GET | только авторизованные |
| `/trade/<int:pk>` | `dashboard:trade` | `ShareTradeView` | POST | только авторизованные |

Порядок объявления изменён так, чтобы статические префиксы (`portfolio/`, `trade/`, `create`, `update/`, `delete/`) не перехватывались динамическим `path("<int:pk>")`; маршрут деталей акции оставлен последним перед вложенными URL API.

#### 8.3.2 Представления (views) — `dashboard/views.py`

| Компонент | Тип | Назначение |
|---|---|---|
| `ShareDetailView` (обновлён) | `View` | Дополнительно передаёт в шаблон `trade_form` (`TradeForm()`) и `position` — текущую позицию пользователя по этой акции (или `None`) |
| `ShareTradeView` (новое) | `View` | Обрабатывает POST покупки/продажи: читает `action` (`buy`/`sell`), валидирует `TradeForm`, вызывает `buy_share()`/`sell_share()`, формирует flash-сообщение, возвращает редирект на `next` (по умолчанию — на страницу акции) |
| `PortfolioView` (новое) | `View` | GET `/portfolio/`: получает/создаёт портфель пользователя, выбирает позиции с `select_related("share")`, рендерит `dashboard/portfolio.html` |
| `buy_share(portfolio, share, quantity, price)` | функция | `get_or_create` позиции, взвешенный пересчёт `purchase_price`, увеличение `quantity`, обновление `purchased_at` |
| `sell_share(portfolio, share, quantity)` | функция | Возвращает `(успех, текст_ошибки)`; проверяет наличие позиции и достаточность остатка, уменьшает `quantity`, удаляет позицию при нуле |

Проверки в `ShareTradeView`: обязательность целого количества ≥ 1, известность текущей цены при покупке (`share.last_price is not None`), достаточность остатка при продаже.

#### 8.3.3 Формы — `dashboard/forms.py`

| Форма | Поля | Назначение |
|---|---|---|
| `TradeForm` (новое) | `quantity` (`IntegerField`, `min_value=1`, `initial=1`, виджет `NumberInput(class="form-control")`) | Ввод количества для покупки/продажи |

`ShareModelForm` оставлена без изменений.

#### 8.3.4 Шаблоны

| Шаблон | Статус | Содержание |
|---|---|---|
| `dashboard/templates/dashboard/portfolio.html` | новый | `GET /portfolio/`: таблица состава (тикер, название, количество, средняя цена покупки, текущая цена, вложено, текущая стоимость, P&L, P&L %), итоговая строка `<tfoot>`, карточка с общей стоимостью/вложениями/P&L, формы «Купить»/«Продать» в каждой строке, состояние «Портфель пуст» |
| `dashboard/templates/dashboard/detail.html` | обновлён | Блок «Купить / Продать»: информация о текущей позиции, `TradeForm`, кнопки `action=buy` / `action=sell`; для неавторизованных — ссылка на вход |
| `dashboard/templates/dashboard/base.html` | обновлён | Ссылка **«Мой портфель»** в шапке (`<header>`) и в футере (только для `user.is_authenticated`); вывод flash-сообщений (`messages`) с разделением на `alert-success` / `alert-danger` |

### 8.4 Подтверждение исправления дефекта с `tinkoff-investments` и отсутствия регрессий

#### 8.4.1 Суть дефекта и его исправление

**Было:** при отсутствии пакета `tinkoff-investments` функция `services.graph.get_graph()` возвращала вместо графика текстовую заглушку
«*Исторические данные недоступны: не установлен пакет `tinkoff-investments`.*» — то есть карточка акции теряла основной функционал.

**Стало:**

- добавлена функция `_mock_candles(share)`, генерирующая синтетический ряд дневных цен за ~180 дней: логарифмическое случайное блуждание с мягким возвратом к линейному тренду, дневная волатильность 1–2.8 %, редкие «новостные» всплески, детерминированный сид от `figi`/`ticker`, стартовая цена = `share.last_price` или `100.0`;
- `get_graph()` использует реальные свечи Tinkoff только при наличии SDK и успешном ответе API; в остальных случаях (SDK отсутствует, сетевая/иная ошибка, пустой ответ) возвращает график по моковым данным;
- **дополнительно устранён скрытый дефект:** вызов `plotly.offline.plot(..., show_link=..., link_text=...)` несовместим с Plotly 7.x (`TypeError: plot() got an unexpected keyword argument 'show_link'`) — аргументы заменены на `include_plotlyjs=False` (plotly.js подключается в `base.html` через CDN); таким образом, график не построился бы даже при установленном SDK.

#### 8.4.2 Матрица проверок (результаты прогонов)

Проверки выполнялись через Django test client и реальные HTTP-запросы к запущенному серверу.

| Проверка | Ожидание | Результат |
|---|---|---|
| Присутствие мокового графика при отсутствии SDK | график отрендерен | ✅ на странице акции есть `plotly-graph-div` |
| Отсутствие текста-заглушки | нет строки «не установлен пакет» | ✅ строка отсутствует |
| Сообщение в логе о режиме | warning о синтетическом ряде | ✅ `Используется синтетический ряд исторических цен` |
| Регистрация пользователя | вход выполнен | ✅ `302`, сессия установлена |
| Покупка 10 шт. | позиция создана | ✅ количество = 10, средняя цена = 100.5 |
| Страница `/portfolio/` | 200, агрегаты посчитаны | ✅ вложено 1005.00 · стоимость 1005.00 · P&L 0.00 |
| Продажа 4 шт. | остаток уменьшен | ✅ осталось 6 |
| Продажа 999 шт. | отказано | ✅ остаток сохранён (6), показана ошибка |
| Полная продажа (6 шт.) | позиция удалена | ✅ записи `PortfolioPosition` нет |
| Ссылка «Мой портфель» в навигации | присутствует | ✅ `href="/portfolio/"` в шапке |
| `/` (список акций) | 200 | ✅ 200 |
| `/user/login/` | 200 | ✅ 200 |
| `/<pk>` (карточка) | 200 | ✅ 200 |
| `/portfolio/` без авторизации | редирект | ✅ 302 → главная |
| `/999999` (несуществующая акция) | 404 | ✅ 404 (без регрессии `get_object_or_404`) |
| `/api/v1/shares/` | 200 | ✅ 200 |

**Регрессии не выявлены:** ранее исправленные дефекты (404 вместо 500 в `ShareDetailView`, валидация форм регистрации/входа, URL `user/` со слэшем, обновление цен в Celery) сохраняют корректное поведение.

### 8.5 Готовность проекта: миграции и запуск

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py showmigrations
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

| Команда | Результат |
|---|---|
| `manage.py check` | `System check identified no issues (0 silenced).` |
| `manage.py showmigrations` | все миграции отмечены `[X]`, включая `dashboard.0008_portfolio_portfolioposition` |
| `manage.py makemigrations --check --dry-run` | `No changes detected` — модель данных синхронизирована с миграциями |
| `manage.py migrate` | `Applying dashboard.0008_portfolio_portfolioposition... OK` |
| `manage.py runserver` | сервер запущен на `http://127.0.0.1:8000`, страницы отвечают корректно |

**Вывод:** все миграции БД применены, схема актуальна, проект запускается и работает без ошибок.

---

## Приложение. Сводная карта ключевых файлов

| Файл | Роль |
|---|---|
| `config/settings.py` | Настройки проекта, БД, DRF, Celery, логирование, токен Tinkoff |
| `config/urls.py` | Корневая маршрутизация |
| `config/celery.py` | Инициализация Celery и расписание Beat |
| `dashboard/models.py` | Модели `Share`, `Portfolio`, `PortfolioPosition` |
| `dashboard/views.py` | HTML-контроллеры акций, портфеля и торговли (`ShareTradeView`, `PortfolioView`) |
| `dashboard/forms.py` | Формы `ShareModelForm`, `TradeForm` |
| `dashboard/templates/dashboard/portfolio.html` | Страница «Мой портфель» (состав, стоимость, P&L) |
| `dashboard/tasks.py` | Celery-задача обновления цен |
| `dashboard/services/market_data.py` | Получение последней цены (Tinkoff) |
| `dashboard/services/graph.py` | Построение графика котировок (Plotly) |
| `dashboard/management/commands/add_shares.py` | Загрузка списка акций |
| `dashboard/api/v1/{router,views,serializer,urls}.py` | REST API v1 |
| `user/forms.py`, `user/views.py`, `user/urls.py` | Аутентификация и регистрация |
| `docker-compose.yml` | PostgreSQL + Redis |

---

## 9. Итоги разработки и новые фичи

Раздел подводит итог доработкам, выполненным поверх исходной версии проекта: от устранения блокирующего дефекта визуализации до полноценной новой функции «Виртуальный инвестиционный портфель» и наведения порядка в вёрстке.

### 9.1 Исправление дефекта с историческими данными (моковые данные для Plotly)

| Аспект | Было | Стало |
|---|---|---|
| Отображение графика | текстовая заглушка «Исторические данные недоступны: не установлен пакет `tinkoff-investments`» | график Plotly строится **всегда** |
| Источник данных | только Tinkoff Invest SDK (обязательное условие) | реальные свечи при наличии SDK, иначе — синтетический ряд (`_mock_candles`) |
| Характер ряда | плоская линия (SDK брал `candle.close.units` без наночастиц; при моке — фиксированное значение) | правдоподобный ряд: логарифмическое случайное блуждание с трендом, волатильностью 1–2.8 % и редкими всплесками |
| Детерминированность | — | ряд стабилен для акции (сид от `figi`/`ticker`), график не «прыгает» при перезагрузке |
| Совместимость с библиотекой | `plotly.offline.plot(..., show_link=..., link_text=...)` падал на Plotly 7.x | аргументы заменены на `include_plotlyjs=False` (библиотека подключается через CDN) |
| Версия plotly.js на странице | `plotly-latest.min.js` → фактически v1.58.5 | `plotly-3.0.1.min.js` — соответствует `plotly` (Python) 7.x |

Результат: карточка акции сохраняет основной функционал при любой конфигурации окружения — установлен SDK или нет, доступен API или нет.

### 9.2 Реализация функционала «Виртуальный инвестиционный портфель»

Полностью новая прикладная функция, охватывающая модель данных, серверную логику и интерфейс.

**Модели** (`dashboard/models.py`):

- `Portfolio` — портфель пользователя (`OneToOne` к `AUTH_USER_MODEL`), агрегаты `total_cost`, `total_value`, `total_profit`;
- `PortfolioPosition` — позиция портфеля (`share`, `quantity`, `purchase_price`, `purchased_at`), вычисляемые `cost`, `current_value`, `profit`, `profit_percent`; ограничение `unique_together = ("portfolio", "share")`.

**Представления** (`dashboard/views.py`):

- `ShareTradeView` — единая точка торговли (POST `buy`/`sell`) для страницы акции и страницы портфеля;
- `PortfolioView` — `GET /portfolio/` со составом портфеля, общей стоимостью и P&L;
- функции `buy_share()` (взвешенный пересчёт средней цены покупки) и `sell_share()` (проверка остатка, удаление позиции при обнулении);
- доступ только для авторизованных (`IsUserAuthenticatedMixin`).

**Интерфейс покупки/продажи и просмотра**:

- `TradeForm` — ввод количества (целое ≥ 1);
- блок «Купить / Продать» на карточке акции с текущей позицией пользователя;
- страница `/portfolio/` `dashboard/templates/dashboard/portfolio.html` — таблица позиций, итоговая строка, карточка «Общая стоимость / вложено / P&L», формы торговли в каждой строке;
- ссылка **«Мой портфель»** в шапке и футере;
- flash-сообщения об успехе/ошибке операции.

**Схема БД**: миграция `0008_portfolio_portfolioposition` (итого 8 миграций `dashboard`, все применены).

### 9.3 Устранение визуальных дефектов и оптимизация вёрстки

| Дефект | Причина | Исправление |
|---|---|---|
| Текст шаблонного комментария вверху страницы | Django-комментарий `{# ... #}` был записан в две строки и не распознавался как комментарий, а выводился «как есть» | комментарий удалён из `base.html`; проверено отсутствие литерала `{#` на всех страницах |
| График накладывался на блок «Купить / Продать» | Plotly генерирует div со `style="height:100%"`; без высоты родителя полотно схлопывалось и перекрывало контент | контейнер графика обёрнут в отдельный `div.plotly-chart` со `clear: both; margin-bottom: 40px; height: 400px; min-height: 400px` |
| Плоская линия вместо динамики цен | см. раздел 9.1 | явный `layout.height = 400` + осмысленный моковый ряд |
| Подписи осей и дат «прилипали» к краям | отсутствовали отступы макета | `margin=dict(l=40, r=40, t=20, b=50)`, подписи осей (`Дата`, `Цена, <валюта>`), `automargin`, `hovermode="x unified"` |
| Некорректная сетка страницы акции | использовались несуществующие бутстрап-классы `col3` | заменено на штатную сетку Bootstrap (`row` / `col-12`) |
| Неактуальная библиотека Plotly на клиенте | `plotly-latest.min.js` отдавал v1.58.5 | подключён `plotly-3.0.1.min.js` |

Итог: страница акции отображается без наложений, график читаемый и информативный, комментарии шаблонов не попадают в HTML.

### 9.4 Краткая карта изменённых файлов

| Файл | Характер изменений |
|---|---|
| `dashboard/services/graph.py` | моковый ряд цен, layout Plotly (высота и отступы), цвет и толщина линии, корректная цена из свечей Tinkoff |
| `dashboard/models.py` | новые модели `Portfolio`, `PortfolioPosition` |
| `dashboard/migrations/0008_portfolio_portfolioposition.py` | новая миграция схемы |
| `dashboard/views.py` | `ShareTradeView`, `PortfolioView`, `buy_share()`, `sell_share()`; обновлён `ShareDetailView` |
| `dashboard/forms.py` | новая форма `TradeForm` |
| `dashboard/urls.py` | маршруты `/portfolio/` и `/trade/<pk>` |
| `dashboard/templates/dashboard/portfolio.html` | новая страница портфеля |
| `dashboard/templates/dashboard/detail.html` | сетка Bootstrap, контейнер графика, блок торговли |
| `dashboard/templates/dashboard/base.html` | ссылка «Мой портфель», flash-сообщения, актуальная версия plotly.js |

**Общий вывод:** исходные дефекты (недоступность исторических данных, 500 вместо 404 в карточке, проблемы с URL и обновлением цен) устранены, приложение дополнено работоспособным виртуальным портфелем, вёрстка приведена в порядок; проект проходит `manage.py check` без замечаний, все миграции применены, сервер запускается и обслуживает страницы корректно.
