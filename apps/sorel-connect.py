from datetime import datetime, timedelta
import json
from urllib.parse import ParseResult, urlencode, urlparse, urlunparse
import appdaemon.plugins.hass.hassapi as hass
import requests
from typing import Any, Dict, Final

SENSOR_RESORUCE: Final[str] = "sensors.json"
SENSOR_COUNT: Final[int] = 13

RELAY_RESOURCE: Final[str] = "relays.json"
RELAY_COUNT: Final[int] = 7

LOG_RESOURCE: Final[str] = "log.json"
LOG_COUNT: Final[int] = 3

LOGIN_TIMEOUT: Final[timedelta] = timedelta(hours=1)


class SorelConnect(hass.Hass):
    _session: requests.Session | None = None
    _last_login: datetime | None = None

    def initialize(self):
        base_url = self.args["sorel-connect-url"]
        self.base_url_parsed = urlparse(base_url)

        self.get_data_from_sorel_connect()
        # self.run_minutely(self.get_data_from_sorel_connect, start)

    def _get_url(self, resource: str, query: dict = None) -> str:
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
    ) -> Dict[str, str]:
        entity_values: Dict[str, str] = {}
        for entity_id in range(1, entity_count + 1):
            entity_url = self._get_url(entity_resource, {"id": entity_id})
            response: requests.Response = self._session.get(entity_url)
            response.raise_for_status()
            response.encoding = "utf-8"
            parsed_response_body: Dict[str, Any] = self._jsonp_to_json(response.text)
            entity_values[entity_id] = parsed_response_body.get("val", None)
        return entity_values

    def _get_sensor_values(self) -> Dict[str, str]:
        return self._get_entity_values(SENSOR_RESORUCE, SENSOR_COUNT)

    def _get_relay_values(self) -> Dict[str, str]:
        # values look like '0_0%', '30_30%' or '0_Aus'
        raw_values = self._get_entity_values(RELAY_RESOURCE, RELAY_COUNT)
        # removing the '0_' prefix
        values = {k: v.split("_", 1)[1] for k, v in raw_values.items()}
        return values

    def _get_log_values(self) -> Dict[str, str]:
        return self._get_entity_values(LOG_RESOURCE, LOG_COUNT)

    def get_data_from_sorel_connect(self):
        if not self._has_login_expired():
            self.log("Login expired, logging in again")
            self._login()

        self.log("Refreshing sensor values")
        sensor_values = self._get_sensor_values()
        print(sensor_values)
        self.log("Refreshing relay values")
        relay_values = self._get_relay_values()
        print(relay_values)
        self.log("Refreshing log values")
        log_values = self._get_log_values()
        print(log_values)
