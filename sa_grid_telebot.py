#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Solar Assistant (MQTT) -> Telegram
Оповещения "городская сеть появилась/пропала" по событию grid_voltage или device_mode.

Требует:
  pip install paho-mqtt requests
Запуск (в venv):
  /home/solar-assistant/mqttbot/bin/python /opt/sa_grid_telebot.py
"""

import json
import os
import sys
import time
import signal
from dataclasses import dataclass
from typing import Any, Optional

import requests
from paho.mqtt.client import Client, CallbackAPIVersion


# ========= НАСТРОЙКИ =========

# MQTT брокер
MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883
MQTT_USERNAME = "sa_user"
MQTT_PASSWORD = "s3cret"
MQTT_TLS = False                # True если нужен TLS (обычно порт 8883)
MQTT_CLIENT_ID = "sa-grid-telebot"
MQTT_KEEPALIVE = 60

# Топик, который меняется при наличии/пропадании городской сети.
# Вариант 1 (по напряжению): >= GRID_MIN_VOLT считаем "сеть есть"
MQTT_TOPIC = "solar_assistant/inverter_1/grid_voltage/state"
JSON_FIELD = ""                 # если payload JSON, указать поле (например "grid.connected"); иначе оставить ""

# Порог "есть/нет сети" для напряжения (если используем grid_voltage/state)
GRID_MIN_VOLT = 180.0

# Топики для дополнительных уведомлений
LOAD_TOPIC = "solar_assistant/inverter_1/load_power/state"
LOAD_JSON_FIELD = ""

BATTERY_SOC_TOPIC = "solar_assistant/inverter_1/battery_soc/state"
BATTERY_JSON_FIELD = ""

# Пороговые значения (Вт и %)
LOAD_HIGH_THRESHOLD = 1700.0    # высокая нагрузка
LOAD_HIGH_CLEAR = 1500.0        # ниже этого сбрасываем статус высокой нагрузки
LOAD_CRITICAL_THRESHOLD = 2200.0  # предельная нагрузка
LOAD_CRITICAL_CLEAR = 2000.0

BATTERY_FULL_THRESHOLD = 99.5
BATTERY_FULL_CLEAR = 98.0
BATTERY_HALF_THRESHOLD = 50.0
BATTERY_HALF_CLEAR = 52.0
BATTERY_LOW_THRESHOLD = 20.0
BATTERY_LOW_CLEAR = 22.0
BATTERY_NEAR_EMPTY_THRESHOLD = 10.0
BATTERY_NEAR_EMPTY_CLEAR = 12.0

# Анти-дребезг и подавление дубликатов
DEBOUNCE_SECONDS = 1            # состояние должно удержаться не менее N сек
SUPPRESS_REPEAT_SECONDS = 60    # одинаковые уведомления не чаще, чем раз в N сек

# Игнорировать первое retained-сообщение после подключения
IGNORE_FIRST_RETAINED = True

# Telegram
TG_TOKEN = "112233445:*****************" 
TG_CHAT_ID = "123456789"        # ваш chat_id / id группы / id канала (бот должен иметь права писать)
TG_PREFIX = "⚡️Grid"           # префикс в тексте уведомления

# Хранилище последнего состояния (для переживания перезапусков)
STATE_FILE = "/var/lib/sa-grid-telebot/last_state.json"

# ========= /НАСТРОЙКИ =========


os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)


def send_telegram(text: str) -> None:
    """Отправка сообщения в Telegram."""
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
        if r.status_code != 200:
            print(f"[ERR] Telegram HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"[ERR] Telegram send failed: {e}", file=sys.stderr)


def load_state() -> dict:
    """Читаем последнее отправленное состояние."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"state": None, "ts": 0}


