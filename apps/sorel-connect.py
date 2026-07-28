import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from timeit import default_timer as timer
from typing import Any, Final, Literal
from urllib.parse import ParseResult, urlencode, urlparse, urlunparse

import appdaemon.plugins.mqtt.mqttapi as mqtt
import requests

SENSOR_RESOURCE: Final[str] = "sensors.json"
SENSOR_COUNT: Final[int] = 13
SENSOR_UNIT_OF_MEASURE: Final[str] = "°C"

RELAY_RESOURCE: Final[str] = "relays.json"
RELAY_COUNT: Final[int] = 7
RELAY_UNIT_OF_MEASURE: Final[str] = "%"

LOG_RESOURCE: Final[str] = "log.json"
LOG_COUNT: Final[int] = 3

LOGIN_TIMEOUT: Final[timedelta] = timedelta(hours=1)

MQTT_DISCOVERY_PREFIX: Final[str] = "homeassistant"
MQTT_STATE_PREFIX: Final[str] = "sorel-connect"

DEVICE_BLOCK: Final[dict] = {
    "identifiers": ["sorel_connect"],
    "name": "Sorel Connect",
    "manufacturer": "Sorel",
    "model": "SOREL Connect",
}


@dataclass
class SorelEntityValue:
    value: str
    last_updated: datetime


