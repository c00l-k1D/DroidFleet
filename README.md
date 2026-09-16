# DroidFleet — device fleet orchestration platform

**Русская версия** · [English version](README.en.md)

DroidFleet — кроссплатформенная платформа управления фермой устройств и
оркестрации рабочих узлов. Основной GUI работает на Windows и управляет
Android через ADB, а Windows-компьютерами — через FarmAgent. Протокол
FarmAgent и серверная часть не привязаны к Android и могут использоваться для
управления Windows-узлами через LAN, ngrok или внешний сервер.

Историческое имя класса главного контроллера — `AndroidController`; фактически
это общий UI-контроллер и оркестратор Android- и Windows-контуров.

## Возможности

- автоматическое обнаружение Android-устройств в состояниях `device`,
  `offline` и `unauthorized`;
- обновление списка без перезапуска программы;
- карточки Android с моделью, Android, SDK, RAM, storage, battery,
  temperature, resolution, ADB/IP и статусом;
- превью экранов Android в карточках и настоящий встроенный scrcpy-поток
  внутри главного окна (с управлением мышью и клавиатурой, без отдельного окна);
- массовые screenshot, reboot, reconnect, shell, установка и удаление APK,
  очистка данных, запуск и остановка приложений;
- полноценный просмотр logcat выбранного Android с фильтром, очисткой буфера
  и экспортом в файл;
- выбор устройств и очередь worker-задач с ограничением параллелизма;
- отдельные ошибки одного устройства не останавливают остальные операции;
- группы, теги, поиск, фильтры и сохранение базы устройств;
- FarmAgent для Windows: heartbeat с RTT ping, процессы, screenshot, logs,
  update, live view, remote access и передача файлов между ПК;
- отдельный Android FarmAgent APK с заранее заданным URL сервера;
- режимы подключения `self-host`, `ngrok`, `external server`;
- Android подключается отдельно через локальный ADB: `auto`, `USB` или
  `Wi-Fi ADB`; этот транспорт не использует ngrok;
- логирование в `data/logs` и экспорт screenshot в `data/screenshots`.

## Поддерживаемые платформы и границы

| Контур | Windows | Linux/macOS |
|---|---|---|
| Python-пакет и FarmAgent-протокол | Поддерживается | Поддерживается |
| GUI DroidFleet | Основная платформа | Не проверялся как production-сценарий |
| Android ADB | Поддерживается при установленном `adb` | Поддерживается при установленном `adb` |
| Встроенный scrcpy | Windows embedding | Не поддерживается |
| FarmAgent input/screenshot | Полная реализация Windows | Поддерживается через `pyautogui`/`Pillow` при наличии desktop session |

Для GUI необходимы `tkinter`, Android Platform Tools и при использовании
встроенного просмотра `scrcpy`. Linux FarmAgent запускается как обычный
Python-процесс или systemd-сервис, использует `adb` из `PATH` и сообщает
платформу `Linux` в карточке хоста. Для screenshot/input на Linux нужна
доступная графическая сессия (`DISPLAY` или Wayland-совместимая среда).

## Установка с нуля

Требуется Windows 10/11 и Python 3.10 или новее.

1. Установите Python с сайта <https://www.python.org/downloads/>.
   При установке включите `Add Python to PATH`.
2. Установите Android Platform Tools и убедитесь, что `adb.exe` доступен
   через `PATH`, либо задайте путь:

   ```powershell
   $env:DROIDFLEET_ADB = "C:\tools\platform-tools\adb.exe"
   ```

3. Клонируйте или распакуйте проект и перейдите в его каталог:

   ```powershell
   cd "C:\path\to\Ферма"
   ```

4. Установите проект и зависимости:

   ```powershell
   py -3 -m pip install -e .
   ```

5. Запустите GUI:

   ```powershell
   py -3 farm_bot.py
   ```

   Альтернативно:

   ```powershell
   py -3 -m app.main
   ```

### ADB и телефоны

Включите USB debugging на Android и подтвердите RSA-запрос на устройстве.
Проверьте подключение:

```bash
adb devices
```

Устройство должно иметь состояние `device`. Для Wi-Fi ADB используйте
стандартные команды `adb tcpip` и `adb connect`. DroidFleet и scrcpy используют
один и тот же найденный ADB-бинарник; это предотвращает зависание из-за
конфликтующих ADB-серверов. По умолчанию DroidFleet использует отдельный
порт ADB `5038`, а не общий `5037`; порт можно изменить через
`DROIDFLEET_ADB_SERVER_PORT`.

В настройках DroidFleet параметр `Android ADB transport` задаёт режим по
умолчанию. В подробностях конкретного Android можно выбрать собственный
режим `auto`, `usb` или `wifi`. Подпись `NGROK` относится только к карточкам
Windows FarmAgent.

## Управление GUI

- ЛКМ по Android-карточке выбирает устройство.
- ПКМ открывает меню Android: встроенный scrcpy, отдельный scrcpy, reconnect,
  подробности, задания и группы.
- Пункт «встроенный scrcpy» запускает scrcpy как дочерний элемент главного
  окна. ADB используется только как транспорт Android, вручную вводить
  команды для просмотра экрана не требуется.
