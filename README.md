# DroidFleet

Tkinter-приложение для управления Android-устройствами через ADB и запуска scrcpy.

## Запуск

1. Установите Python 3.10+ и Pillow: `py -3 -m pip install -r requirements.txt`.
2. Убедитесь, что `adb` доступен в `PATH`. `scrcpy` нужен для потокового окна.
3. Запустите `py -3 -m app.main` или совместимый `py -3 farm_bot.py`.

Если ADB или scrcpy не добавлены в `PATH`, задайте путь к ним перед запуском:
`$env:DROIDFLEET_ADB = "C:\\tools\\scrcpy\\adb.exe"`, `$env:DROIDFLEET_SCRCPY = "C:\\tools\\scrcpy\\scrcpy.exe"`.
Можно указать общую папку комплектом: `$env:DROIDFLEET_TOOLS = "C:\\tools\\scrcpy"`.

CLI после установки проекта (`py -3 -m pip install -e .`): `droidfleet devices`, `droidfleet exec --all "input keyevent KEYCODE_HOME"`, `droidfleet reboot --group samsung`. Для GUI используйте `droidfleet gui`, а для отдельного веб-интерфейса — `droidfleet web` и открыть `http://127.0.0.1:8000`.

Отдельный веб-интерфейс — простая страница в стиле DroidLeet: список онлайн-устройств, кнопка `CONNECT` и отдельный view под конкретное устройство. Он не заменяет Tkinter GUI, а служит облегчённым вариантом для быстрой проверки подключения и выбора девайса.

ADB считает устройство доступным только в состоянии `device`. Превью экрана получает отдельный worker-пул и не меняет ADB-состояние.

В панели управления доступна массовая установка APK: выберите локальный файл и target-группу устройств. Фильтр групп строится автоматически по производителю и модели, например `Samsung`, `Xiaomi` или `Lenovo Tab M10`.

Для каждого устройства сохраняются стабильный `device_id`, пользовательское имя, группа и теги в `data/devices.json`. Карточка также показывает модель, Android, IP, батарею, CPU, RAM, температуру и `Last Seen`; статусы: `ONLINE`, `BUSY`, `OFFLINE`, `ERROR`.

## Windows Agent

На сервере DroidFleet запускается endpoint агентов на порту `8765`. На Windows-PC задайте адрес сервера и запустите агент:
`$env:DROIDFLEET_SERVER = "http://SERVER_IP:8765/api/agent/heartbeat"`, затем `py -3 agent/agent.py`.
Для сборки автономного файла выполните `powershell -ExecutionPolicy Bypass -File build_agent.ps1`; результат будет в `dist/FarmAgent.exe`.
Панель `Windows` показывает hostname, Windows, IP, CPU, RAM и актуальный статус агента.
Команды управления не выполняют произвольный shell: Agent принимает только `START`, `STOP`, `RESTART`, `STATUS`, `SCREENSHOT` и `GET_LOGS`. Для запуска процессов задайте на Windows-PC переменные `DROIDFLEET_ROBLOX`, `DROIDFLEET_PYTHON_BOT` и `DROIDFLEET_FARM_WORKER` с командами запуска.
Периодические кадры включаются переменной `DROIDFLEET_SCREENSHOT_INTERVAL` в секундах; качество JPEG задаётся через `DROIDFLEET_SCREENSHOT_QUALITY`, а админский `LIVE VIEW` ограничен `DROIDFLEET_SCREENSHOT_FPS`.

Импортированные аккаунты регистрируются в `data/accounts.json`. Файл содержит имя исходного файла, serial устройства, дату импорта и destination на устройстве; пароли, cookie и токены туда не сохраняются.

## Структура

- `app/adb` - поиск ADB, команды и монитор устройств.
- `app/video` - screencap-декодирование, превью и scrcpy.
- `app/actions` - одиночные и массовые действия.
- `app/ui` - Tkinter dashboard и компоненты интерфейса.
