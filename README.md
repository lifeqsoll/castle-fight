# Castle Fight

Castle Fight — стратегия в реальном времени на одной линии: стройте здания, собирайте армию, улучшайте её и защищайте замок. Можно играть против бота или по локальной сети вдвоём.

## Возможности

- 6 фракций, 2 игровых режима и автоматический бой юнитов.
- Строительство, перестановка и продажа зданий; апгрейды армии.
- Лавка: меч героя, усиления, ремонт замка и бомбы.
- Боты, режим без графического интерфейса и инструменты для проверки баланса.
- Сетевая игра по LAN с автоматическим поиском соперника и синхронизацией состояния.
- Русский интерфейс, встроенные изображения и шрифты.

## Требования

- Python 3.12 или новее.
- Windows 10/11, Linux или macOS.
- Для сетевой игры два компьютера должны быть доступны друг другу в локальной сети.

Зависимости проекта перечислены в `requirements.txt`. Графика загружается из каталога проекта; для запуска из исходников отдельные системные библиотеки SDL устанавливать не требуется.

## Запуск из исходников

Все команды выполняются из корня проекта.

### Windows

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m castlefight.ui.main
```

Если команда активации заблокирована политикой PowerShell, используйте `.\.venv\Scripts\python.exe` вместо `python` для следующих команд.

### Linux и macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m castlefight.ui.main
```

Для выхода из виртуального окружения выполните `deactivate`.

## Управление

| Действие | Управление |
|---|---|
| Играть / подтвердить выбор | `Enter` |
| Выбрать фракцию | клик или `A` / `D`; режим — `Tab` |
| Построить здание | `1`–`4` или карточка, затем клик по свободной клетке |
| Продолжить стройку | удерживать `Shift` при размещении |
| Переместить здание | перетащить его в свободную клетку |
| Продать здание | ПКМ по зданию или `X`, затем подтвердить |
| Ударить вражеского юнита | ЛКМ по нему |
| Купить предмет в лавке | `Q` ярость, `W` каменная кожа, `E` ремонт, `R` бомба, `T` меч |
| Улучшить армию | `U` |
| Отменить текущее действие | `Esc` |
| Изменить скорость / пауза | `F` или клик по панели скорости / `Пробел` |

Ускорение и пауза доступны только в одиночном матче. В сетевой игре темп задаёт хост; `Esc` завершает сетевой матч и возвращает в сетевое меню.

## Игра по локальной сети

1. На обоих компьютерах запустите игру и выберите **По сети**.
2. На первом компьютере выберите **Создать игру**, фракцию и режим.
3. На втором выберите **Подключиться** и игру из списка. Если автопоиск не сработал, укажите IP-адрес хоста вручную.
4. Если система запросит разрешение брандмауэра, разрешите соединение в частной сети.

Для поиска игр используется UDP-порт `47820`, для матча — TCP-порт `47821`. Если соединение блокируется, разрешите эти порты в брандмауэре. Сетевой режим рассчитан на локальную сеть, не на подключение через интернет. На время матча хост рассылает команды и состояние симуляции; оба клиента должны использовать одну версию игры.

## Тесты и инструменты

```bash
python -m pytest -q
python -m castlefight.tools.skirmish
python -m castlefight.tools.run_headless Королевство Орда --mode normal --seed 1
python -m castlefight.tools.balance_check normal 4
python -m castlefight.tools.balance_v3 normal 8
python -m castlefight.tools.ui_smoke screenshots
python -m castlefight.ai.advisor --matches 2000 --eval 40
```

Команда обучения создаёт одну модель `HistGradientBoostingClassifier` из scikit-learn, проверяет её точность на отложенной выборке и сохраняет для советника и ML-бота. После обучения модель используется для подсказок и выбора соперника в одиночной игре; без файла модели остаётся обычный бот. Модель от прежней версии нужно обучить заново.

Тесты покрывают игровое ядро, экономику, LAN-соединение, подбор игр и отрисовку. `ui_smoke` запускает интерфейс в тестовом режиме и сохраняет снимки экранов.

## Сборка приложения

PyInstaller не выполняет кросс-компиляцию: собирать приложение нужно на целевой ОС и для целевой архитектуры. Перед сборкой активируйте виртуальное окружение и установите зависимости проекта, затем установите PyInstaller:

```bash
python -m pip install pyinstaller
```

### Windows

Из корня проекта в PowerShell:

```powershell
python -m PyInstaller --noconfirm --clean --windowed --name CastleFight --paths . --add-data "castlefight\assets;castlefight\assets" --add-data "castlefight\ai\advisor_model.joblib;castlefight\ai" --collect-all pygame --collect-all PIL --hidden-import castlefight.ai.advisor castlefight\ui\main.py
```

Готовое приложение появится в `dist\CastleFight\CastleFight.exe`.

### Linux

```bash
python -m PyInstaller --noconfirm --clean --windowed --name CastleFight --paths . --add-data "castlefight/assets:castlefight/assets" --add-data "castlefight/ai/advisor_model.joblib:castlefight/ai" --collect-all pygame --collect-all PIL --hidden-import castlefight.ai.advisor castlefight/ui/main.py
```

Запускаемый файл будет в `dist/CastleFight/CastleFight`. Для совместимости с разными дистрибутивами собирайте на самой старой из целевых версий Linux: бинарный файл может зависеть от версии системной `glibc`.

### macOS

```bash
python -m PyInstaller --noconfirm --clean --windowed --name CastleFight --paths . --add-data "castlefight/assets:castlefight/assets" --add-data "castlefight/ai/advisor_model.joblib:castlefight/ai" --collect-all pygame --collect-all PIL --hidden-import castlefight.ai.advisor castlefight/ui/main.py
```

Приложение появится в `dist/CastleFight.app`. Сборку выполняйте на macOS для нужной архитектуры (Apple Silicon или Intel). Для распространения вне своего компьютера приложение может потребовать подписи и нотариализации Apple.

PyInstaller включает интерпретатор Python и зависимости в каталог сборки. Перед распространением проверьте готовую сборку на чистой системе соответствующей ОС.

## Структура проекта

- `castlefight/core/` — игровая симуляция, экономика, игроки, команды и лавка.
- `castlefight/data/` — фракции, типы юнитов и баланс.
- `castlefight/ai/` — игровые боты и ML-советник.
- `castlefight/net/` — сетевой матч и поиск игр в локальной сети.
- `castlefight/ui/` — интерфейс на pygame-ce, отрисовка и обработка ввода.
- `castlefight/assets/` — изображения, значки и шрифты.
- `castlefight/tools/` — запуск матчей без окна, проверка баланса и UI smoke-тесты.
- `tests/` — автоматические тесты.
- `balance_sim/` — симулятор для экспериментов с балансом.