- ЛКМ по Windows-карточке выбирает FarmAgent.
- Двойной ЛКМ открывает управление Windows-агентом.
- ПКМ по Windows-карточке открывает live view, remote access, screenshot,
  logs, задания и группы.
- Кнопка `РУКОВОДСТВО / GUIDE` в верхней панели открывает встроенную
  краткую инструкцию на русском и английском.

## FarmAgent

Сервер DroidFleet слушает порт `8765`. Для запуска агента вручную:

```powershell
$env:DROIDFLEET_SERVER = "http://SERVER_IP:8765/api/agent/heartbeat"
py -3 agent/agent.py
```

Для сборки автономного агента:

```powershell
powershell -ExecutionPolicy Bypass -File build_agent.ps1
```

Результат появится в `dist/FarmAgent.exe`. Команды запуска процессов задаются
в настройках DroidFleet или переменными `DROIDFLEET_ROBLOX`,
`DROIDFLEET_PYTHON_BOT`, `DROIDFLEET_FARM_WORKER`.
Скрипт сборки при необходимости скачивает официальный Windows Platform Tools
и вкладывает `adb.exe` с DLL внутрь EXE. Для корпоративной сети без доступа к
Google скачайте архив Platform Tools вручную в каталог `platform-tools`.

### Linux FarmAgent

На Linux-системе установите Python 3.10+, `adb` (если нужны Android-устройства)
и выполните:

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv
chmod +x build_agent.sh
DROIDFLEET_SERVER="https://your-server.example/api/agent/heartbeat" \
  ./build_agent.sh
```

Результат: `dist/FarmAgent-linux`. Передайте его на Linux-PC и запустите:

```bash
chmod +x FarmAgent-linux
DROIDFLEET_SERVER="https://your-server.example/api/agent/heartbeat" \
  ./FarmAgent-linux
```

Linux-агент получает стабильный идентификатор `linux-*`, хранит состояние в
`~/.local/state/droidfleet` и может работать как обычный процесс или systemd
service. Кнопка «Собрать Linux FarmAgent» также доступна в GUI, если на хосте
установлен Bash/WSL.

FarmAgent включает Android Platform Tools (`adb.exe`) при сборке, обнаруживает
подключённые к управляемому Windows-ПК Android-устройства и передаёт их список
на хост. В карточке Windows отображается количество и модели Android-устройств.
FarmAgent показывает RTT последнего heartbeat в карточке Windows, пишет
журнал в `%PROGRAMDATA%\DroidFleet\agent.log`, поддерживает ротацию логов,
передачу файлов с SHA-256 и удалённое обновление собранного EXE.

### Android FarmAgent APK

В проект добавлен отдельный нативный Android-клиент в [android-agent/](android-agent/).
Он не использует ADB и не подменяет Android-контур DroidFleet: APK напрямую
отправляет heartbeat на заранее прописанный endpoint сервера и отображается
как отдельный агент.

Перед сборкой укажите URL в `android-agent/app/build.gradle.kts`:

```kotlin
buildConfigField("String", "FLEET_SERVER_URL",
    "\"https://your-server.example/api/agent/heartbeat\"")
```

Сборка:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_android_agent.ps1 `
  -ServerUrl "https://your-server.example/api/agent/heartbeat"
