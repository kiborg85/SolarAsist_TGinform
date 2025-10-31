# Solar Assistant Grid Telegram Notifier

## Опис

Solar Assistant Grid Telegram Notifier — це Python-скрипт, який відстежує MQTT-події від Solar Assistant і надсилає сповіщення в Telegram про появу чи зникнення міської мережі, перевищення навантаження та стан заряду батареї.

## Можливості

- Моніторинг стану мережі за топіком `grid_voltage` (або іншим, налаштованим у конфігурації).
- Telegram-сповіщення про появу чи зникнення мережі.
- Додаткові повідомлення при перевищенні порогів навантаження та заряду батареї.
- Збереження останнього відправленого стану між перезапусками.
- Гнучке налаштування через JSON-файл конфігурації.

## Вимоги

- Python 3.10+
- Доступ до MQTT-брокера Solar Assistant
- Доступ до Інтернету для роботи з Telegram Bot API

Необхідні Python-пакети:

```bash
pip install paho-mqtt requests
```

## Структура проєкту

- `sa_grid_telebot.py` — основний скрипт.
- `sa_grid_config.json` — приклад конфігураційного файлу (налаштуйте під власні параметри).

## Налаштування конфігурації

Типово скрипт читає налаштування з `sa_grid_config.json`. Шлях можна перевизначити змінною середовища `SA_GRID_CONFIG_FILE`.

Приклад вмісту конфігурації:

```json
{
  "telegram": {
    "token": "112233445:*****************",
    "chat_ids": ["123456789"]
  },
  "grid": {
    "min_voltage": 180.0
  },
  "load": {
    "topic": "solar_assistant/inverter_1/load_power/state",
    "high_threshold": 1700.0,
    "high_clear": 1500.0,
    "critical_threshold": 2200.0,
    "critical_clear": 2000.0
  },
  "battery": {
    "topic": "solar_assistant/total/battery_state_of_charge/state",
    "full_threshold": 99.5,
    "full_clear": 98.0,
    "half_threshold": 50.0,
    "half_clear": 52.0,
    "low_threshold": 20.0,
    "low_clear": 22.0,
    "near_empty_threshold": 10.0,
    "near_empty_clear": 12.0
  }
}
```

### Основні параметри

- `telegram.token` — токен Telegram-бота.
- `telegram.chat_ids` — список chat_id отримувачів.
- `grid.min_voltage` — поріг напруги, при якому вважається, що мережа з’явилася.
- `load.topic` / `battery.topic` — MQTT-топіки для моніторингу навантаження та заряду батареї.
- Порогові значення `high_threshold`, `critical_threshold`, `full_threshold` тощо визначають, коли надсилати сповіщення.

## Запуск вручну

1. Створіть віртуальне середовище та встановіть залежності:

    ```bash
    python3 -m venv /opt/sa-grid-telebot
    /opt/sa-grid-telebot/bin/pip install --upgrade pip
    /opt/sa-grid-telebot/bin/pip install paho-mqtt requests
    ```

2. Скопіюйте файли скрипта та конфігурації в цільову директорію, наприклад `/opt/sa-grid-telebot/`.
3. Запустіть скрипт:

    ```bash
    /opt/sa-grid-telebot/bin/python /opt/sa-grid-telebot/sa_grid_telebot.py
    ```

## Встановлення як systemd-сервіс

1. Створіть системного користувача без можливості входу (наприклад, `sa-grid`), якщо хочете запускати сервіс від окремого користувача:

    ```bash
    sudo useradd --system --home /opt/sa-grid-telebot --shell /usr/sbin/nologin sa-grid
    ```

2. Створіть директорію `/opt/sa-grid-telebot`, скопіюйте туди файли проєкту та налаштуйте права:

    ```bash
    sudo mkdir -p /opt/sa-grid-telebot
    sudo cp sa_grid_telebot.py sa_grid_config.json /opt/sa-grid-telebot/
    sudo chown -R sa-grid:sa-grid /opt/sa-grid-telebot
    ```

3. Створіть віртуальне середовище та встановіть залежності від імені root або через sudo:

    ```bash
    sudo -u sa-grid python3 -m venv /opt/sa-grid-telebot/venv
    sudo -u sa-grid /opt/sa-grid-telebot/venv/bin/pip install --upgrade pip
    sudo -u sa-grid /opt/sa-grid-telebot/venv/bin/pip install paho-mqtt requests
    ```

4. Створіть unit-файл `/etc/systemd/system/sa-grid-telebot.service` з таким вмістом:

    ```ini
    [Unit]
    Description=Solar Assistant Grid Telegram Notifier
    After=network-online.target
    Wants=network-online.target

    [Service]
    Type=simple
    User=sa-grid
    Group=sa-grid
    WorkingDirectory=/opt/sa-grid-telebot
    Environment=SA_GRID_CONFIG_FILE=/opt/sa-grid-telebot/sa_grid_config.json
    ExecStart=/opt/sa-grid-telebot/venv/bin/python /opt/sa-grid-telebot/sa_grid_telebot.py
    Restart=on-failure
    RestartSec=10

    [Install]
    WantedBy=multi-user.target
    ```

