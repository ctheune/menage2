import datetime

import arrow
import requests
from requests.exceptions import JSONDecodeError, RequestException

from menage2 import publictransport


def test_get_departures_handles_json_decode_error():
    station_specs = [("robert-koch-straße", "kantstraße")]

    def mock_get(url):
        class MockResponse:
            def json(self):
                raise JSONDecodeError("Expecting value", "", 0)

        return MockResponse()

    original_get = publictransport.session.get
    publictransport.session.get = mock_get

    try:
        result = publictransport.get_departures(station_specs)
        assert result == []
    finally:
        publictransport.session.get = original_get


def test_get_departures_handles_request_exception():
    station_specs = [("robert-koch-straße", "kantstraße")]

    def mock_get(url):
        raise RequestException("Connection error")

    original_get = publictransport.session.get
    publictransport.session.get = mock_get

    try:
        result = publictransport.get_departures(station_specs)
        assert result == []
    finally:
        publictransport.session.get = original_get


def test_get_departures_handles_missing_departures_key():
    station_specs = [("robert-koch-straße", "kantstraße")]

    def mock_get(url):
        class MockResponse:
            def json(self):
                return {}

        return MockResponse()

    original_get = publictransport.session.get
    publictransport.session.get = mock_get

    try:
        result = publictransport.get_departures(station_specs)
        assert result == []
    finally:
        publictransport.session.get = original_get


def test_get_journeys_handles_json_decode_error():
    station_specs = [("robert-koch-straße", "hauptbahnhof")]

    def mock_get(url):
        class MockResponse:
            def json(self):
                raise JSONDecodeError("Expecting value", "", 0)

        return MockResponse()

    original_get = publictransport.session.get
    publictransport.session.get = mock_get

    try:
        result = publictransport.get_journeys(station_specs)
        assert result == []
    finally:
        publictransport.session.get = original_get


def test_get_journeys_handles_request_exception():
    station_specs = [("robert-koch-straße", "hauptbahnhof")]

    def mock_get(url):
        raise RequestException("Connection error")

    original_get = publictransport.session.get
    publictransport.session.get = mock_get

    try:
        result = publictransport.get_journeys(station_specs)
        assert result == []
    finally:
        publictransport.session.get = original_get


def test_get_journeys_handles_missing_journeys_key():
    station_specs = [("robert-koch-straße", "hauptbahnhof")]

    def mock_get(url):
        class MockResponse:
            def json(self):
                return {}

        return MockResponse()

    original_get = publictransport.session.get
    publictransport.session.get = mock_get

    try:
        result = publictransport.get_journeys(station_specs)
        assert result == []
    finally:
        publictransport.session.get = original_get