class SorelConnect(mqtt.Mqtt):
    _session: requests.Session | None = None
    _last_login: datetime | None = None
    _discovery_published: bool = False
    base_url_parsed: ParseResult

    def initialize(self):
        base_url = self.args["sorel-connect-url"]
        self.base_url_parsed = urlparse(base_url)
        self.run_every(
            callback=self.get_data_from_sorel_connect,
            start=datetime.now(),
            interval=5 * 60,
        )

    def _get_url(self, resource: str, query: dict = {}) -> str:
        if query is None:
            query = {}
        return urlunparse(
            ParseResult(
                scheme=self.base_url_parsed.scheme,
                netloc=self.base_url_parsed.netloc,
                params=self.base_url_parsed.params,
                fragment=self.base_url_parsed.fragment,
                path=resource,
                query=urlencode(query),
            )
        )

    def _do_get_return_parsed_response_body(self, url: str) -> dict[str, Any]:
        assert self._session is not None, "Login is required before calling this method"
        response: requests.Response = self._session.get(url)
        response.raise_for_status()
        response.encoding = "utf-8"
        text = response.text.strip()
        # login endpoint returns JSONP like ({...}), data endpoints return plain JSON
        json_start = text.find("{")
        json_end = text.rfind("}")
        return json.loads(text[json_start : json_end + 1])

    def _login(self) -> bool:
        user = self.args["sorel-connect-user"]
        password = self.args["sorel-connect-password"]
        self._session = requests.session()
        self._session.headers.update({"X-Requested-With": "XMLHttpRequest"})
        url = self._get_url(
            "/nabto/hosted_plugin/login/execute", {"email": user, "password": password}
        )
        parsed_response_body = self._do_get_return_parsed_response_body(url)
        login_successful = bool(parsed_response_body.get("session_key", None))
        if login_successful:
            # The Set-Cookie is scoped to the login path; broaden it to / so it's
            # sent with subsequent data requests.
            session_cookie = self._session.cookies.get("nabto-session")
            if session_cookie:
                self._session.cookies.set(
                    "nabto-session", session_cookie,
                    domain=self.base_url_parsed.netloc, path="/"
                )
            self._last_login = datetime.utcnow()
            self.log("Login successful")
        else:
            self.log(f"Login failed, response: {parsed_response_body}", level="ERROR")

        return login_successful

    def _has_login_expired(self) -> bool:
        if self._last_login is None:
            return True
        if datetime.utcnow() - self._last_login > LOGIN_TIMEOUT:
            return True
        return False

    def _get_entity_values(
        self, entity_resource: str, entity_count: int
    ) -> dict[str, SorelEntityValue]:
        assert self._session is not None, "Login is required before calling this method"

        start = timer()
        entity_values: dict[str, SorelEntityValue] = {}
        for entity_id in range(1, entity_count + 1):
            entity_url = self._get_url(entity_resource, {"id": entity_id})
            parsed_response_body = self._do_get_return_parsed_response_body(entity_url)
            entity_values[str(entity_id)] = SorelEntityValue(
                value=parsed_response_body.get("val") or "",
                last_updated=parsed_response_body.get("dt", datetime.utcnow()),
            )
        self.log(
            f"Retrieving {entity_count} values for '{entity_resource}'"
            + f" in {timedelta(seconds=(timer() - start))}s"
        )
        return entity_values

    def _clean_sensor_value(self, raw_value: str) -> str:
        return raw_value.rstrip(SENSOR_UNIT_OF_MEASURE)

    def _get_sensor_values(self) -> dict[str, SorelEntityValue]:
        raw_values = self._get_entity_values(SENSOR_RESOURCE, SENSOR_COUNT)
        return {
            k: SorelEntityValue(
                value=self._clean_sensor_value(v.value), last_updated=v.last_updated
            )
            for k, v in raw_values.items()
            if v.value != "--"
        }

    def _clean_relay_value(self, raw_value: str) -> str:
        # values look like '0_0%', '30_30%' or '0_Aus'
        # removing the '0_' prefix
        value = raw_value.split("_", 1)[1]
        return value.rstrip(RELAY_UNIT_OF_MEASURE)

    def _get_relay_values(self) -> dict[str, SorelEntityValue]:
        raw_values = self._get_entity_values(RELAY_RESOURCE, RELAY_COUNT)
        return {
            k: SorelEntityValue(
                value=self._clean_relay_value(v.value), last_updated=v.last_updated
            )
            for k, v in raw_values.items()
        }

    def _get_log_values(self) -> dict[str, SorelEntityValue]:
        return self._get_entity_values(LOG_RESOURCE, LOG_COUNT)

    def _mqtt_publish_json(self, topic: str, payload: dict, retain: bool = False) -> None:
        self.mqtt_publish(topic, payload=json.dumps(payload), retain=retain, namespace="mqtt")

    def _publish_discovery(self) -> None:
        self.log("Publishing MQTT Discovery configs")

        for sensor_id in range(1, SENSOR_COUNT + 1):
            unique_id = f"sorelconnect_sensor_{sensor_id}"
            self._mqtt_publish_json(
                f"{MQTT_DISCOVERY_PREFIX}/sensor/{unique_id}/config",
                {
                    "unique_id": unique_id,
                    "name": f"Sorel Connect Sensor {sensor_id}",
                    "state_topic": f"{MQTT_STATE_PREFIX}/sensor/{sensor_id}",
                    "unit_of_measurement": SENSOR_UNIT_OF_MEASURE,
                    "device_class": "temperature",
                    "state_class": "measurement",
                    "device": DEVICE_BLOCK,
                },
                retain=True,
            )

        for relay_id in range(1, RELAY_COUNT + 1):
            unique_id = f"sorelconnect_relay_{relay_id}"
            self._mqtt_publish_json(
                f"{MQTT_DISCOVERY_PREFIX}/sensor/{unique_id}/config",
                {
                    "unique_id": unique_id,
                    "name": f"Sorel Connect Relay {relay_id}",
                    "state_topic": f"{MQTT_STATE_PREFIX}/relay/{relay_id}",
                    "unit_of_measurement": RELAY_UNIT_OF_MEASURE,
                    "state_class": "measurement",
                    "device": DEVICE_BLOCK,
                },
                retain=True,
            )

        self._mqtt_publish_json(
            f"{MQTT_DISCOVERY_PREFIX}/sensor/sorelconnect_log/config",
            {
                "unique_id": "sorelconnect_log",
                "name": "Sorel Connect Log",
                "state_topic": f"{MQTT_STATE_PREFIX}/log",
                "value_template": "{{ value_json.log_1 }}",
                "json_attributes_topic": f"{MQTT_STATE_PREFIX}/log",
                "json_attributes_template": (
                    "{{ {'log_1': value_json.log_1, "
                    "'log_2': value_json.log_2, "
                    "'log_3': value_json.log_3} | tojson }}"
                ),
                "device": DEVICE_BLOCK,
            },
            retain=True,
        )

        self.log("MQTT Discovery configs published")

    def _publish_sensor_states(self, sensor_values: dict[str, SorelEntityValue]) -> None:
        start = timer()
        for sensor_id, entity_value in sensor_values.items():
            self.mqtt_publish(
                f"{MQTT_STATE_PREFIX}/sensor/{sensor_id}",
                payload=entity_value.value,
                namespace="mqtt",
            )
        self.log(
            f"Published {len(sensor_values)} sensor states"
            f" in {timedelta(seconds=(timer() - start))}s"
        )

    def _publish_relay_states(self, relay_values: dict[str, SorelEntityValue]) -> None:
        start = timer()
        for relay_id, entity_value in relay_values.items():
            self.mqtt_publish(
                f"{MQTT_STATE_PREFIX}/relay/{relay_id}",
                payload=entity_value.value,
                namespace="mqtt",
            )
        self.log(
            f"Published {len(relay_values)} relay states"
            f" in {timedelta(seconds=(timer() - start))}s"
        )

    def _publish_log_state(self, log_values: dict[str, SorelEntityValue]) -> None:
        start = timer()
        self._mqtt_publish_json(
            f"{MQTT_STATE_PREFIX}/log",
            {f"log_{log_id}": entity_value.value for log_id, entity_value in log_values.items()},
        )
        self.log(f"Published log state in {timedelta(seconds=(timer() - start))}s")

    def get_data_from_sorel_connect(self, _):
        if self._has_login_expired():
            self.log("Login expired, logging in again")
            if not self._login():
                self.log("Login failed, skipping data fetch", level="ERROR")
                return

        sensor_values = self._get_sensor_values()
        relay_values = self._get_relay_values()
        log_values = self._get_log_values()

        if not self._discovery_published:
            self._publish_discovery()
            self._discovery_published = True

        if not self.is_client_connected(namespace="mqtt"):
            self.log("MQTT broker not connected, skipping publish", level="WARNING")
            return

        self._publish_sensor_states(sensor_values)
        self._publish_relay_states(relay_values)
        self._publish_log_state(log_values)
