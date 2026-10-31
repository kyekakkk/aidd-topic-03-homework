# investing

# Установка
pip install -r requirements.txt
# (для разработки: pip install -r requirements-dev.txt)

# Настройки
cp .env.example .env
# заполните DJANGO_SECRET_KEY, TINKOFF_TOKEN; DB_ENGINE=sqlite3 или postgresql

# PostgreSQL и Redis (Docker)
docker-compose up

# База данных и запуск
python manage.py migrate
python manage.py runserver

# Источники данных
# 1. Московская биржа (MOEX ISS) — по умолчанию, без токена и регистрации:
#    акции режима TQBR, котировки (с задержкой ~15 минут) и дневные свечи.
#    https://iss.moex.com/iss/reference/
# 2. T-Invest API — если в .env задан TINKOFF_TOKEN (REST-шлюз TINVEST_API_URL).
#    Если сертификат invest-public-api.tbank.ru не проходит проверку, укажите в
#    TINVEST_CA_BUNDLE путь к PEM с корневым сертификатом НУЦ Минцифры.
# Источник определяется для каждой акции (FIGI вида MOEX-SBER — биржа).

# Загрузка списка акций (повторный запуск обновляет данные).
# auto — T-Invest при наличии токена, иначе MOEX. Акции с биржи при импорте
# из T-Invest получают настоящий FIGI, история и портфели сохраняются.
python manage.py add_shares
python manage.py add_shares --source moex

# История цен
# Накапливается автоматически при каждом обновлении цен (задача Celery).
# Загрузить дневные свечи за прошлый период (по умолчанию — для акций
# из портфелей и списков наблюдения; --all — для всех, --ticker SBER — выборочно):
python manage.py load_price_history --days 365
# Демо-акции DEMOA/DEMOB/DEMOC с вымышленной историей — для проверки без токена:
python manage.py seed_demo_history

# Страницы
# /dynamics/            — динамика рынка за период
# /<id>/history/        — история цены акции, график и изменения по дням
# /watchlists/          — списки наблюдения и целевые уровни (после входа)
# /portfolio/           — виртуальный портфель (после входа)
# /strategies/          — симулятор стратегий: бэктест на истории цен
#                         и журнал виртуальных сделок (после входа)

# Celery Beat (обновление цен каждые 5 минут)
celery -A config beat

# Celery Worker
celery -A config worker -l info

# Celery Worker для Windows
celery -A config worker -l info -P solo

# Тесты
python manage.py test

# API
# /api/v1/shares/ — работа с акциями (чтение — всем, изменение — после входа)
# Вход и регистрация: /user/login/, /user/registration/
