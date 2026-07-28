import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from timeit import default_timer as timer
from typing import Any, Final, Literal
from urllib.parse import ParseResult, urlencode, urlparse, urlunparse

import appdaemon.plugins.hass.hassapi as hass
import requests

APP_NAMESPACE = "sorel-connect"

SENSOR_RESORUCE: Final[str] = "sensors.json"
SENSOR_COUNT: Final[int] = 13
SENOR_UNIT_OF_MEASURE = "°C"

RELAY_RESOURCE: Final[str] = "relays.json"
RELAY_COUNT: Final[int] = 7
REPLAY_UNIT_OF_MEASURE = "%"

LOG_RESOURCE: Final[str] = "log.json"
LOG_COUNT: Final[int] = 3

LOGIN_TIMEOUT: Final[timedelta] = timedelta(hours=1)


@dataclass
class SorelEntityValue:
    value: str
    last_updated: datetime


@dataclass
class SorelEntityValueContainer:
    sorel_entity_type: Literal["sensor", "relay", "log"]
    ha_domain: Literal["sensor", "text"]
    unit_of_measure: Literal["°C", "%"]
    values: dict[str, SorelEntityValue]


class SorelSensorValueContainer(SorelEntityValueContainer):
    def __init__(self, values: dict[str, SorelEntityValue]) -> None:
        super().__init__(
            sorel_entity_type="sensor",
            ha_domain="sensor",
            unit_of_measure=SENOR_UNIT_OF_MEASURE,
            values=values,
        )


class SorelRelayValueContainer(SorelEntityValueContainer):
    def __init__(self, values: dict[str, SorelEntityValue]) -> None:
        super().__init__(
            sorel_entity_type="relay",
            ha_domain="sensor",
            unit_of_measure=REPLAY_UNIT_OF_MEASURE,
            values=values,
        )


class SorelConnect(hass.Hass):
    _session: requests.Session | None = None
    _last_login: datetime | None = None
    base_url_parsed: ParseResult

    def initialize(self):
        # self.set_namespace(APP_NAMESPACE)

        base_url = self.args["sorel-connect-url"]
        self.base_url_parsed = urlparse(base_url)

        # self.get_data_from_sorel_connect(None)
        self.run_every(
            callback=self.get_data_from_sorel_connect,
            start=datetime.now(),
            interval=1# 5 * 60,
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
                self._session.cookies.set("nabto-session", session_cookie,
                                          domain=self.base_url_parsed.netloc, path="/")
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
        # self.log(f"Values: {entity_values}")
        return entity_values

    def _clean_sensor_value(self, raw_value: str) -> str:
        return raw_value.rstrip(SENOR_UNIT_OF_MEASURE)

    def _get_sensor_values(self) -> dict[str, SorelEntityValue]:
        raw_values = self._get_entity_values(SENSOR_RESORUCE, SENSOR_COUNT)
        filtered_values = {
            k: SorelEntityValue(
                value=self._clean_sensor_value(v.value), last_updated=v.last_updated
            )
            for k, v in raw_values.items()
            if v.value != "--"
        }
        return filtered_values

    def _clean_relay_value(self, raw_value: str) -> str:
        # values look like '0_0%', '30_30%' or '0_Aus'
        # removing the '0_' prefix
        value = raw_value.split("_", 1)[1]
        # remove unit of measure
        value = value.rstrip(REPLAY_UNIT_OF_MEASURE)
        return value

    def _get_relay_values(self) -> dict[str, SorelEntityValue]:
        raw_values = self._get_entity_values(RELAY_RESOURCE, RELAY_COUNT)
        values = {
            k: SorelEntityValue(
                value=self._clean_relay_value(v.value), last_updated=v.last_updated
            )
            for k, v in raw_values.items()
        }
        return values

    def _get_log_values(self) -> dict[str, SorelEntityValue]:
        return self._get_entity_values(LOG_RESOURCE, LOG_COUNT)

    def _set_ha_entity_state(
        self, ha_entity_id: str, state: str, attributes: dict[str, Any] = {}
    ):
        if not self.entity_exists(ha_entity_id):
            self.log(f"Entity '{ha_entity_id}' does not exist, creating it...")
            self.add_entity(ha_entity_id, state=state, attributes=attributes)
        else:
            self.set_state(ha_entity_id, state=state, attributes=attributes)

    def _set_states_for_entity(self, value_container: SorelEntityValueContainer):
        start = timer()
        for entity_id, entity_value in value_container.values.items():
            ha_entity_id = f"{value_container.ha_domain}.sorelconnect_{value_container.sorel_entity_type}_{entity_id}"
            attributes = {
                "friendly_name": f"Sorel Connect {value_container.sorel_entity_type.capitalize()} {entity_id}",
                "last_updated": entity_value.last_updated,
                "unit_of_measurement": value_container.unit_of_measure,
            }
            self._set_ha_entity_state(ha_entity_id, entity_value.value, attributes)

        self.log(
            f"Setting {len(value_container.values)} states for '{value_container.sorel_entity_type}' "
            + f" in {timedelta(seconds=(timer() - start))}s"
        )

    def _set_states_for_log(self, log_values: dict[str, SorelEntityValue]):
        start = timer()
        base_attributes = {"friendly_name": "Sorel Connect Log"}
        for _, log_value in log_values.items():
            ha_entity_id = "text.sorelconnect_log"
            attributes = {
                **base_attributes,
                "last_updated": log_value.last_updated,
            }
            self._set_ha_entity_state(ha_entity_id, log_value.value, attributes)
        self.log(
            f"Setting {len(log_values)} states for 'log' in {timedelta(seconds=(timer() - start))}s"
        )

    def get_data_from_sorel_connect(self, _):
        if self._has_login_expired():
            self.log("Login expired, logging in again")
            if not self._login():
                self.log("Login failed, skipping data fetch", level="ERROR")
                return

        sensor_values = SorelSensorValueContainer(self._get_sensor_values())
        relay_values = SorelRelayValueContainer(self._get_relay_values())
        log_values = self._get_log_values()

        self._set_states_for_entity(sensor_values)
        self._set_states_for_entity(relay_values)
        self._set_states_for_log(log_values)
