"""Minimal read-only Moodle REST client.

The token is accepted at runtime and is never persisted by this module.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import requests


class MoodleClientError(RuntimeError):
    """Safe Moodle connectivity/API failure."""


class MoodleClient:
    def __init__(self, base_url, token, *, session=None, timeout=20, max_file_bytes=100 * 1024 * 1024):
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.token = str(token or "").strip()
        self.session = session or requests.Session()
        self.timeout = int(timeout)
        self.max_file_bytes = int(max_file_bytes)
        try:
            parts = urlsplit(self.base_url)
        except ValueError as error:
            raise MoodleClientError("Moodle URL is invalid.") from error
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise MoodleClientError("Moodle URL must be an http(s) site.")
        if not self.token:
            raise MoodleClientError("Moodle token is not configured.")
        self._host = parts.hostname.casefold()

    @property
    def endpoint(self):
        return self.base_url + "/webservice/rest/server.php"

    def call(self, function, **params):
        payload = {
            "wstoken": self.token,
            "wsfunction": str(function),
            "moodlewsrestformat": "json",
        }
        payload.update(params)
        try:
            response = self.session.post(
                self.endpoint,
                data=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as error:
            raise MoodleClientError(
                "Moodle could not complete the read-only request."
            ) from error
        if isinstance(data, dict) and data.get("exception"):
            raise MoodleClientError(
                "Moodle rejected the read-only request: {}".format(
                    str(data.get("message") or data.get("errorcode") or "unknown error")[:240]
                )
            )
        return data

    def site_info(self):
        data = self.call("core_webservice_get_site_info")
        if not isinstance(data, dict) or data.get("userid") in (None, ""):
            raise MoodleClientError("Moodle site information is incomplete.")
        return data

    def enrolled_courses(self, user_id):
        data = self.call("core_enrol_get_users_courses", userid=int(user_id))
        if not isinstance(data, list):
            raise MoodleClientError("Moodle returned an invalid course list.")
        return tuple(data)

    def course_contents(self, course_id):
        data = self.call("core_course_get_contents", courseid=int(course_id))
        if not isinstance(data, list):
            raise MoodleClientError("Moodle returned invalid course contents.")
        return tuple(data)

    def download_file(self, file_url):
        url = str(file_url or "").strip()
        try:
            parts = urlsplit(url)
        except ValueError as error:
            raise MoodleClientError("Moodle file URL is invalid.") from error
        if parts.scheme not in {"http", "https"} or (parts.hostname or "").casefold() != self._host:
            raise MoodleClientError("Moodle file URL points outside the configured Moodle host.")
        try:
            response = self.session.get(
                url,
                params={"token": self.token},
                timeout=self.timeout,
                stream=True,
            )
            response.raise_for_status()
            advertised = response.headers.get("Content-Length")
            if advertised and int(advertised) > self.max_file_bytes:
                raise MoodleClientError("Moodle file is larger than the configured safety limit.")
            data = bytearray()
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                data.extend(chunk)
                if len(data) > self.max_file_bytes:
                    raise MoodleClientError("Moodle file is larger than the configured safety limit.")
            return bytes(data)
        except MoodleClientError:
            raise
        except (requests.RequestException, ValueError) as error:
            raise MoodleClientError("Moodle file download failed.") from error