```

APK появится в `android-agent/app/build/outputs/apk/release/app-release.apk`.
При первом запуске Android попросит разрешение на уведомления/фоновую работу
в зависимости от версии системы. Сервис использует foreground notification,
чтобы Android не останавливал heartbeat.

### Настройка запуска процессов

FarmAgent не угадывает путь к Roblox или боту и не запускает произвольную
команду из сети. Для каждого процесса нужно один раз задать переменную
окружения **на том Windows-PC, где работает FarmAgent**. Например, в обычном
PowerShell:

```powershell
[Environment]::SetEnvironmentVariable(
  "DROIDFLEET_ROBLOX",
  "C:\Games\Roblox\RobloxPlayerBeta.exe",
  "User"
)
[Environment]::SetEnvironmentVariable(
  "DROIDFLEET_PYTHON_BOT",
  "C:\Farm\venv\Scripts\python.exe C:\Farm\bot.py",
  "User"
)
[Environment]::SetEnvironmentVariable(
  "DROIDFLEET_FARM_WORKER",
  "C:\Farm\FarmWorker.exe",
  "User"
)
```

Для Roblox агент сначала использует `DROIDFLEET_ROBLOX`, а если переменная не
задана, автоматически ищет последний `RobloxPlayerBeta.exe` в стандартной
папке `%LOCALAPPDATA%\Roblox\Versions`. Если Roblox установлен в другом месте,
задайте переменную явно. После изменения переменных полностью перезапустите FarmAgent, потому что
переменные окружения читаются при старте процесса. Если переменная не задана,
команда `START` возвращает понятную ошибку вместо падения агента. Команда
`STATUS` показывает для каждого процесса поле `configured`.

### Подключение

- `self-host`: управляющий компьютер и агент находятся в одной LAN;
- `ngrok`: используется публичный URL ngrok и Agent Authtoken;
- ошибки `SSL: UNEXPECTED_EOF_WHILE_READING` относятся к разорванному TLS-туннелю FarmAgent/ngrok, а не к Android ADB. Агент повторяет запросы с backoff и ограничивает одинаковые предупреждения в журнале;
- Windows FarmAgent поддерживает передачу файлов через кнопку `SEND FILE`: файл передаётся по текущему self-host/ngrok/external server каналу, проверяется SHA-256 и сохраняется в указанное место (по умолчанию `Downloads`, лимит 50 МБ);
- журнал FarmAgent одновременно выводится в консоль и сразу записывается в `%PROGRAMDATA%\DroidFleet\agent.log`; файл ротируется после 5 МБ, старые копии сохраняются до трёх файлов;
- карточка Windows FarmAgent показывает RTT последнего heartbeat (`Ping`, миллисекунды); значение обновляется автоматически при каждом heartbeat;
- при кратком обрыве TLS/ngrok FarmAgent создаёт новый SSL-контекст на каждой повторной попытке и повторяет запрос с backoff; проверять доступность туннеля можно по `/api/agent/config`;
- несколько FarmAgent могут одновременно работать через один ngrok endpoint; polling по умолчанию выполняется раз в 1 секунду с небольшим случайным сдвигом, чтобы агенты не создавали синхронный пик запросов;
- `external server`: указывается внешний URL endpoint.

Не храните токены в исходном коде. Передавайте их через настройки или
переменные окружения. Для LAN откройте TCP-порт `8765` в Windows Firewall.

## CLI

После установки проекта в editable-режиме:

```powershell
py -3 -m pip install -e .
droidfleet devices
droidfleet info --all
droidfleet screenshot --all --output data/screenshots
droidfleet reconnect --group samsung
droidfleet reboot --group samsung
```

## Данные, логи и обновление

- база устройств: `data/devices.json`;
- сохранённые Android-карточки восстанавливаются при запуске и показываются как `OFFLINE`, пока ADB не вернёт устройство;
- в контекстном меню Android доступны отключение ADB Wi-Fi и удаление записи устройства;
- постоянные задания: `data/tasks.json`;
- аккаунты: `data/accounts.json`;
- логи: `data/logs`;
- screenshot: `data/screenshots`;
- настройки читаются из конфигурации проекта и переменных окружения;
- FarmAgent обновляется через кнопку `UPDATE` после сборки нового EXE; если `FarmAgent-start.cmd` не опубликован рядом с EXE, агент создаёт launcher локально и всё равно завершает обновление;
- результаты и ошибки операций пишутся в лог, а screenshot сохраняются
  локально.

Не удаляйте `data`, если нужно сохранить группы, имена, историю и задания. Для очистки
локального состояния остановите DroidFleet и удалите только нужные файлы
`data/devices.json`, `data/accounts.json`, `data/logs` или `data/screenshots`.
Для Android очистка приложения выполняется кнопкой `Очистить данные приложения`
(`adb shell pm clear`), а полное удаление — кнопкой `Удалить приложение`
(`adb uninstall`). Эти операции требуют package name и выбранные устройства.
Для полного удаления Python-зависимостей используйте отдельное виртуальное
окружение и удалите его после остановки программы.

## Проверка проекта

Запустите:

```powershell
py -3 -m pytest -q
py -3 -m compileall -q app agent tests
```

## Чек-лист текущего состояния

| Требование | Статус |
|---|---|
| Обнаружение подключения/отключения ADB | Реализовано |
| 5–10 устройств | Архитектура рассчитана; нагрузочный прогон не включён |
| Модель, Android, SDK, RAM, storage, battery, temperature, resolution, IP, status | Реализовано |
| APK install, launch, stop, reboot, screenshot, shell | Реализовано |
| Uninstall, cleanup и полноценный logcat в GUI | Реализовано |
| Очередь задач | Реализовано: worker-пулы и очередь FarmAgent |
| Ошибка одного устройства не валит процесс | Реализовано обработчиками ошибок |
| Повторное появление после USB reconnect | Реализовано монитором |
| Логирование ошибок | Реализовано |
| Конфиг и сохранение настроек | Реализовано |
| База устройств/задач | Реализовано: `data/devices.json` и `data/tasks.json` |
| GUI/dashboard | Реализовано |
| Экспорт логов/результатов | Реализовано для logcat и screenshot; общий экспорт журнала GUI не добавлен |
| Механизм обновления | Реализован для FarmAgent |
| Установка с нуля | Описана выше |
| Uninstall/cleanup | Android uninstall/cleanup реализованы; отдельного скрипта удаления DroidFleet нет |
| Нет захардкоженных секретов | Реализовано |
| Несколько часов непрерывной работы | Нужен отдельный длительный нагрузочный прогон |

Текущая версия проекта — `0.3.0`. Это alpha-версия: unit-тесты и компиляция
проходят, но нагрузочный прогон на 5–10 физических устройств и длительный
soak-тест ещё должны выполняться отдельно перед выпуском `1.0`.
