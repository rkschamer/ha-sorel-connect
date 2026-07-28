import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, call, patch

import pytest
import requests_mock as req_mock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from conftest import SorelConnect, sorel_module

SorelEntityValue = sorel_module.SorelEntityValue
SENSOR_COUNT = sorel_module.SENSOR_COUNT
RELAY_COUNT = sorel_module.RELAY_COUNT
MQTT_DISCOVERY_PREFIX = sorel_module.MQTT_DISCOVERY_PREFIX
MQTT_STATE_PREFIX = sorel_module.MQTT_STATE_PREFIX
LOGIN_TIMEOUT = sorel_module.LOGIN_TIMEOUT


class TestInitialize:
    def test_parses_base_url(self, app):
        app.initialize()
        assert app.base_url_parsed.netloc == "test.sorel-connect.net"
        assert app.base_url_parsed.scheme == "https"

    def test_schedules_run_every(self, app):
        app.initialize()
        app.run_every.assert_called_once()
        _, kwargs = app.run_every.call_args
        assert kwargs["interval"] == 5 * 60
        assert kwargs["callback"] == app.get_data_from_sorel_connect


class TestGetUrl:
    def test_basic_resource_with_query(self, app):
        app.initialize()
        url = app._get_url("sensors.json", {"id": 1})
        assert url == "https://test.sorel-connect.net/sensors.json?id=1"

    def test_empty_query(self, app):
        app.initialize()
        url = app._get_url("sensors.json", {})
        assert url == "https://test.sorel-connect.net/sensors.json"

    def test_none_query_guard(self, app):
        app.initialize()
        url = app._get_url("sensors.json", None)
        assert url == "https://test.sorel-connect.net/sensors.json"


class TestHasLoginExpired:
    def test_none_login_is_expired(self, app):
        app._last_login = None
        assert app._has_login_expired() is True

    def test_stale_login_is_expired(self, app):
        app._last_login = datetime.utcnow() - LOGIN_TIMEOUT - timedelta(seconds=1)
        assert app._has_login_expired() is True

    def test_fresh_login_not_expired(self, app):
        app._last_login = datetime.utcnow()
        assert app._has_login_expired() is False


class TestCleanSensorValue:
    def test_strips_degree_c(self, app):
        assert app._clean_sensor_value("42°C") == "42"

    def test_leaves_double_dash(self, app):
        assert app._clean_sensor_value("--") == "--"

    def test_strips_decimal(self, app):
        assert app._clean_sensor_value("23.5°C") == "23.5"


class TestCleanRelayValue:
    def test_zero_percent(self, app):
        assert app._clean_relay_value("0_0%") == "0"

    def test_nonzero_percent(self, app):
        assert app._clean_relay_value("30_30%") == "30"

    def test_aus(self, app):
        assert app._clean_relay_value("0_Aus") == "Aus"


class TestGetSensorValues:
    def test_filters_double_dash(self, app):
        app.initialize()
        app._session = MagicMock()
        raw = {str(i): SorelEntityValue(value="--", last_updated=datetime.utcnow()) for i in range(1, 14)}
        raw["1"] = SorelEntityValue(value="42°C", last_updated=datetime.utcnow())
        with patch.object(app, "_get_entity_values", return_value=raw):
            result = app._get_sensor_values()
        assert "1" in result
        assert len(result) == 1

    def test_strips_unit(self, app):
        app.initialize()
        app._session = MagicMock()
        raw = {"8": SorelEntityValue(value="41°C", last_updated=datetime.utcnow())}
        with patch.object(app, "_get_entity_values", return_value=raw):
            result = app._get_sensor_values()
        assert result["8"].value == "41"


class TestGetRelayValues:
    def test_cleans_all_entries(self, app):
        app.initialize()
        app._session = MagicMock()
        raw = {str(i): SorelEntityValue(value=f"0_{i*10}%", last_updated=datetime.utcnow())
               for i in range(1, 8)}
        with patch.object(app, "_get_entity_values", return_value=raw):
            result = app._get_relay_values()
        assert result["1"].value == "10"
        assert result["7"].value == "70"


