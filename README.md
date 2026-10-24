# DroidFleet — device fleet orchestration platform

**Русская версия** · [English version](README.en.md)

DroidFleet — это кроссплатформенная платформа для управления фермой устройств,
подключённых через Android ADB, узлов FarmAgent и управляемых ПК-систем.
Основной GUI работает на Windows, а безопасная серверная часть рассчитана на
HTTPS/self-host deployment без постоянного публичного туннеля.

Поддержка ПК-систем означает, что система может управлять не только Android-устройствами,
но и Windows/Linux хостами, которые участвуют в оркестрации, мониторинге и
массовых операциях наравне с мобильными целями.

Проект ориентирован на Python 3.13, использует шифрование секретов в
`data/accounts.enc`, хранит критичные данные в безопасном хранилище и
предотвращает работу по HTTP по умолчанию. Историческое имя
`AndroidController` осталось в коде как совместимость, но фактически это общий
UI-контроллер и оркестратор Android + Windows контуров.

## Ключевые возможности

- автоматическое обнаружение Android-устройств, ПК-систем и статусный мониторинг;
- карточки устройств с моделью, ОС, SDK, RAM, battery, temperature, ADB/IP и состоянием;
- встроенный scrcpy preview внутри главного окна;
- массовые операции с устройствами: screenshot, reboot, reconnect, install/uninstall APK, shell по allowlist;
- просмотр logcat, фильтрация, очистка и экспорт;
- работа с Windows/Linux FarmAgent: heartbeat, screenshots, логи, процессы, remote update, file transfer;
- отдельный Android APK-агент с заранее сконфигурированным endpoint;
- безопасный по умолчанию transport: HTTPS-only для удалённого `SERVER_URL`, `localhost` только при explicit opt-in;
- шифрованное хранение импортированных учётных записей в `data/accounts.enc`.

## Архитектура

- GUI: основной управляющий интерфейс DroidFleet на Windows;
- Android transport: `adb` через `AdbClient` и `DeviceMonitor`;
- ПК-системы: подключение и мониторинг хостов через локальный и сетевой контрольный слой;
- Windows/Linux FarmAgent: heartbeat и команды через HTTPS/self-host endpoint;
- Accounts: `app/accounts/repository.py` хранит импортированные записи в encrypted-at-rest хранилище (`data/accounts.enc`);
- Device/task runtime state: хранится через локальный registry layer проекта; критичные учётные данные не сохраняются в открытом виде;
- Logs/screenshots: `data/logs` и `data/screenshots` используются для пользовательских артефактов и аудита.

## Поддерживаемые платформы

| Компонент | Windows | Linux/macOS |
|---|---|---|
| Python runtime | Поддерживается | Поддерживается |
| GUI DroidFleet | Основная платформа | Не является primary production scenario |
| Android ADB | Поддерживается | Поддерживается |
| Embedded scrcpy | Поддерживается | Не поддерживается |
| FarmAgent input/screenshot | Полная реализация | Поддерживается при наличии desktop session |

## Установка

Требования: Windows 10/11 и Python 3.13.

1. Установите Python 3.13 с сайта <https://www.python.org/downloads/>.
2. Установите Android Platform Tools и убедитесь, что `adb.exe` доступен в `PATH`:

   ```powershell
   $env:DROIDFLEET_ADB = "C:\tools\platform-tools\adb.exe"
   ```

3. Клонируйте проект и установите зависимости:

   ```powershell
   py -3.13 -m pip install -e .
   ```

4. Запустите GUI:

   ```powershell
   py -3.13 farm_bot.py
   ```

   Альтернативно:

   ```powershell
   py -3.13 -m app.main
   ```

## Конфигурация соединения

Production profile использует только HTTPS endpoint. `localhost` / loopback допустим только при явном включении:

```powershell
$env:DROIDFLEET_SERVER = "https://server.example/api/agent/heartbeat"
$env:DROIDFLEET_ALLOW_INSECURE_LOOPBACK = "true"  # только для локального debug
```

Поддерживаются только безопасные сценарии:

- `self-host` на защищённой внутренней сети;
- `external server` с HTTPS endpoint;
- `localhost` только для локального отладки и только при разрешении.

## FarmAgent

Сервер DroidFleet работает на порту `8765`. Запуск агента вручную:

```powershell
$env:DROIDFLEET_SERVER = "https://server.example/api/agent/heartbeat"
py -3.13 agent/agent.py
```

Сборка автономного Windows-агента:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_agent.ps1
```

Результат будет сохранён в `dist/FarmAgent.exe`. Для запуска процессов используйте
переменные окружения `DROIDFLEET_ROBLOX`, `DROIDFLEET_PYTHON_BOT` и
`DROIDFLEET_FARM_WORKER`.

### Linux FarmAgent

На Linux установите Python 3.13, `adb` при необходимости и выполните:

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv
chmod +x build_agent.sh
DROIDFLEET_SERVER="https://your-server.example/api/agent/heartbeat" \
  ./build_agent.sh
```

Готовый бинарник будет в `dist/FarmAgent-linux`.

## Android FarmAgent APK

Отдельный Android-клиент находится в [android-agent/](android-agent/). Он отправляет
heartbeat напрямую на заранее настроенный `FLEET_SERVER_URL` без замены ADB-контуров.

Перед сборкой задайте URL в `android-agent/app/build.gradle.kts`:

```kotlin
buildConfigField("String", "FLEET_SERVER_URL",
    "\"https://your-server.example/api/agent/heartbeat\"")
```

Сборка:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_android_agent.ps1 `
  -ServerUrl "https://your-server.example/api/agent/heartbeat"
```

## Безопасность и хранение

Проект следует production-safe defaults:

- HTTPS-only для удалённых endpoint;
- loopback только при `DROIDFLEET_ALLOW_INSECURE_LOOPBACK=true`;
- хеширование пинов/токенов перед сохранением;
- шифрование секретов в `data/accounts.enc` вместо открытого JSON с паролями;
- ограничение пути и размера файлов при transfer;
- маскирование секретов в логах.

## Данные и логи

- Accounts: `data/accounts.enc`
- Runtime registry и состояние задач: локальная директория данных проекта, без хранения секретов в открытом виде
- GUI logs: `data/logs`
- Screenshots: `data/screenshots`
- FarmAgent log: `%PROGRAMDATA%\DroidFleet\agent.log`

## Запуск через CLI

```powershell
py -3.13 -m app.cli --help
```

См. также [docs/production_security.md](docs/production_security.md) для production-hardening checklist.
