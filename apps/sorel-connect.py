from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from timeit import default_timer as timer
from urllib.parse import ParseResult, urlencode, urlparse, urlunparse
import appdaemon.plugins.hass.hassapi as hass
import requests
from typing import Any, Dict, Final, Literal

APP_NAMESPACE = "sorel-connect"

SENSOR_RESORUCE: Final[str] = "sensors.json"
SENSOR_COUNT: Final[int] = 13

RELAY_RESOURCE: Final[str] = "relays.json"
RELAY_COUNT: Final[int] = 7

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
    values: Dict[str, SorelEntityValue]


class SorelSensorValueContainer(SorelEntityValueContainer):
    def __init__(self, values: Dict[str, SorelEntityValue]) -> None:
        super().__init__(
            sorel_entity_type="sensor",
            ha_domain="sensor",
            unit_of_measure="°C",
            values=values,
        )


class SorelRelayValueContainer(SorelEntityValueContainer):
    def __init__(self, values: Dict[str, SorelEntityValue]) -> None:
        super().__init__(
            sorel_entity_type="relay",
            ha_domain="sensor",
            unit_of_measure="%",
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
        self.run_minutely(
            callback=self.get_data_from_sorel_connect, start=datetime.now()
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

    def _jsonp_to_json(self, jsonp_payload: str) -> Dict[str, Any]:
        json_start = jsonp_payload.find("{")
        json_end = jsonp_payload.rfind("}")
        json_string = jsonp_payload[json_start : json_end + 1]
        return json.loads(json_string)

    def _do_get_return_parsed_response_body(self, url: str) -> Dict[str, Any]:
        assert self._session is not None, "Login is required before calling this method"
        response: requests.Response = self._session.get(url)
        response.raise_for_status()
        response.encoding = "utf-8"
        parsed_response_body: Dict[str, Any] = self._jsonp_to_json(response.text)
        return parsed_response_body

    def _login(self) -> bool:
        user = self.args["sorel-connect-user"]
        password = self.args["sorel-connect-password"]
        self._session = requests.session()
        # https://db7bb5.sorel-connect.net/nabto/hosted_plugin/login/execute?email=r.horsmar@arcor.de&password=asdasda&callback=jQuery1102038743513531490015_1685218651224&_=1685218651225
        url = self._get_url(
            "/nabto/hosted_plugin/login/execute", {"email": user, "password": password}
        )
        parsed_response_body = self._do_get_return_parsed_response_body(url)
        login_successful = bool(parsed_response_body.get("session_key", None))
        if login_successful:
            self._last_login = datetime.utcnow()

        return login_successful

    def _has_login_expired(self) -> bool:
        if self._last_login is None:
            return False
        if datetime.utcnow() - self._last_login > LOGIN_TIMEOUT:
            return False
        return True

    def _get_entity_values(
        self, entity_resource: str, entity_count: int
    ) -> Dict[str, SorelEntityValue]:
        assert self._session is not None, "Login is required before calling this method"

        start = timer()
        entity_values: Dict[str, SorelEntityValue] = {}
        for entity_id in range(1, entity_count + 1):
            entity_url = self._get_url(entity_resource, {"id": entity_id})
            response: requests.Response = self._session.get(entity_url)
            response.raise_for_status()
            response.encoding = "utf-8"
            parsed_response_body: Dict[str, Any] = self._jsonp_to_json(response.text)
            entity_values[str(entity_id)] = SorelEntityValue(
                value=parsed_response_body.get("val", None),
                last_updated=parsed_response_body.get("dt", datetime.utcnow()),
            )
        self.log(
            f"Retrieving {entity_count} values for '{entity_resource}'"
            + f" in {timedelta(seconds=(timer() - start))}s"
        )
        # self.log(f"Values: {entity_values}")
        return entity_values

    def _get_sensor_values(self) -> Dict[str, SorelEntityValue]:
        raw_values = self._get_entity_values(SENSOR_RESORUCE, SENSOR_COUNT)
        filtered_values = {k: v for k, v in raw_values.items() if v.value != "--"}
        return filtered_values

    def _get_relay_values(self) -> Dict[str, SorelEntityValue]:
        # values look like '0_0%', '30_30%' or '0_Aus'
        raw_values = self._get_entity_values(RELAY_RESOURCE, RELAY_COUNT)
        # removing the '0_' prefix
        values = {
            k: SorelEntityValue(
                value=v.value.split("_", 1)[1], last_updated=v.last_updated
            )
            for k, v in raw_values.items()
        }
        return values

    def _get_log_values(self) -> Dict[str, SorelEntityValue]:
        return self._get_entity_values(LOG_RESOURCE, LOG_COUNT)

    def _set_ha_entity_state(
        self, ha_entity_id: str, state: str, attributes: Dict[str, Any] = {}
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

    def _set_states_for_log(self, log_values: Dict[str, SorelEntityValue]):
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
        if not self._has_login_expired():
            self.log("Login expired, logging in again")
            self._login()

        sensor_values = SorelSensorValueContainer(self._get_sensor_values())
        relay_values = SorelRelayValueContainer(self._get_relay_values())
        log_values = self._get_log_values()

        self._set_states_for_entity(sensor_values)
        self._set_states_for_entity(relay_values)
        self._set_states_for_log(log_values)