class TestPublishDiscovery:
    def test_publishes_correct_count(self, app):
        app.initialize()
        app._publish_discovery()
        expected = SENSOR_COUNT + RELAY_COUNT + 1
        assert app.mqtt_publish.call_count == expected

    def test_all_configs_retained(self, app):
        app.initialize()
        app._publish_discovery()
        for c in app.mqtt_publish.call_args_list:
            assert c.kwargs.get("retain") is True

    def test_sensor_config_has_device_class(self, app):
        app.initialize()
        app._publish_discovery()
        sensor_calls = [
            c for c in app.mqtt_publish.call_args_list
            if "sorelconnect_sensor_" in c.args[0]
        ]
        for c in sensor_calls:
            payload = json.loads(c.kwargs["payload"])
            assert payload["device_class"] == "temperature"

    def test_relay_config_has_no_device_class(self, app):
        app.initialize()
        app._publish_discovery()
        relay_calls = [
            c for c in app.mqtt_publish.call_args_list
            if "sorelconnect_relay_" in c.args[0]
        ]
        for c in relay_calls:
            payload = json.loads(c.kwargs["payload"])
            assert "device_class" not in payload

    def test_log_config_has_value_template(self, app):
        app.initialize()
        app._publish_discovery()
        log_calls = [
            c for c in app.mqtt_publish.call_args_list
            if "sorelconnect_log" in c.args[0]
        ]
        assert len(log_calls) == 1
        payload = json.loads(log_calls[0].kwargs["payload"])
        assert "value_template" in payload
        assert "json_attributes_topic" in payload

    def test_all_configs_share_device_identifiers(self, app):
        app.initialize()
        app._publish_discovery()
        for c in app.mqtt_publish.call_args_list:
            payload = json.loads(c.kwargs["payload"])
            assert payload["device"]["identifiers"] == ["sorel_connect"]

    def test_sets_discovery_published_flag(self, app):
        app.initialize()
        assert app._discovery_published is False
        # Flag is set by the caller (get_data_from_sorel_connect), not _publish_discovery itself
        ts = datetime.now()
        sensors = {"1": SorelEntityValue("42", ts)}
        relays = {str(i): SorelEntityValue("0", ts) for i in range(1, 8)}
        logs = {str(i): SorelEntityValue(f"Log {i}", ts) for i in range(1, 4)}
        with patch.object(app, "_get_sensor_values", return_value=sensors), \
             patch.object(app, "_get_relay_values", return_value=relays), \
             patch.object(app, "_get_log_values", return_value=logs):
            app._last_login = datetime.now()
            app.get_data_from_sorel_connect(None)
        assert app._discovery_published is True


class TestPublishSensorStates:
    def test_publishes_once_per_sensor(self, app):
        app.initialize()
        values = {
            "1": SorelEntityValue(value="42", last_updated=datetime.utcnow()),
            "8": SorelEntityValue(value="23", last_updated=datetime.utcnow()),
        }
        app._publish_sensor_states(values)
        assert app.mqtt_publish.call_count == 2

    def test_topic_pattern(self, app):
        app.initialize()
        values = {"5": SorelEntityValue(value="37", last_updated=datetime.utcnow())}
        app._publish_sensor_states(values)
        topic = app.mqtt_publish.call_args.args[0]
        assert topic == f"{MQTT_STATE_PREFIX}/sensor/5"

    def test_payload_is_bare_string(self, app):
        app.initialize()
        values = {"1": SorelEntityValue(value="42", last_updated=datetime.utcnow())}
        app._publish_sensor_states(values)
        payload = app.mqtt_publish.call_args.kwargs["payload"]
        assert payload == "42"


class TestPublishRelayStates:
    def test_publishes_once_per_relay(self, app):
        app.initialize()
        values = {str(i): SorelEntityValue(value="0", last_updated=datetime.utcnow())
                  for i in range(1, 8)}
        app._publish_relay_states(values)
        assert app.mqtt_publish.call_count == 7

    def test_topic_pattern(self, app):
        app.initialize()
        values = {"3": SorelEntityValue(value="30", last_updated=datetime.utcnow())}
        app._publish_relay_states(values)
        topic = app.mqtt_publish.call_args.args[0]
        assert topic == f"{MQTT_STATE_PREFIX}/relay/3"