5. Перезавантажте конфігурацію systemd та ввімкніть сервіс:

    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable --now sa-grid-telebot.service
    ```

6. Перевірте статус:

    ```bash
    sudo systemctl status sa-grid-telebot.service
    ```

### Журнали

Логи сервісу доступні через `journalctl`:

```bash
sudo journalctl -u sa-grid-telebot.service -f
```

## Оновлення

Щоб оновити скрипт, замініть файли в `/opt/sa-grid-telebot/`, після чого перезапустіть сервіс:

```bash
sudo systemctl restart sa-grid-telebot.service
```

## Ліцензія

Проєкт розповсюджується за ліцензією MIT (за потреби уточніть та оновіть цей розділ).

---

# Solar Assistant Grid Telegram Notifier (English)

## Overview

Solar Assistant Grid Telegram Notifier is a Python script that listens for MQTT events from Solar Assistant and sends Telegram notifications when the utility grid appears or disappears, when load thresholds are exceeded, and when the battery charge level changes.

## Features

- Monitor the grid state via the `grid_voltage` topic (or any other configured topic).
- Telegram alerts when the grid becomes available or unavailable.
- Additional notifications for load and battery charge thresholds.
- Persist the last sent state across restarts.
- Flexible configuration through a JSON file.

## Requirements

- Python 3.10+
- Access to the Solar Assistant MQTT broker
- Internet connectivity for Telegram Bot API access

Required Python packages:

```bash
pip install paho-mqtt requests
```

## Project Structure

- `sa_grid_telebot.py` – main script.
- `sa_grid_config.json` – example configuration file (adjust for your setup).

## Configuration

By default, the script reads settings from `sa_grid_config.json`. Override the path using the `SA_GRID_CONFIG_FILE` environment variable if needed.

Example configuration:

```json
{
  "telegram": {
    "token": "112233445:*****************",
    "chat_ids": ["123456789"]
  },
  "grid": {
    "min_voltage": 180.0
  },
  "load": {
    "topic": "solar_assistant/inverter_1/load_power/state",
    "high_threshold": 1700.0,
    "high_clear": 1500.0,
    "critical_threshold": 2200.0,
    "critical_clear": 2000.0
  },
  "battery": {
    "topic": "solar_assistant/total/battery_state_of_charge/state",
    "full_threshold": 99.5,
    "full_clear": 98.0,
    "half_threshold": 50.0,
    "half_clear": 52.0,
    "low_threshold": 20.0,
    "low_clear": 22.0,
    "near_empty_threshold": 10.0,
    "near_empty_clear": 12.0
  }
}
```

### Key Parameters

- `telegram.token` – Telegram bot token.
- `telegram.chat_ids` – list of recipient chat IDs.
- `grid.min_voltage` – voltage threshold that indicates the grid is available.
- `load.topic` / `battery.topic` – MQTT topics for monitoring load and battery charge.
- Threshold values (`high_threshold`, `critical_threshold`, `full_threshold`, etc.) define when notifications are sent.

## Manual Execution

1. Create a virtual environment and install dependencies:

    ```bash
    python3 -m venv /opt/sa-grid-telebot
    /opt/sa-grid-telebot/bin/pip install --upgrade pip
    /opt/sa-grid-telebot/bin/pip install paho-mqtt requests
    ```

2. Copy the script and configuration files into the target directory, for example `/opt/sa-grid-telebot/`.
3. Run the script:

    ```bash
    /opt/sa-grid-telebot/bin/python /opt/sa-grid-telebot/sa_grid_telebot.py
    ```

## Installing as a systemd Service

1. Create a system user without login access (for example, `sa-grid`) if you want to run the service under a dedicated account:

    ```bash
    sudo useradd --system --home /opt/sa-grid-telebot --shell /usr/sbin/nologin sa-grid
    ```

2. Create the `/opt/sa-grid-telebot` directory, copy project files there, and adjust permissions:

    ```bash
    sudo mkdir -p /opt/sa-grid-telebot
    sudo cp sa_grid_telebot.py sa_grid_config.json /opt/sa-grid-telebot/
    sudo chown -R sa-grid:sa-grid /opt/sa-grid-telebot
    ```

3. Create a virtual environment and install dependencies as root or via sudo:

    ```bash
    sudo -u sa-grid python3 -m venv /opt/sa-grid-telebot/venv
    sudo -u sa-grid /opt/sa-grid-telebot/venv/bin/pip install --upgrade pip
    sudo -u sa-grid /opt/sa-grid-telebot/venv/bin/pip install paho-mqtt requests
    ```

4. Create the unit file `/etc/systemd/system/sa-grid-telebot.service` with the following content:

    ```ini
    [Unit]
    Description=Solar Assistant Grid Telegram Notifier
    After=network-online.target
    Wants=network-online.target

    [Service]
    Type=simple
    User=sa-grid
    Group=sa-grid
    WorkingDirectory=/opt/sa-grid-telebot
    Environment=SA_GRID_CONFIG_FILE=/opt/sa-grid-telebot/sa_grid_config.json
    ExecStart=/opt/sa-grid-telebot/venv/bin/python /opt/sa-grid-telebot/sa_grid_telebot.py
    Restart=on-failure
    RestartSec=10

    [Install]
    WantedBy=multi-user.target
    ```

5. Reload systemd configuration and enable the service:

    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable --now sa-grid-telebot.service
    ```

6. Check the status:

    ```bash
    sudo systemctl status sa-grid-telebot.service
    ```

### Logs

Service logs are available via `journalctl`:

```bash
sudo journalctl -u sa-grid-telebot.service -f
```

## Updating

To update the script, replace the files in `/opt/sa-grid-telebot/` and restart the service:

```bash
sudo systemctl restart sa-grid-telebot.service
```

## License

The project is distributed under the MIT License (adjust this section if necessary).