def save_state(state: Any) -> None:
    """Сохраняем последнее отправленное состояние."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"state": state, "ts": int(time.time())}, f)
    except Exception as e:
        print(f"[ERR] save_state: {e}", file=sys.stderr)


@dataclass
class ThresholdEvent:
    """Описывает пороговое уведомление для числового значения."""

    direction: str  # 'above' или 'below'
    trigger: float
    clear: float
    message: str
    active: bool = False
    last_sent: float = 0.0

    def evaluate(self, value: float, now: float) -> bool:
        """Возвращает True, если нужно отправить уведомление."""
        triggered = False

        if self.direction == "above":
            if value >= self.trigger and not self.active:
                self.active = True
                triggered = True
            elif value <= self.clear and self.active:
                self.active = False
        elif self.direction == "below":
            if value <= self.trigger and not self.active:
                self.active = True
                triggered = True
            elif value >= self.clear and self.active:
                self.active = False

        if triggered:
            if (now - self.last_sent) >= SUPPRESS_REPEAT_SECONDS:
                self.last_sent = now
                return True
        return False


def get_json_path(d: Any, path: str):
    """Достаём значение по пути вида 'a.b.c' из словаря."""
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def extract_numeric(payload: str, json_field: str = "") -> Optional[float]:
    """Возвращает числовое значение из payload (простое число или JSON)."""
    value: Any = payload

    if json_field:
        try:
            data = json.loads(payload)
            value = get_json_path(data, json_field)
        except Exception:
            return None

    try:
        return float(value)
    except Exception:
        return None


def normalize_state(val: Any) -> bool | None:
    """
    Унификация состояния:
      True  -> сеть есть
      False -> сеть пропала
      None  -> непонятно
    Если val — число (например grid_voltage), используем GRID_MIN_VOLT.
    Если val — строка (например device_mode), распознаём по словам.
    """
    if val is None:
        return None

    # Числа: порог по напряжению
    try:
        n = float(val)
        return n >= GRID_MIN_VOLT
    except Exception:
        pass

    s = str(val).strip().lower()

    # Явные режимы
    # Пример: device_mode/state => "Grid" | "Battery" | "PV" | ...
    if s in {"grid", "line", "utility", "ac"}:
        return True
    if s in {"battery", "pv", "solar"}:
        return False

    truthy = {"1", "on", "true", "online", "up", "present", "connected", "ok"}
    falsy = {"0", "off", "false", "offline", "down", "absent", "disconnected", "fail", "failed"}

    if s in truthy:
        return True
    if s in falsy:
        return False

    # Эвристики по словам
    if "connect" in s and "dis" not in s:
        return True
    if "discon" in s or "no grid" in s or "grid fail" in s:
        return False

    return None


class GridWatcher:
    def __init__(self):
        # paho-mqtt 2.x: используем API v5
        self.client = Client(client_id=MQTT_CLIENT_ID)

        if MQTT_USERNAME:
            self.client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        if MQTT_TLS:
            self.client.tls_set()  # при необходимости добавить параметры CA/сертов

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        self.last_observed_state: bool | None = None
        self.last_change_ts: float = 0.0
        self.pending_state: bool | None = None
        self.pending_since: float = 0.0

        st = load_state()
        self.last_sent_state: bool | None = st["state"]
        self.last_send_ts: int = st["ts"]

        self.first_message_seen = not IGNORE_FIRST_RETAINED  # если игнорируем первое retained — начнём с False

        self.load_events = [
            ThresholdEvent(
                direction="above",
                trigger=LOAD_HIGH_THRESHOLD,
                clear=LOAD_HIGH_CLEAR,
                message=f"{TG_PREFIX}: ⚠️ Высокая нагрузка {{value_kw:.2f}} кВт",
            ),
            ThresholdEvent(
                direction="above",
                trigger=LOAD_CRITICAL_THRESHOLD,
                clear=LOAD_CRITICAL_CLEAR,
                message=f"{TG_PREFIX}: 🚨 Предельная нагрузка {{value_kw:.2f}} кВт",
            ),
        ]

        self.battery_events = [
            ThresholdEvent(
                direction="above",
                trigger=BATTERY_FULL_THRESHOLD,
                clear=BATTERY_FULL_CLEAR,
                message=f"{TG_PREFIX}: 🔋 Батарея зарядилась ({{percent:.0f}}%)",
            ),
            ThresholdEvent(
                direction="below",
                trigger=BATTERY_HALF_THRESHOLD,
                clear=BATTERY_HALF_CLEAR,
                message=f"{TG_PREFIX}: 🔋 Батарея разряжена наполовину ({{percent:.0f}}%)",
            ),
            ThresholdEvent(
                direction="below",
                trigger=BATTERY_LOW_THRESHOLD,
                clear=BATTERY_LOW_CLEAR,
                message=f"{TG_PREFIX}: 🔋 Батарея разряжена на 20% ({{percent:.0f}}%)",
            ),
            ThresholdEvent(
                direction="below",
                trigger=BATTERY_NEAR_EMPTY_THRESHOLD,
                clear=BATTERY_NEAR_EMPTY_CLEAR,
                message=f"{TG_PREFIX}: 🔋 Батарея почти разрядилась ({{percent:.0f}}%)",
            ),
        ]

    # Новый прототип on_connect для v5
    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        print(f"[MQTT] Connected, rc={reason_code}")
        client.subscribe(MQTT_TOPIC, qos=1)
        if LOAD_TOPIC:
            client.subscribe(LOAD_TOPIC, qos=1)
        if BATTERY_SOC_TOPIC:
            client.subscribe(BATTERY_SOC_TOPIC, qos=1)

    def on_message(self, client, userdata, msg):
        now = time.time()
        topic = msg.topic.decode("utf-8") if isinstance(msg.topic, bytes) else msg.topic

        payload_raw = msg.payload
        try:
            payload = payload_raw.decode("utf-8", "ignore").strip()
        except Exception:
            payload = str(payload_raw)

        if topic == MQTT_TOPIC:
            if IGNORE_FIRST_RETAINED and not self.first_message_seen and msg.retain:
                self.first_message_seen = True
                print("[MQTT] Ignored first retained message")
                return
            self.first_message_seen = True
            self.process_grid_payload(payload, now)
            return

        if topic == LOAD_TOPIC and LOAD_TOPIC:
            self.process_load_payload(payload, now)
            return

        if topic == BATTERY_SOC_TOPIC and BATTERY_SOC_TOPIC:
            self.process_battery_payload(payload, now)
            return

        # Неизвестный топик — логируем для отладки
        print(f"[WARN] Unexpected topic {topic}")

    def process_grid_payload(self, payload: str, now: float) -> None:
        """Обрабатывает сообщения о состоянии городской сети."""

        # Извлекаем значение
        new_state: bool | None = None
        if JSON_FIELD:
            try:
                data = json.loads(payload)
                val = get_json_path(data, JSON_FIELD)
                new_state = normalize_state(val)
            except Exception:
                new_state = None
        if new_state is None:
            new_state = normalize_state(payload)

        if new_state is None:
            print(f"[WARN] Can't parse state from payload: {payload[:200]}")
            return

        # Фиксация изменения и запуск анти-дребезга
        if self.last_observed_state != new_state:
            self.last_observed_state = new_state
            self.last_change_ts = now
            self.pending_state = new_state
            self.pending_since = now
            print(f"[OBS] Observed change -> {new_state}")
            return

        # Подтверждение устойчивого состояния
        if (
            self.pending_state is not None
            and new_state == self.pending_state
            and now - self.pending_since >= DEBOUNCE_SECONDS
        ):
            # Подавление повторов
            if self.last_sent_state == new_state and (now - self.last_send_ts) < SUPPRESS_REPEAT_SECONDS:
                return

            # Отправляем Telegram
            txt = f"{TG_PREFIX}: 🟢 Сеть появилась" if new_state else f"{TG_PREFIX}: 🔴 Сеть пропала"
            send_telegram(txt)

            # Запоминаем отправленное состояние
            self.last_sent_state = new_state
            self.last_send_ts = int(now)
            save_state(new_state)

            # Сброс pending
            self.pending_state = None

    def process_load_payload(self, payload: str, now: float) -> None:
        """Отправляет уведомления по нагрузке."""
        value = extract_numeric(payload, LOAD_JSON_FIELD)
        if value is None:
            print(f"[WARN] Can't parse load value: {payload[:200]}")
            return

        kw = value / 1000.0

        for event in self.load_events:
            if event.evaluate(value, now):
                msg = event.message.format(value=value, value_kw=kw)
                send_telegram(msg)

    def process_battery_payload(self, payload: str, now: float) -> None:
        """Отправляет уведомления по состоянию батареи."""
        value = extract_numeric(payload, BATTERY_JSON_FIELD)
        if value is None:
            print(f"[WARN] Can't parse battery value: {payload[:200]}")
            return

        percent = max(0.0, min(100.0, value))

        for event in self.battery_events:
            if event.evaluate(percent, now):
                msg = event.message.format(percent=percent, value=percent)
                send_telegram(msg)

    def run(self):
        self.client.connect(MQTT_HOST, MQTT_PORT, keepalive=MQTT_KEEPALIVE)
        self.client.loop_forever()


def main():
    watcher = GridWatcher()

    def handle_sig(sig, frm):
        try:
            watcher.client.disconnect()
        finally:
            sys.exit(0)

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)
    watcher.run()


if __name__ == "__main__":
    main()