class TestPublishLogState:
    def test_publishes_single_json_message(self, app):
        app.initialize()
        values = {
            "1": SorelEntityValue(value="Entry 1", last_updated=datetime.utcnow()),
            "2": SorelEntityValue(value="Entry 2", last_updated=datetime.utcnow()),
            "3": SorelEntityValue(value="Entry 3", last_updated=datetime.utcnow()),
        }
        app._publish_log_state(values)
        assert app.mqtt_publish.call_count == 1

    def test_topic(self, app):
        app.initialize()
        values = {"1": SorelEntityValue(value="x", last_updated=datetime.utcnow())}
        app._publish_log_state(values)
        topic = app.mqtt_publish.call_args.args[0]
        assert topic == f"{MQTT_STATE_PREFIX}/log"

    def test_payload_contains_all_log_keys(self, app):
        app.initialize()
        values = {
            "1": SorelEntityValue(value="A", last_updated=datetime.utcnow()),
            "2": SorelEntityValue(value="B", last_updated=datetime.utcnow()),
            "3": SorelEntityValue(value="C", last_updated=datetime.utcnow()),
        }
        app._publish_log_state(values)
        payload = json.loads(app.mqtt_publish.call_args.kwargs["payload"])
        assert payload == {"log_1": "A", "log_2": "B", "log_3": "C"}


class TestGetDataFromSorelConnect:
    def _make_values(self):
        ts = datetime.utcnow()
        sensors = {"1": SorelEntityValue("42", ts)}
        relays = {str(i): SorelEntityValue("0", ts) for i in range(1, 8)}
        logs = {str(i): SorelEntityValue(f"Log {i}", ts) for i in range(1, 4)}
        return sensors, relays, logs

    def test_skips_publish_when_broker_disconnected(self, app):
        app.initialize()
        app.is_client_connected.return_value = False
        sensors, relays, logs = self._make_values()
        with patch.object(app, "_login", return_value=True), \
             patch.object(app, "_get_sensor_values", return_value=sensors), \
             patch.object(app, "_get_relay_values", return_value=relays), \
             patch.object(app, "_get_log_values", return_value=logs), \
             patch.object(app, "_publish_sensor_states") as mock_pub:
            app._last_login = datetime.utcnow()
            app.get_data_from_sorel_connect(None)
            mock_pub.assert_not_called()

    def test_calls_login_when_expired(self, app):
        app.initialize()
        app._last_login = None
        sensors, relays, logs = self._make_values()
        with patch.object(app, "_login", return_value=True) as mock_login, \
             patch.object(app, "_get_sensor_values", return_value=sensors), \
             patch.object(app, "_get_relay_values", return_value=relays), \
             patch.object(app, "_get_log_values", return_value=logs):
            app.get_data_from_sorel_connect(None)
            mock_login.assert_called_once()

    def test_aborts_on_login_failure(self, app):
        app.initialize()
        app._last_login = None
        with patch.object(app, "_login", return_value=False), \
             patch.object(app, "_get_sensor_values") as mock_get:
            app.get_data_from_sorel_connect(None)
            mock_get.assert_not_called()

    def test_publishes_discovery_only_on_first_run(self, app):
        app.initialize()
        app._last_login = datetime.utcnow()
        sensors, relays, logs = self._make_values()
        with patch.object(app, "_get_sensor_values", return_value=sensors), \
             patch.object(app, "_get_relay_values", return_value=relays), \
             patch.object(app, "_get_log_values", return_value=logs), \
             patch.object(app, "_publish_discovery") as mock_disc, \
             patch.object(app, "_publish_sensor_states"), \
             patch.object(app, "_publish_relay_states"), \
             patch.object(app, "_publish_log_state"):
            app.get_data_from_sorel_connect(None)
            assert mock_disc.call_count == 1
            app.get_data_from_sorel_connect(None)
            assert mock_disc.call_count == 1  # not called again
