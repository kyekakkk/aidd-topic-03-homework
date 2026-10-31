# Технический анализ проекта Investing Demo

> Отчёт составлен по исходному коду в ветке `branch-agent-opencoder` (коммит `362510b`).
> Ссылки вида `файл:строка` указывают на конкретные места в коде.

---

## 1. Назначение приложения и технологический стек

### 1.1. Назначение

**Investing Demo** — веб-приложение для просмотра каталога биржевых акций и их котировок. Данные берутся из **Tinkoff Invest API**. Приложение умеет:

- загружать в локальную БД справочник акций (FIGI, ISIN, тикер, название, валюта) — management-командой `add_shares`;
- периодически, в фоне, обновлять **последнюю цену** каждой акции и признак **направления тренда** (выросла/упала цена относительно предыдущего значения) — задачей Celery;
- показывать список акций в виде HTML-таблицы с постраничным выводом и цветовой подсветкой тренда (зелёный — рост, красный — падение);
- показывать карточку акции с **графиком дневных цен закрытия за последние 180 дней** (Plotly), который строится «на лету» запросом к Tinkoff API;
- давать **аутентифицированным** пользователям создавать, редактировать и удалять акции через HTML-формы;
- регистрировать пользователей и выполнять вход/выход (логин — e-mail);
- предоставлять **REST API** (`/api/v1/shares/`) с полным CRUD, фильтрацией, поиском, сортировкой и пагинацией;
- давать доступ к стандартной админке Django (`/admin/`) с управлением акциями.

### 1.2. Технологический стек

| Слой | Технология | Версия по `requirements.txt` |
|---|---|---|
| Язык | Python | 3.x (в `.venv` установлен 3.13.7) |
| Веб-фреймворк | Django | 4.1.7 |
| REST API | Django REST Framework | 3.14.0 |
| Фильтрация API | django-filter | 22.1 |
| Рендеринг форм | django-crispy-forms + crispy-bootstrap3 | 2.0 / 2022.1 |
| СУБД | PostgreSQL (драйвер psycopg2-binary) | 2.9.5 |
| Фоновые задачи | Celery (worker + beat) | 5.2.7 |
| Брокер сообщений | Redis (клиент redis-py) | 4.5.1 |
| Внешний источник данных | Tinkoff Invest API (gRPC SDK `tinkoff-investments`) | 0.2.0b50 |
| Графики | Plotly (серверная генерация HTML/JS) | 5.13.1 |
| Фронтенд | Django Templates, Bootstrap (локальный CSS), jQuery, Popper, Font Awesome, Moment.js, Tempus Dominus (CDN) | — |
| Инфраструктура | Docker Compose (контейнеры `postgres` и `redis`) | — |
| Инструменты разработки | black, isort | 23.1.0 / 5.12.0 |

> **Замечание.** В `.venv` установлены более новые версии, чем закреплены в `requirements.txt` (Django 5.2.18, DRF 3.18.3, Celery 5.6.3, plotly 7.1.0, django-filter 26.2, django-crispy-forms 2.7), а пакет `tinkoff-investments` не установлен вовсе. То есть файл зависимостей и реальное окружение расходятся.

---

## 2. Структура проекта и основные компоненты

```
aidd-topic-03-homework/
├── manage.py                     # CLI Django; DJANGO_SETTINGS_MODULE=config.settings
├── requirements.txt              # Зависимости Python (закреплённые версии)
├── docker-compose.yml            # PostgreSQL + Redis для локальной разработки
├── README.md                     # Краткая инструкция по запуску
├── HOMEWORK.md                   # Текст домашнего задания
│
├── config/                       # Пакет конфигурации проекта (Django "project")
│   ├── __init__.py               # Импорт celery_app, чтобы Celery поднимался вместе с Django
│   ├── settings.py               # Все настройки: приложения, БД, DRF, логирование, Celery, токен Tinkoff
│   ├── urls.py                   # Корневой роутинг: admin/, "" → dashboard, "user" → user
│   ├── celery.py                 # Экземпляр Celery, autodiscover задач, расписание beat
│   ├── wsgi.py / asgi.py         # Точки входа для WSGI/ASGI-серверов (стандартные)
│
├── dashboard/                    # Основное приложение: акции, котировки, API
│   ├── models.py                 # Модель Share
│   ├── views.py                  # HTML-представления (CBV): список, деталь, CRUD
│   ├── forms.py                  # ShareModelForm (ModelForm по всем полям)
│   ├── urls.py                   # Маршруты dashboard + подключение api/
│   ├── admin.py                  # Регистрация Share в админке
│   ├── tasks.py                  # Celery-задача update_last_price
│   ├── tests.py                  # Тесты API и главной страницы (APITestCase)
│   ├── services/                 # Слой интеграции с Tinkoff Invest API
│   │   ├── market_data.py        # get_last_data(): последняя цена акции
│   │   └── graph.py              # get_graph(): свечи за 180 дней → Plotly-div
│   ├── api/                      # REST API
│   │   ├── urls.py               # v1/ → api.v1.urls
│   │   └── v1/
│   │       ├── router.py         # DefaultRouter, регистрация "shares"
│   │       ├── urls.py           # include(router.urls)
│   │       ├── views.py          # ShareViewSet (ModelViewSet) + ShareFilter
│   │       └── serializer.py     # ShareSerializer (ModelSerializer)
│   ├── management/commands/
│   │   └── add_shares.py         # Первичная загрузка справочника акций из Tinkoff
│   ├── migrations/               # 0001–0007: эволюция таблицы dashboard_share
│   ├── templates/dashboard/      # base, list, detail, create (create+update), delete
│   └── static/dashboard/css/     # bootstrap.min.css, sticky-footer-navbar.css
│
└── user/                         # Приложение аутентификации
    ├── models.py                 # User = get_user_model() (собственной модели нет)
    ├── forms.py                  # RegistrationForm, AuthForm
    ├── views.py                  # AuthView, RegistrationView, LogoutView
    ├── urls.py                   # login/, registration/, logout/
    ├── templates/user/           # base, auth, registration
    └── static/user/css/          # bootstrap.min.css, signin.css
```

### 2.1. Назначение компонентов

**`config`** — «проект» Django. Он связывает приложения, задаёт настройки и инициализирует Celery. `config/__init__.py` импортирует `celery_app`, поэтому задачи регистрируются при любом запуске Django.

**`dashboard`** — бизнес-ядро приложения:

- *модель* `Share` — единственная прикладная сущность;
- *HTML-интерфейс* на generic class-based views (`ListView`, `CreateView`, `UpdateView`, `DeleteView`) и одном «ручном» `View` для карточки;
- *REST API* на DRF `ModelViewSet`;
- *сервисный слой* (`services/`) — тонкие обёртки над SDK Tinkoff;
- *фоновая обработка* (`tasks.py`) и *CLI-команда* (`add_shares`) для наполнения и актуализации данных.

**`user`** — регистрация, вход и выход на стандартной модели `django.contrib.auth.models.User`. E-mail используется одновременно как `username` и как `email`.

**Встроенные приложения Django** — `admin`, `auth`, `contenttypes`, `sessions`, `messages`, `staticfiles` — дают админку, аутентификацию, сессии и раздачу статики.

---

## 3. Архитектура и взаимодействие компонентов

### 3.1. Общая схема

Приложение — **монолит Django** по классической схеме MTV (Model–Template–View). К нему добавлены отдельный процесс фоновых задач (Celery) и внешний gRPC-сервис (Tinkoff).

