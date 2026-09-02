# Архитектура

`app.main.AndroidController` связывает слои приложения и владеет жизненным циклом Tkinter.

- ADB: `AdbClient` выполняет процессы, `DeviceMonitor` сообщает список online-устройств.
- Video: `PreviewService` выполняет screencap в фоне, `ScrcpyStream` управляет полноэкранным потоком.
- Actions: функции формируют операции, `BatchExecutor` распределяет их по устройствам.
- UI: `Toolbar`, `Dashboard` и `DeviceCard` не выполняют ADB напрямую.
- APK: локальный файл выбирается в UI и устанавливается на targets через `adb install -r`.
- Groups: производитель и модель из hardware monitoring используются для фильтрации карточек.
- Accounts: `app/accounts/repository.py` ведёт локальный JSON-каталог импортов в `data/accounts.json`.
