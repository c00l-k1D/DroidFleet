# Архитектура

`app.main.AndroidController` — историческое имя главного контроллера. На
практике он является UI-контроллером и оркестратором DroidFleet: управляет
Android ADB-контуром, Windows FarmAgent и общим жизненным циклом Tkinter.

- Android transport: `AdbClient` выполняет процессы, `DeviceMonitor` сообщает список online-устройств.
- Windows transport: `AgentServer` принимает heartbeat/команды FarmAgent через
  self-host, ngrok или внешний endpoint.
- Video: `PreviewService` выполняет screencap в фоне, `ScrcpyStream` управляет полноэкранным потоком.
- Actions: функции формируют операции, `BatchExecutor` распределяет их по устройствам.
- UI: `Toolbar`, `Dashboard`, `DeviceCard` и `AgentCard` не выполняют транспортные операции напрямую.
- APK: локальный файл выбирается в UI и устанавливается на targets через `adb install -r`.
- Groups: производитель и модель из hardware monitoring используются для фильтрации карточек.
- Accounts: `app/accounts/repository.py` ведёт локальный JSON-каталог импортов в `data/accounts.json`.
- Shared state: реестры устройств и задач сохраняются в JSON, а FarmAgent хранит
  локальный журнал с ротацией.