```
                ┌──────────────────────────── Браузер / API-клиент ────────────────────────────┐
                │                                                                              │
                ▼ HTTP                                                                         ▼ HTTP (JSON)
┌──────────────────────────────────────── Процесс Django (WSGI/ASGI) ─────────────────────────────────────────┐
│  Middleware: Security → Session → Common → CSRF → Auth → Messages → XFrameOptions                           │
│                                                                                                             │
│  config/urls.py ──┬── admin/            → django.contrib.admin (ShareAdmin)                                 │
│                   ├── ""                → dashboard/urls.py ──┬── HTML views (views.py) ── templates         │
│                   │                                           └── api/v1/ → DRF Router → ShareViewSet        │
│                   └── "user"            → user/urls.py → AuthView / RegistrationView / LogoutView           │
│                                                                                                             │
│  ShareDetailView ──► services/graph.py ──► Tinkoff Invest API (gRPC, синхронно, в рамках HTTP-запроса)       │
└──────────────────────────────────┬──────────────────────────────────────────────────────────────────────────┘
                                   │ Django ORM
                                   ▼
                        ┌──────────────────────┐
                        │  PostgreSQL          │◄───────────────┐
                        │  dashboard_share,    │                │ ORM (update)
                        │  auth_user, ...      │                │
                        └──────────────────────┘                │
                                                                │
┌──────────── Celery Beat ────────────┐   Redis (брокер)   ┌────┴──────────── Celery Worker ─────────────┐
│ beat_schedule: каждые 10 секунд  ───┼──────────────────►│ dashboard.tasks.update_last_price            │
│ "dashboard.tasks.update_last_price" │                    │   └► services/market_data.get_last_data()    │
└─────────────────────────────────────┘                    │        └► Tinkoff Invest API (gRPC)          │
                                                           └──────────────────────────────────────────────┘

┌──────── manage.py add_shares (разово) ────────┐
│ Tinkoff instruments.shares() → get_or_create  │──► PostgreSQL
└───────────────────────────────────────────────┘
```

### 3.2. Процессы времени выполнения

Для полной работы нужно запустить **пять процессов** (см. `README.md`):

1. PostgreSQL (`docker-compose up`, порт 5432);
2. Redis (`docker-compose up`, порт 6379);
3. веб-сервер Django (`manage.py runserver`);
4. Celery Beat (`celery -A config beat`) — планировщик;
5. Celery Worker (`celery -A config worker`) — исполнитель; на Windows — с пулом `eventlet`.

Плюс один раз, до начала работы, — `python manage.py add_shares` для наполнения справочника.

### 3.3. Слои и их связи

| Слой | Компоненты | От кого зависит |
|---|---|---|
| Представление (HTML) | `dashboard/views.py`, `user/views.py`, шаблоны | формы, модель, `services.graph` |
| Представление (API) | `ShareViewSet`, `ShareSerializer`, `ShareFilter` | модель |
| Формы / валидация | `ShareModelForm`, `RegistrationForm`, `AuthForm` | модели |
| Доменная модель | `Share`, `User` (встроенная) | Django ORM |
| Интеграция | `services/market_data.py`, `services/graph.py`, `add_shares` | `tinkoff.invest.Client`, `settings.TINKOFF_TOKEN` |
| Фоновые задачи | `tasks.update_last_price` | модель, `services.market_data` |
| Конфигурация | `config/settings.py`, `config/celery.py` | — |

**Архитектурные особенности:**

- Сервисный слой есть только для внешнего API. Бизнес-логика расчёта тренда лежит прямо в Celery-задаче ([dashboard/tasks.py:15-22](dashboard/tasks.py#L15-L22)).
- Логгер `main` создаётся в `settings.py`, и модули импортируют его оттуда (`from config.settings import logger`). Так же импортируется `TINKOFF_TOKEN`: напрямую из `config.settings`, а не через `django.conf.settings`.
- HTML-часть и REST API работают с одной моделью независимо друг от друга: у них разные механизмы валидации (`ModelForm` и `ModelSerializer`) и разные правила доступа.
- Карточка акции **синхронно** обращается к Tinkoff API при каждом открытии страницы. Время ответа и доступность страницы зависят от внешнего сервиса, кэширования нет.

---

## 4. Библиотеки и внешние зависимости

### 4.1. Зависимости, которые используются в коде напрямую

| Пакет | Где импортируется | Назначение |
|---|---|---|
| `Django` | везде | веб-фреймворк, ORM, шаблоны, аутентификация, админка |
| `djangorestframework` | `dashboard/api/v1/*`, `dashboard/tests.py` | `ModelViewSet`, `ModelSerializer`, `DefaultRouter`, `OrderingFilter`, `SearchFilter`, `APITestCase`, `LimitOffsetPagination` (через settings) |
| `django-filter` | `dashboard/api/v1/views.py`, settings | `FilterSet`, `DjangoFilterBackend` — фильтрация по `name` и `ticker` |
| `django-crispy-forms`, `crispy-bootstrap3` | `INSTALLED_APPS`, шаблон `create.html` (`as_crispy_field`) | рендеринг полей формы в разметке Bootstrap 3 |
| `celery` | `config/celery.py`, `dashboard/tasks.py` | фоновые и периодические задачи |
| `redis` | неявно, через `CELERY_BROKER_URL="redis://..."` | транспорт брокера для Celery/kombu |
| `psycopg2-binary` | неявно, через `ENGINE=django.db.backends.postgresql` | драйвер PostgreSQL |
| `tinkoff-investments` | `dashboard/services/*`, `add_shares.py` (`from tinkoff.invest import Client, CandleInterval`, `tinkoff.invest.utils.now`) | gRPC-клиент Tinkoff Invest API |
| `plotly` | `dashboard/services/graph.py` (`plotly.graph_objs.Scatter`, `plotly.offline.plot`) | генерация HTML-div с интерактивным графиком |

### 4.2. Транзитивные зависимости, закреплённые в `requirements.txt`

- **Стек Celery:** `amqp`, `kombu`, `billiard`, `vine`, `click`, `click-didyoumean`, `click-plugins`, `click-repl`, `prompt-toolkit`, `wcwidth`, `pytz`, `async-timeout` (для redis).
- **Стек Tinkoff SDK:** `grpcio`, `protobuf==3.20.3` (жёстко закреплена старая ветка protobuf), `python-dateutil`, `cachetools`, `six`.
- **Django:** `asgiref`, `sqlparse`.
- **Прочие:** `pydantic`, `tenacity` (plotly), `typing_extensions`, `packaging`.
- **Инструменты разработки, попавшие в рабочие зависимости:** `black`, `isort`, `mypy-extensions`, `pathspec`, `platformdirs`, `tomli`.

### 4.3. Проблемные места в зависимостях

- В файле одновременно есть `tinkoff==0.1.1` и `tinkoff-investments==0.2.0b50`. Оба пакета используют пространство имён `tinkoff`. Код работает только с `tinkoff.invest` из `tinkoff-investments`, поэтому `tinkoff==0.1.1` лишний и может конфликтовать с ним.
- `tinkoff-investments==0.2.0b50` — бета-версия. SDK позже переименован и переехал (`t-tech-investments`, домен T-Bank).
- Рабочие и dev-зависимости не разделены (black/isort лежат в общем `requirements.txt`).
- `eventlet` и `cryptography`, нужные для worker'а на Windows, упомянуты только в README и в `requirements.txt` не входят.
- Версии устарели: Django 4.1 больше не поддерживается, `protobuf 3.20` несовместим с современными `grpcio`, а `psycopg2-binary 2.9.5` и `grpcio 1.51` не ставятся из готовых wheel на Python 3.13.

### 4.4. Фронтенд-зависимости (CDN, [dashboard/templates/dashboard/base.html](dashboard/templates/dashboard/base.html))

- `plotly-latest.min.js` (cdn.plot.ly) — версия не закреплена. Кроме того, `plotly.offline.plot(..., output_type="div")` по умолчанию сам встраивает plotly.js в страницу, так что библиотека загружается дважды.
- jQuery 3.3.1 slim, Popper 1.14.6, Font Awesome 4.7.0, Moment.js 2.23.0, Tempus Dominus Bootstrap 4 5.1.2. Moment.js и Tempus Dominus (выбор даты) нигде не используются.
- Bootstrap подключён локальным файлом. CSS-классы в шаблонах (`d-flex`, `text-end`, `fw-normal`) относятся к Bootstrap 4/5, а crispy-формы рендерятся шаблонным пакетом `bootstrap3`. Версии не согласованы.

### 4.5. Внешние сервисы

| Сервис | Протокол | Где используется | Методы |
|---|---|---|---|
| Tinkoff Invest API | gRPC (TLS) | `add_shares`, `market_data`, `graph` | `instruments.shares()`, `market_data.get_last_prices(figi=[...])`, `get_all_candles(figi, from_, interval=DAY)` |
| PostgreSQL | TCP 5432 | Django ORM | — |
| Redis | TCP 6379 | брокер Celery | — |

---

## 5. Модель данных

### 5.1. Сущность `Share` (таблица `dashboard_share`)

Источник: [dashboard/models.py](dashboard/models.py). Акция — финансовый инструмент из справочника Tinkoff.

| Поле | Тип Django → тип PostgreSQL | Ограничения | Описание |
|---|---|---|---|
| `id` | `BigAutoField` → `bigint` (identity) | PK | Суррогатный ключ (`DEFAULT_AUTO_FIELD`) |
| `figi` | `CharField(255)` → `varchar(255)` | `UNIQUE`, `NOT NULL` | Financial Instrument Global Identifier — по нему идут запросы к Tinkoff API |
| `isin` | `CharField(255)` | `NOT NULL` | International Securities Identification Number |
| `name` | `CharField(255)` | `NOT NULL` | «Наименование компании» |
| `ticker` | `CharField(10)` | `UNIQUE`, `NOT NULL` | «Тикер» — биржевой код |
| `currency` | `CharField(20)` | `NOT NULL` | «Валюта» (`rub`, `usd`, …) |
| `uid` | `CharField(255)` | `UNIQUE`, `NOT NULL` | Внутренний UID инструмента в Tinkoff |
| `last_price` | `FloatField` → `double precision` | `NULL` | «Текущая цена» — последняя полученная цена |
| `is_trend_high` | `BooleanField(null=True)` | `NULL` | «Растет цена»: `True` — цена не упала относительно прошлого значения, `False` — упала, `NULL` — ещё не рассчитано |
| `updated_at` | `DateTimeField(auto_now=True)` → `timestamptz` | `NULL` | Время последнего сохранения через `save()` |

Метаданные: `verbose_name="Акция"`, `verbose_name_plural="Акции"`. Порядок по умолчанию (`ordering`) и дополнительные индексы не заданы. Индексы есть только неявные — от PK и `UNIQUE`.

**История схемы (миграции):**

| Миграция | Изменение |
|---|---|
| `0001_add_share` | Создание таблицы: `figi`, `isin`, `name`, `ticker`, `currency` |
| `0002_update_share` | `UNIQUE` на `figi` и `ticker` |
| `0003_add_uuid` | Поле `uid` (`UNIQUE`, временный default `""`) |
| `0004_add_last_price` | Поля `last_price`, `is_trend_high`; промежуточные (ошибочные) `verbose_name` |
| `0005`, `0006` | Исправление `verbose_name` у `name` и `ticker` |
| `0007_add_updated_at` | Поле `updated_at` (`auto_now`) |

### 5.2. Сущность `User` (таблица `auth_user`)

Собственной модели пользователя нет: [user/models.py](user/models.py) только экспортирует `get_user_model()`, то есть стандартный `django.contrib.auth.models.User`. Из его полей приложение использует:

| Поле | Как используется |
|---|---|
| `username` | Хранит e-mail (при регистрации `create_user(email, email, password)`) |
| `email` | Тот же e-mail; по нему проверяется уникальность при регистрации |
| `password` | Хэш пароля (PBKDF2 по умолчанию) |
| `is_authenticated` (свойство) | Право на создание, изменение и удаление акций в HTML-интерфейсе |
| `is_staff` / `is_superuser` | Доступ к `/admin/` |

### 5.3. Связи

```
┌─────────────────────┐                ┌─────────────────────┐
│      auth_user      │                │   dashboard_share   │
│─────────────────────│     (связи     │─────────────────────│
│ id (PK)             │      нет)      │ id (PK)             │
│ username = email    │                │ figi (UK)           │
│ email               │                │ ticker (UK)         │
│ password            │                │ uid (UK)            │
│ ...                 │                │ isin, name, currency│
└─────────────────────┘                │ last_price          │
          │ 1                          │ is_trend_high       │
          │                            │ updated_at          │
          │ N                          └─────────────────────┘
┌─────────────────────┐
│   django_session    │  (сессии аутентифицированных пользователей)
└─────────────────────┘
```

- Между `Share` и `User` **нет связей**: акции — общий справочник, без владельцев, портфелей или избранного.
- В модели данных нет истории котировок. Хранится только последнее значение (`last_price`), исторические свечи каждый раз запрашиваются из Tinkoff API.
- Остальные таблицы (`auth_group`, `auth_permission`, `django_content_type`, `django_admin_log`, `django_session`, `django_migrations`) — стандартные таблицы Django со стандартными связями.

### 5.4. Внешнее представление модели

| Канал | Состав полей |
|---|---|
| `ShareModelForm` (HTML) | `fields="__all__"` → `figi, isin, name, ticker, currency, uid, last_price, is_trend_high` (`updated_at` не редактируется из-за `auto_now`) |
| `ShareSerializer` (API) | `id, figi, isin, name, ticker, currency, last_price, is_trend_high, updated_at` — **без `uid`** |
| `ShareAdmin` | список: `figi, isin, name, ticker, currency`; поиск: `figi, isin, name, ticker`; форма: всё, кроме `updated_at` |

---

## 6. Обработка пользовательских запросов и взаимодействие с БД

### 6.1. Таблица маршрутов

| Метод | URL | Обработчик | Доступ | Работа с БД |
|---|---|---|---|---|
| GET | `/` | `ShareListView` | все | `SELECT ... ORDER BY name LIMIT 100 OFFSET n` + `COUNT(*)` |
| GET | `/<pk>` | `ShareDetailView` | все | `SELECT ... WHERE id=pk` + gRPC-запрос свечей |
| GET/POST | `/create` | `ShareCreateView` | аутентифицированные | `INSERT` |
| GET/POST | `/update/<pk>` | `ShareUpdateView` | аутентифицированные | `SELECT` + `UPDATE` |
| GET/POST | `/delete/<pk>` | `ShareDeleteView` | аутентифицированные | `SELECT` + `DELETE` |
| GET/POST | `/userlogin/` | `AuthView` | все | `SELECT auth_user`, `INSERT/UPDATE django_session`, `UPDATE last_login` |
| GET/POST | `/userregistration/` | `RegistrationView` | все | `SELECT auth_user WHERE email=`, `INSERT auth_user`, сессия |
| GET | `/userlogout/` | `LogoutView` | все | `DELETE django_session` |
| GET, POST | `/api/v1/shares/` | `ShareViewSet` list/create | **все (AllowAny)** | `SELECT` с фильтрами/`LIMIT`/`OFFSET`, `INSERT` |
| GET, PUT, PATCH, DELETE | `/api/v1/shares/<pk>/` | `ShareViewSet` retrieve/update/partial_update/destroy | **все (AllowAny)** | `SELECT`/`UPDATE`/`DELETE` |
| GET | `/api/v1/` | корневой view `DefaultRouter` | все | — |
| * | `/admin/...` | Django Admin | `is_staff` | стандартный CRUD |

> **Важно.** В [config/urls.py:7](config/urls.py#L7) префикс приложения `user` записан **без завершающего слэша** (`path("user", ...)`). Поэтому реальные адреса — `/userlogin/`, `/userregistration/`, `/userlogout/`, а не `/user/login/` и т. д. В шаблонах ссылки строятся через `{% url %}` и потому работают, но выглядят неожиданно.

### 6.2. Жизненный цикл HTTP-запроса

1. WSGI-сервер передаёт запрос в Django. Цепочка middleware загружает сессию (`SessionMiddleware`), проверяет CSRF-токен для POST (`CsrfViewMiddleware`) и записывает пользователя в `request.user` (`AuthenticationMiddleware`).
2. `ROOT_URLCONF = "config.urls"` выбирает обработчик по URL.
3. Для HTML-маршрутов вызывается class-based view. Миксин `IsUserAuthenticatedMixin` ([dashboard/views.py:11-17](dashboard/views.py#L11-L17)) в `test_func()` проверяет `request.user.is_authenticated`. При отказе `handle_no_permission()` **перенаправляет на главную**, а не на страницу входа и не отдаёт 403.
4. View обращается к ORM. Транзакции заданы по умолчанию — autocommit, `ATOMIC_REQUESTS` не включён.
5. Ответ рендерится шаблоном (HTML) или DRF-рендерером (JSON или Browsable API).

### 6.3. HTML-интерфейс акций (`dashboard/views.py`)

**Список (`ShareListView`).** Generic `ListView`: `paginate_by=100`, `ordering=["name"]`. Django строит `Share.objects.order_by("name")`, Paginator выполняет `COUNT(*)` и выборку страницы. Номер страницы передаётся в `?page=N`. Шаблон `list.html` выводит таблицу, подкрашивает ячейку цены по `is_trend_high` и показывает кнопки управления только аутентифицированным пользователям.

**Карточка (`ShareDetailView`).**

```python
share = Share.objects.get(id=pk)                      # 1 SELECT
render(..., {"plot_div": get_graph(share), ...})     # gRPC-запрос к Tinkoff
```

`get_graph()` открывает `Client(TINKOFF_TOKEN)`, итерирует `get_all_candles(figi, from_=now()-180 дней, interval=DAY)` и собирает пары «дата — `candle.close.units`». Затем `plotly.offline.plot(..., output_type="div")` превращает их в HTML+JS, который шаблон вставляет с `{% autoescape off %}`.

Особенности:
- При несуществующем `pk` выбрасывается `Share.DoesNotExist`, и пользователь получает **500** вместо 404 (`get_object_or_404` не используется).
- Если Tinkoff API недоступен или токен пуст, страница тоже падает с 500: ошибки не обрабатываются.
- Берётся только целая часть цены (`units`), дробная часть (`nano`) отбрасывается.

**Создание и редактирование (`ShareCreateView`, `ShareUpdateView`).** Generic-представления на `ShareModelForm` с общим шаблоном `create.html` (поля рендерит crispy). На POST:
1. `form.is_valid()` проверяет типы и длины полей, а `validate_unique()` — уникальность `figi`, `ticker` и `uid` (по одному `SELECT` на каждое уникальное поле);
2. `form.save()` выполняет `INSERT` или `UPDATE`; `auto_now` обновляет `updated_at`;
3. после этого — редирект на `success_url = dashboard:index`.

Через форму можно вручную задать `last_price` и `is_trend_high`, хотя эти поля должна заполнять фоновая задача.

**Удаление (`ShareDeleteView`).** GET показывает страницу подтверждения `delete.html`, POST выполняет `DELETE` и редиректит на главную.

### 6.4. Аутентификация (`user/views.py`, `user/forms.py`)

**Вход (`AuthView.post`).** Форма `AuthForm` создаётся, но **не валидируется**: значения берутся напрямую из `form.data["email"]` и `form.data["password"]`. E-mail приводится к нижнему регистру и передаётся в `authenticate(username=email, password=...)`. `ModelBackend` выполняет `SELECT ... FROM auth_user WHERE username=...` и проверяет хэш. При успехе `login()` создаёт сессию и обновляет `last_login`, после чего идёт редирект на главную. При неудаче форма показывается снова с сообщением об ошибке. Если поле в POST отсутствует, возникает `KeyError` и, как следствие, 500.

**Регистрация (`RegistrationView.post`).** `RegistrationForm.clean()`:
1. сравнивает `password1` и `password2`;
2. выполняет `User.objects.filter(email=email)` и, если запись найдена, сообщает, что e-mail уже занят.

`save()` вызывает `User.objects.create_user(email, email, password)` (`INSERT` в `auth_user`), затем `authenticate()`, после чего view выполняет `login()`.

Особенности:
- `AUTH_PASSWORD_VALIDATORS` настроены, но при регистрации **не вызываются**: `validate_password` нигде не используется.
- E-mail при регистрации не приводится к нижнему регистру, а при входе приводится. Пользователь, зарегистрированный как `User@Mail.ru`, не сможет войти.
- Если e-mail невалиден, `self.cleaned_data["email"]` в `clean()` выбрасывает `KeyError`. А view обращается к `form.errors["__all__"]`, которого нет при ошибках отдельных полей. В обоих случаях — 500.

**Выход (`LogoutView.get`).** `logout()` очищает сессию и перенаправляет на главную. Выход выполняется GET-запросом без CSRF-защиты.

### 6.5. REST API (`dashboard/api/v1/`)

`ShareViewSet(ModelViewSet)` с `queryset = Share.objects.all()` автоматически поддерживает операции `list`, `create`, `retrieve`, `update`, `partial_update`, `destroy`.

**Конвейер обработки запроса в DRF:**

1. **Аутентификация и права.** В `REST_FRAMEWORK` не заданы `DEFAULT_PERMISSION_CLASSES`, поэтому действует `AllowAny`: **любой анонимный клиент может создавать, изменять и удалять акции** (HTML-интерфейс при этом требует входа).
2. **Фильтрация** (`filter_backends`):
   - `DjangoFilterBackend` + `ShareFilter` — точное совпадение: `?name=Apple`, `?ticker=AAPL` → `WHERE name = ... AND ticker = ...`;
   - `SearchFilter` с `search_fields=["$name"]` — поиск по **регулярному выражению**: `?search=^App` → `WHERE name ~* '^App'` в PostgreSQL;
   - `OrderingFilter` — `?ordering=name`, `?ordering=-ticker`.
3. **Пагинация.** `LimitOffsetPagination`, `PAGE_SIZE=100`: `?limit=20&offset=40` → `LIMIT 20 OFFSET 40` плюс `COUNT(*)`. Ответ имеет вид `{count, next, previous, results}`.
4. **Сериализация.** `ShareSerializer` проверяет обязательные поля и уникальность через `UniqueValidator` (по `SELECT` на каждое уникальное поле). Поле `uid` в сериализатор не входит, поэтому при `POST` оно сохраняется пустой строкой `""`. Так как `uid` уникально, **второе создание акции через API** нарушит ограничение `UNIQUE`: `IntegrityError` → 500.
5. **Запись.** `serializer.save()` → `INSERT`/`UPDATE` через `Model.save()`, `updated_at` обновляется.

Коды ответов, проверенные в [dashboard/tests.py](dashboard/tests.py): 200 (list/retrieve/update), 201 (create), 204 (delete), 400 (невалидные данные), 404 (несуществующий id).

### 6.6. Фоновое обновление цен (Celery)

**Расписание.** [config/celery.py:13-18](config/celery.py#L13-L18) — задача `"add-every-5-min"`, но интервал фактически `schedule: 10.0`, то есть **каждые 10 секунд**. Beat кладёт сообщение в Redis (`redis://127.0.0.1:6379/0`), worker его забирает.

**Алгоритм `update_last_price`** ([dashboard/tasks.py](dashboard/tasks.py)):

```
shares = Share.objects.all()                       # 1 SELECT всех акций
для каждой share:
    [last_price, _] = get_last_data(share)         # 1 gRPC-запрос на акцию
    is_trend_high = not (share.last_price > last_price)
                    # при last_price = None → TypeError → логируется, тренд = True
    Share.objects.filter(id=share.id).update(...)  # 1 UPDATE на акцию
    исключения → logger.error(...)
```

Особенности взаимодействия с БД и API:

- **N+1 по внешнему API и по БД.** На каждую акцию — отдельный gRPC-запрос и отдельный `UPDATE`, хотя `get_last_prices(figi=[...])` принимает список FIGI, а Django умеет `bulk_update`. После `add_shares` в справочнике обычно больше 1500 акций, и такой цикл заведомо не уложится в 10 секунд. Задачи будут накапливаться в очереди, а запросы — упираться в лимиты Tinkoff API.
- **`updated_at` не обновляется.** `QuerySet.update()` не вызывает `save()`, и `auto_now` не срабатывает, поэтому «Время последнего обновления» на карточке не отражает обновлений цены.
- **Потеря точности.** Сохраняется только `price.units` — целая часть цены. Цена 0.0345 превращается в 0.
- Второе возвращаемое значение (время котировки, переменная `detetime`) не используется.
- Одинаковая цена считается «ростом» (`is_trend_high=True`).

### 6.7. Первичная загрузка данных (`add_shares`)

[dashboard/management/commands/add_shares.py](dashboard/management/commands/add_shares.py): `client.instruments.shares()` возвращает все акции, доступные в Tinkoff. Для каждой выполняется `Share.objects.get_or_create(figi=..., name=..., isin=..., ticker=..., currency=..., uid=...)`.

Все поля передаются как **критерии поиска**, а не через `defaults`. Если у существующей акции изменилось хотя бы одно поле (например, название), `get_or_create` не найдёт запись и попытается создать дубликат. Это нарушит `UNIQUE(figi)`, и команда упадёт с `IntegrityError`. Транзакции нет, поэтому при падении в середине часть данных уже будет записана. Тикеры длиннее 10 символов тоже вызовут ошибку вставки (`max_length=10`).

### 6.8. Конфигурация, влияющая на обработку запросов

- `SECRET_KEY = ""` и `TINKOFF_TOKEN = ""` захардкожены пустыми в [config/settings.py](config/settings.py). Локальный `.env` (переменные `DJANGO_SECRET_KEY`, `DB_*`, `TINKOFF_TOKEN`, `CELERY_*`, `TINVEST_*`) настройками **не читается**.
- Параметры PostgreSQL (`postgres/postgres@localhost:5432/investing`) записаны в коде. Блок SQLite закомментирован, поэтому даже тесты требуют запущенного PostgreSQL.
- `DEBUG = True`, `ALLOWED_HOSTS = []` — конфигурация только для разработки.
- `TIME_ZONE = "UTC"`, а `CELERY_TIMEZONE = "Europe/Moscow"`; `LANGUAGE_CODE = "en-us"`, хотя интерфейс на русском.
- Логирование: логгер `main` пишет в консоль и в файл `app.logs` (путь относительно текущего рабочего каталога).
- `STATIC_ROOT` не задан, поэтому для продакшена не настроен `collectstatic`.
- В `docker-compose.yml` каталог проекта монтируется в контейнер PostgreSQL (`./:/app`) без видимой цели, а данные БД не вынесены в именованный volume.

---

## 7. Функциональные требования и дефекты реализации

> Раздел восстановлен по исходному коду («как реализовано», а не «как задумывалось»).
> Обозначения: **FR** — функциональная возможность, **SC** — сценарий, **BR** — бизнес-правило или ограничение, **DEF** — дефект, **AMB** — неоднозначность или противоречие.

### 7.1. Фактические функциональные возможности

#### Каталог акций (HTML-интерфейс)

1. **FR-01. Просмотр списка акций.** Главная страница `/` выводит таблицу акций, отсортированную по названию (`ordering=["name"]`). Столбцы: «Тикер», «Название», «ISIN», «Текущая цена» (цена + валюта).
2. **FR-02. Постраничный вывод списка.** По 100 акций на страницу, переход по `?page=N`. Отображаются кнопки «назад» и «вперёд» и номера всех страниц.
3. **FR-03. Индикация тренда цены.** Ячейка цены подсвечивается зелёным (`mediumseagreen`), если `is_trend_high` истинно, иначе красным (`palevioletred`).
4. **FR-04. Пустое состояние.** Если акций нет, вместо таблицы выводится «Акций еще нет».
5. **FR-05. Карточка акции.** По ссылке с тикера (`/<id>`) показываются название, текущая цена с валютой и время последнего обновления записи.
6. **FR-06. График исторических цен.** На карточке выводится интерактивный линейный график Plotly с дневными ценами закрытия за последние 180 дней. Данные запрашиваются из Tinkoff Invest API при каждом открытии страницы.
7. **FR-07. Добавление акции** (`/create`): форма со всеми редактируемыми полями модели. Доступно только вошедшим пользователям.
8. **FR-08. Редактирование акции** (`/update/<id>`): та же форма, заполненная текущими значениями. Только для вошедших пользователей.
9. **FR-09. Удаление акции** (`/delete/<id>`): страница подтверждения и удаление по POST. Только для вошедших пользователей.
10. **FR-10. Управление по ролям в интерфейсе.** Кнопки «Добавить», «Редактировать» и «Удалить» и столбец «Управление» видны только аутентифицированным пользователям.

#### Пользователи

11. **FR-11. Регистрация** по e-mail и паролю с подтверждением. После успешной регистрации пользователь сразу входит в систему.
12. **FR-12. Вход** по e-mail и паролю.
13. **FR-13. Выход** из системы.
14. **FR-14. Приветствие в шапке.** Вошедшему пользователю показывается «Привет, <email>» и кнопка «Выход», гостю — кнопка «Войти».

#### REST API (`/api/v1/`)

15. **FR-15. Список акций** `GET /api/v1/shares/` с пагинацией `limit`/`offset` (по умолчанию 100 записей).
16. **FR-16. Фильтрация** по точному совпадению `?name=` и `?ticker=`.
17. **FR-17. Поиск** по названию с регулярным выражением без учёта регистра: `?search=`.
18. **FR-18. Сортировка** `?ordering=name|-name|ticker|-ticker`.
19. **FR-19. CRUD одной акции:** `GET`, `PUT`, `PATCH`, `DELETE /api/v1/shares/<id>/`, создание — `POST /api/v1/shares/`.
20. **FR-20. Browsable API** — HTML-обозреватель DRF и корневая страница `/api/v1/` со списком ресурсов.

#### Администрирование и обслуживание данных

21. **FR-21. Админ-панель** `/admin/`: список акций (`figi`, `isin`, `name`, `ticker`, `currency`), поиск по `figi`, `isin`, `name`, `ticker`, редактирование и удаление. Через стандартный раздел `auth` — управление пользователями и группами.
22. **FR-22. Загрузка справочника акций** командой `python manage.py add_shares`: все акции, доступные в Tinkoff Invest API.
23. **FR-23. Периодическое обновление цен** задачей Celery `update_last_price` каждые 10 секунд: для всех акций обновляются `last_price` и `is_trend_high`.
24. **FR-24. Журналирование** ошибок фоновой задачи и запросов цен в консоль и в файл `app.logs`.
25. **FR-25. Автотесты** REST API (CRUD, коды 200/201/204/400/404) и доступности главной страницы.

**Чего в приложении нет**, хотя по назначению этого можно ожидать: портфелей и избранного, хранения истории котировок, восстановления пароля, профиля пользователя, ролевой модели (кроме `is_staff` для админки), уведомлений, API для пользователей и аутентификации.

### 7.2. Сценарии взаимодействия пользователя

#### SC-01. Просмотр списка акций (любой посетитель)

1. Пользователь открывает `/`.
2. Система выбирает страницу акций (100 записей, сортировка по названию) и показывает таблицу с подсветкой тренда.
3. Пользователь листает страницы кнопками пагинации (`?page=N`).
4. **Альтернатива:** акций нет → сообщение «Акций еще нет».

#### SC-02. Просмотр карточки акции с графиком (любой посетитель)

1. Пользователь нажимает на тикер в списке → `/<id>`.
2. Система читает акцию из БД, запрашивает у Tinkoff дневные свечи за 180 дней и строит график.
3. Отображаются название, цена, валюта, время обновления и график.
4. **Исключения:** несуществующий `id` → ошибка 500. Tinkoff API недоступен или токен не задан → ошибка 500.

#### SC-03. Регистрация

1. Гость нажимает «Войти» → «Зарегистрироваться» (`/userregistration/`).
2. Вводит e-mail, пароль и повтор пароля.
3. Система проверяет совпадение паролей и уникальность e-mail.
4. Создаётся пользователь (`username = email = введённый e-mail`), выполняется вход и редирект на главную.
5. **Альтернативы:** пароли не совпадают → «Введенные пароли не совпадают». E-mail занят → «Данный e-mail уже зарегистрирован!…». Некорректный формат e-mail → ошибка 500 (см. DEF-08).

#### SC-04. Вход

1. Гость нажимает «Войти» (`/userlogin/`), вводит e-mail и пароль.
2. Система приводит e-mail к нижнему регистру и проверяет пару «логин — пароль».
3. Успех → создаётся сессия, редирект на главную. Неудача → «Неверный логин или пароль! Повторите попытку.».

#### SC-05. Выход

1. Вошедший пользователь нажимает «Выход» (`/userlogout/`, GET).
2. Сессия завершается, редирект на главную.

#### SC-06. Добавление акции (вошедший пользователь)

1. На главной пользователь нажимает «Добавить» → `/create`.
2. Заполняет форму: FIGI, ISIN, наименование, тикер, валюта, UID, а также текущая цена и признак роста (необязательные).
3. Нажимает «Сохранить». Система проверяет обязательность, длины и уникальность `figi`, `ticker`, `uid`.
4. Успех → запись создаётся, редирект на главную. Ошибка → форма с сообщениями crispy-forms.
5. **Альтернатива:** гость открывает `/create` напрямую → его молча перенаправляют на главную.

#### SC-07. Редактирование акции (вошедший пользователь)

1. В строке таблицы пользователь нажимает «Редактировать» → `/update/<id>`.
2. Форма заполнена текущими значениями. Пользователь меняет поля и сохраняет.
3. Проверки — как в SC-06. Успех → редирект на главную.

#### SC-08. Удаление акции (вошедший пользователь)

1. Пользователь нажимает «Удалить» → `/delete/<id>`, видит вопрос «Вы уверены, что хотите удалить инструмент: "<name>"?».
2. Подтверждает. Запись удаляется, редирект на главную.

#### SC-09. Работа через REST API (любой клиент, без аутентификации)

1. Клиент запрашивает `GET /api/v1/shares/?search=^Сбер&ordering=ticker&limit=20`.
2. Получает JSON `{count, next, previous, results:[...]}`.
3. Выполняет `POST`, `PUT`, `PATCH` или `DELETE` без какой-либо аутентификации.

#### SC-10. Наполнение и актуализация данных (оператор)

1. Оператор задаёт `TINKOFF_TOKEN` в `settings.py` и запускает PostgreSQL и Redis (`docker-compose up`).
2. Выполняет `python manage.py add_shares` → справочник акций загружается в БД.
3. Запускает `celery beat` и `celery worker` → цены и тренды обновляются каждые 10 секунд.

### 7.3. Бизнес-правила, проверки и ограничения

#### Данные акции

| ID | Правило / ограничение | Где реализовано |
|---|---|---|
| BR-01 | `figi`, `ticker`, `uid` уникальны в пределах системы | `models.py` (`unique=True`), миграции 0002, 0003 |
| BR-02 | Обязательные поля: `figi`, `isin`, `name`, `ticker`, `currency`, `uid` (в API `uid` не передаётся) | `models.py`, `ShareModelForm`, `ShareSerializer` |
| BR-03 | Длина: `ticker` ≤ 10 символов, `currency` ≤ 20, остальные строковые ≤ 255 | `models.py` |
| BR-04 | `last_price` и `is_trend_high` необязательны (допускают `NULL`) | `models.py` |
| BR-05 | `updated_at` выставляется автоматически при каждом `save()` и вручную не редактируется | `auto_now=True` |
| BR-06 | Формат FIGI, ISIN и кода валюты **не проверяется**: допустим произвольный текст | — |
| BR-07 | Цена хранится как число с плавающей точкой (`FloatField`), без проверки на неотрицательность | `models.py` |

#### Расчёт цены и тренда

| ID | Правило | Где реализовано |
|---|---|---|
| BR-08 | Текущая цена = целая часть (`units`) последней цены из Tinkoff, дробная часть (`nano`) отбрасывается | `services/market_data.py` |
| BR-09 | Тренд «растёт» (`True`), если новая цена ≥ сохранённой, «падает» (`False`), если новая цена меньше | `tasks.py:16-19` |
| BR-10 | Если предыдущей цены нет (`NULL`), тренд считается «растёт» (через перехват `TypeError`) | `tasks.py:20-22` |
| BR-11 | Если тренд не рассчитан (`NULL`), в списке ячейка подсвечивается красным, как при падении | `list.html` |
| BR-12 | Цены обновляются для **всех** акций справочника каждые 10 секунд; ошибка по одной акции не прерывает обработку остальных | `config/celery.py`, `tasks.py` |
| BR-13 | График строится по дневным свечам (`CANDLE_INTERVAL_DAY`) за 180 дней от текущего момента, по целой части цены закрытия | `services/graph.py` |

#### Доступ и пользователи

| ID | Правило | Где реализовано |
|---|---|---|
| BR-14 | Список и карточку акций видят все, включая анонимов | `ShareListView`, `ShareDetailView` |
| BR-15 | Создание, изменение и удаление через HTML доступно **любому** аутентифицированному пользователю; ролей и владельцев записей нет | `IsUserAuthenticatedMixin` |
| BR-16 | Анониму, обратившемуся к защищённой странице, ошибка не показывается: его перенаправляют на главную | `handle_no_permission` |
| BR-17 | REST API доступен без аутентификации для всех операций | DRF по умолчанию — `AllowAny` |
| BR-18 | Логин пользователя — e-mail; `username` и `email` совпадают | `RegistrationForm.save` |
| BR-19 | При регистрации e-mail должен быть уникален (точное, регистрозависимое сравнение) | `RegistrationForm.clean` |
| BR-20 | Пароль и его подтверждение должны совпадать; требования к сложности **не применяются** | `RegistrationForm.clean` |
| BR-21 | При входе e-mail приводится к нижнему регистру | `AuthView.post` |
| BR-22 | Админ-панель доступна только пользователям с `is_staff` | Django Admin |

#### Ограничения вывода

| ID | Правило | Где реализовано |
|---|---|---|
| BR-23 | HTML-список — по 100 записей на страницу, сортировка по названию | `ShareListView` |
| BR-24 | API — по 100 записей по умолчанию (`limit`/`offset`), сортировка только по `name` и `ticker` | `REST_FRAMEWORK`, `ShareViewSet` |
| BR-25 | Поле `uid` наружу через API не отдаётся и не принимается | `ShareSerializer` |

### 7.4. Дефекты реализации

Уровни критичности: **Критический** — угроза безопасности или потеря данных; **Высокий** — функция работает неверно или падает; **Средний** — некорректное поведение в частных случаях или заметная неэффективность; **Низкий** — качество кода и косметика.

#### Безопасность

| ID | Критичность | Дефект | Место | Последствия |
|---|---|---|---|---|
| DEF-01 | Критический | REST API не требует аутентификации: не заданы `DEFAULT_PERMISSION_CLASSES` и `permission_classes` | `settings.py` (`REST_FRAMEWORK`), `api/v1/views.py` | Любой анонимный клиент может создать, изменить или удалить все акции. Защита HTML-интерфейса обходится через API |
| DEF-02 | Критический | `SECRET_KEY = ""`, `DEBUG = True`, учётные данные БД и `TINKOFF_TOKEN` захардкожены; `.env` не читается | `config/settings.py` | Подписи сессий и CSRF не защищены. Секреты попадают в репозиторий. В режиме DEBUG пользователю показываются трассировки |
| DEF-03 | Средний | Выход выполняется GET-запросом без CSRF-защиты | `user/views.py` (`LogoutView`) | Пользователя можно разлогинить сторонней ссылкой или картинкой |
| DEF-04 | Средний | Валидаторы сложности паролей (`AUTH_PASSWORD_VALIDATORS`) не вызываются при регистрации | `user/forms.py` | Можно зарегистрироваться с паролем «1» |
| DEF-05 | Средний | Пользовательский regex передаётся в БД без проверки (`search_fields=["$name"]`) | `api/v1/views.py` | Некорректное выражение (`?search=(`) → `DataError` в PostgreSQL → 500. Тяжёлые выражения нагружают БД |
| DEF-06 | Низкий | HTML графика выводится с `{% autoescape off %}` | `detail.html` | Сейчас риск низкий (в графике нет пользовательских строк), но любой будущий вывод пользовательских данных в график станет XSS |

#### Обработка ошибок и корректность запросов

| ID | Критичность | Дефект | Место | Последствия |
|---|---|---|---|---|
| DEF-07 | Высокий | Карточка ищет акцию через `Share.objects.get` без `get_object_or_404` | `dashboard/views.py:32` | Несуществующий `id` → 500 вместо 404 |
| DEF-08 | Высокий | `RegistrationForm.clean()` обращается к `cleaned_data["email"]` и `cleaned_data["password1"]` без проверки наличия ключей | `user/forms.py:32-34` | Невалидный или пустой e-mail → `KeyError` → 500 |
| DEF-09 | Высокий | `RegistrationView.post` берёт текст ошибки из `form.errors["__all__"]`, которого нет, если ошибки только у отдельных полей | `user/views.py:54` | Ошибка конкретного поля → `KeyError` → 500 |
| DEF-10 | Высокий | `AuthView.post` не валидирует форму и читает `form.data["email"]` напрямую | `user/views.py:18-19` | POST без поля `email` или `password` → `KeyError` → 500 |
| DEF-11 | Высокий | Отказ или таймаут Tinkoff API при построении графика не обрабатывается | `services/graph.py`, `ShareDetailView` | Без токена или сети карточка любой акции недоступна (500), хотя данные из БД показать можно |
| DEF-12 | Высокий | E-mail при регистрации сохраняется как введён, а при входе приводится к нижнему регистру | `user/forms.py` и `user/views.py` | Пользователь, зарегистрированный как `User@Mail.ru`, не может войти. Возможны «дубликаты», различающиеся только регистром |
| DEF-13 | Высокий | Поле `uid` уникально и обязательно в модели, но исключено из сериализатора: при `POST` в API записывается `uid=""` | `api/v1/serializer.py`, `models.py` | Вторая акция, созданная через API, нарушает `UNIQUE(uid)` → `IntegrityError` → 500 |

#### Обновление цен и интеграция с Tinkoff

| ID | Критичность | Дефект | Место | Последствия |
|---|---|---|---|---|
| DEF-14 | Высокий | Цена берётся только как `price.units`, без `nano` (то же для `candle.close.units`) | `services/market_data.py:11`, `services/graph.py:20` | Цены округляются вниз до целого: 0.0345 → 0, 245.97 → 245. График «ступенчатый», тренд считается неверно |
| DEF-15 | Высокий | Обновление цен делается через `QuerySet.update()`, который не срабатывает `auto_now` | `tasks.py:24-26` | `updated_at` не меняется при обновлении цены; «Время последнего обновления» на карточке недостоверно |
| DEF-16 | Высокий | N+1: отдельное подключение, gRPC-запрос и `UPDATE` на каждую акцию, хотя `get_last_prices` принимает список FIGI | `tasks.py`, `services/market_data.py` | Справочник из 1500+ акций → тысячи запросов за запуск. Задача не укладывается в интервал и упирается в лимиты API |
| DEF-17 | Высокий | Интервал запуска — 10 секунд без защиты от параллельных запусков | `config/celery.py:16` | Запуски накапливаются в очереди и выполняются параллельно. Порядок записи цен и тренда не гарантирован |
| DEF-18 | Высокий | `add_shares` передаёт все поля в `get_or_create` как критерии поиска, а не через `defaults` | `add_shares.py:15-22` | Повторный запуск после изменения любого атрибута акции в Tinkoff → попытка вставить дубликат → `IntegrityError`, команда падает |
| DEF-19 | Средний | `add_shares` работает без транзакции и без обработки ошибок; тикеры длиннее 10 символов не помещаются в поле | `add_shares.py`, `models.py` | Частичная загрузка при сбое; падение на нестандартных тикерах |
| DEF-20 | Средний | Тренд при равной цене и при отсутствии предыдущей цены — «растёт», причём второй случай обрабатывается перехватом `TypeError` | `tasks.py:15-22` | После первой загрузки все акции «растут». В лог пишутся ложные ошибки `'>' not supported between ... NoneType` |
| DEF-21 | Средний | Ошибки в задаче только логируются (`logger.error(e)`), без трассировки и без указания акции | `tasks.py` | Причину сбоя трудно диагностировать |
| DEF-22 | Средний | Карточка синхронно вызывает внешний API при каждом просмотре, без кэша; клиент gRPC создаётся заново | `services/graph.py` | Медленная страница, лишняя нагрузка на API и лимиты |

#### Данные и модель

| ID | Критичность | Дефект | Место | Последствия |
|---|---|---|---|---|
| DEF-23 | Средний | Денежные значения хранятся во `FloatField` | `models.py` | Ошибки округления; для цен принято использовать `DecimalField` |
| DEF-24 | Средний | В форме HTML (`fields="__all__"`) и в API доступны для ручного изменения `last_price` и `is_trend_high` | `forms.py`, `serializer.py` | Пользователь может подменить расчётные данные. Следующий запуск задачи их перезапишет |
| DEF-25 | Низкий | Акции без рассчитанного тренда (`NULL`) отображаются красным, как падающие | `list.html` | Вводящая в заблуждение индикация |

#### Конфигурация, зависимости, инфраструктура

| ID | Критичность | Дефект | Место | Последствия |
|---|---|---|---|---|
| DEF-26 | Высокий | Устаревшие и несовместимые версии: Django 4.1 (без поддержки), `protobuf 3.20`, `grpcio 1.51`, бета-SDK Tinkoff; конфликт `tinkoff==0.1.1` и `tinkoff-investments` в одном пространстве имён | `requirements.txt` | Проект не устанавливается на актуальном Python (3.13). Установленное `.venv` уже не соответствует `requirements.txt` |
| DEF-27 | Средний | Префикс `path("user", ...)` без слэша | `config/urls.py:7` | Адреса `/userlogin/`, `/userregistration/`, `/userlogout/` |
| DEF-28 | Средний | Тесты жёстко привязаны к PostgreSQL (SQLite закомментирован), а `test_share_detail_invalid` и `test_share_delete_invalid` полагаются на «несуществующие» id 2 и 3 | `settings.py`, `tests.py` | Тесты не запускаются без сервера БД; хрупкость при изменении порядка или количества тестов |
| DEF-29 | Средний | Нет тестов HTML-форм, аутентификации, Celery-задачи, сервисов и команды `add_shares` | `tests.py` | Большинство дефектов этого раздела не ловится тестами |
| DEF-30 | Низкий | Plotly.js загружается дважды: `plotly-latest` с CDN без версии и встраивается самим `plotly.offline.plot` (`include_plotlyjs=True` по умолчанию) | `base.html`, `graph.py` | Несколько мегабайт лишнего JS на карточке; непредсказуемая версия |
| DEF-31 | Низкий | Не используются, но подключаются Moment.js, Tempus Dominus, Font Awesome; Bootstrap-классы 4/5 смешаны с crispy-пакетом `bootstrap3` | `base.html`, `settings.py` | Лишняя загрузка; некорректная вёрстка форм |
| DEF-32 | Низкий | `docker-compose.yml` монтирует проект в контейнер PostgreSQL (`./:/app`) и не сохраняет данные БД в volume | `docker-compose.yml` | Бессмысленный mount; данные теряются при пересоздании контейнера |
| DEF-33 | Низкий | Лог-файл `app.logs` пишется по относительному пути; `STATIC_ROOT` не задан | `settings.py` | Расположение логов зависит от каталога запуска; `collectstatic` не работает |

### 7.5. Неоднозначности и противоречия в коде

| ID | Противоречие | Где |
|---|---|---|
| AMB-01 | **Разные правила доступа для одной операции:** в HTML создание, изменение и удаление требуют входа, в REST API — нет | `IsUserAuthenticatedMixin` и `ShareViewSet` |
| AMB-02 | **Разный набор полей в HTML и API:** форма требует `uid`, сериализатор его не знает. Одна и та же сущность создаётся по разным правилам | `forms.py` и `serializer.py` |
| AMB-03 | **Имя расписания противоречит значению:** `"add-every-5-min"`, но `schedule: 10.0` (10 секунд). Непонятно, какой интервал задуман | `config/celery.py` |
| AMB-04 | **Смысл `updated_at`:** на карточке подписан «Время последнего обновления» (подразумевается цена), но фактически это время последнего ручного сохранения записи | `detail.html`, `tasks.py` |
| AMB-05 | **Смысл `is_trend_high`:** назван «Растет цена», но сравнивается только с предыдущим опросом (10 секунд назад), а не с ценой закрытия дня или другим периодом; равенство считается ростом | `models.py`, `tasks.py` |
| AMB-06 | **Часовые пояса:** `TIME_ZONE="UTC"`, `CELERY_TIMEZONE="Europe/Moscow"`; язык `en-us` при полностью русском интерфейсе | `settings.py` |
| AMB-07 | **Конфигурация:** README говорит, что токен задаётся в `settings.py`, а в проекте лежит `.env` с полным набором переменных, которые код не читает | `README.md`, `.env`, `settings.py` |
| AMB-08 | **Реакция на отказ в доступе:** аноним на `/create` молча попадает на главную вместо страницы входа с `?next=` — неясно, ошибка это или намеренное поведение | `handle_no_permission` |
| AMB-09 | **Дублирование фильтров:** `DEFAULT_FILTER_BACKENDS` в настройках перекрывается `filter_backends` во view; фильтр `?name=` (точное совпадение) пересекается с `?search=` (regex по тому же полю) | `settings.py`, `api/v1/views.py` |
| AMB-10 | **Стиль URL:** HTML-маршруты без завершающего слэша (`/create`, `/update/1`), API — со слэшем (`/api/v1/shares/1/`) | `dashboard/urls.py`, DRF router |
| AMB-11 | **Шаблоны получают класс формы вместо экземпляра** (`{"form": AuthForm}`). Это работает только потому, что шаблонизатор Django вызывает callable-объекты | `user/views.py:13, 41` |
| AMB-12 | **Следы копипасты:** docstring `ShareDeleteView` — «Удаление задачи»; в `graph.py` у серии `name="test"`; в `manage.py` и миграциях — «DjangoOld»; переменная `detetime` не используется | разные файлы |

---

## Итог

Investing Demo — небольшой монолит на Django 4.1. В нём одна прикладная сущность (`Share`) и два интерфейса к ней: HTML на generic CBV и REST на DRF ModelViewSet. Данные поступают из Tinkoff Invest API тремя путями: разовая загрузка справочника, периодическое обновление цен через Celery+Redis и синхронная загрузка исторических свечей при просмотре карточки.

Основные технические недостатки, которые стоит учесть при модернизации:

- секреты захардкожены, `.env` не используется;
- REST API открыт для анонимной записи;
- обработка ошибок отсутствует — 500 на несуществующую акцию и некорректные формы;
- неэффективная задача обновления цен: N запросов каждые 10 секунд, к тому же не обновляет `updated_at`;
- цены теряют точность (`units` без `nano`);
- `add_shares` хрупкая;
- зависимости устарели и конфликтуют.
