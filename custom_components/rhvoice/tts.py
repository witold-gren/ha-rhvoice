"""Support for the RHVoice tts service."""
import logging
from asyncio import TimeoutError as aioTimeoutError
from http import HTTPStatus
from itertools import chain

import async_timeout
import voluptuous as vol
from aiohttp import ClientError
from homeassistant.components.tts import PLATFORM_SCHEMA, Provider
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_SSL,
    CONF_TIMEOUT,
    CONF_VERIFY_SSL,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

CONF_FORMAT = "format"
CONF_PITCH = "pitch"
CONF_RATE = "rate"
CONF_VOICE = "voice"
CONF_VOLUME = "volume"

SUPPORTED_FORMATS = ["flac", "mp3", "opus", "wav"]
SUPPORTED_OPTIONS = [CONF_FORMAT, CONF_PITCH, CONF_RATE, CONF_VOICE, CONF_VOLUME]
SUPPORTED_LANGUAGES = {
    "en-US": ("alan", "bdl", "clb", "evgeniy-eng", "slt"),
    "eo": ("spomenka",),
    "ka-GE": ("natia",),
    "ky-KG": ("azamat", "nazgul"),
    "mk": ("kiko",),
    "pl-PL": ("natan", "michal", "cezary", "magda", "alicja"),
    "pt-BR": ("letícia-f123",),
    "ru-RU": (
        "aleksandr",
        "anna",
        "arina",
        "artemiy",
        "elena",
        "evgeniy-rus",
        "irina",
        "pavel",
        "yuriy",
        "victoria",
    ),
    "tt-RU": ("talgat",),
    "uk-UA": ("anatol", "natalia", "volodymyr"),
}

DEFAULT_PORT = 8080

DEFAULT_FORMAT = "mp3"
DEFAULT_PITCH = 50
DEFAULT_RATE = 50
DEFAULT_VOICE = "anna"
DEFAULT_VOLUME = 50

FORMAT_SCHEMA = vol.All(cv.string, vol.In(SUPPORTED_FORMATS))
PITCH_SCHEMA = vol.All(vol.Coerce(int), vol.Range(0, 100))
RATE_SCHEMA = vol.All(vol.Coerce(int), vol.Range(0, 100))
VOICE_SCHEMA = vol.All(cv.string, vol.In(list(chain(*SUPPORTED_LANGUAGES.values()))))
VOLUME_SCHEMA = vol.All(vol.Coerce(int), vol.Range(0, 100))

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_FORMAT, default=DEFAULT_FORMAT): FORMAT_SCHEMA,
        vol.Optional(CONF_PITCH, default=DEFAULT_PITCH): PITCH_SCHEMA,
        vol.Optional(CONF_RATE, default=DEFAULT_RATE): RATE_SCHEMA,
        vol.Optional(CONF_SSL, default=False): cv.boolean,
        vol.Optional(CONF_VERIFY_SSL, default=True): cv.boolean,
        vol.Optional(CONF_VOICE, default=DEFAULT_VOICE): VOICE_SCHEMA,
        vol.Optional(CONF_VOLUME, default=DEFAULT_VOLUME): VOLUME_SCHEMA,
    }
)


async def async_get_engine(hass, config, discovery_info=None):
    """Set up RHVoice speech component."""
    return RHVoiceProvider(hass, config)


class RHVoiceProvider(Provider):
    """RHVoice speech api provider."""

    def __init__(self, hass, conf):
        """Init RHVoice TTS service."""
        self.name = "RHVoice"
        self.hass = hass
        host, port, ssl = conf.get(CONF_HOST), conf.get(CONF_PORT), conf.get(CONF_SSL)
        self._url = f"http{'s' if ssl else ''}://{host}:{port}/say"
        self._verify_ssl = conf.get(CONF_VERIFY_SSL)

        self._encoding = conf.get(CONF_FORMAT)
        self._pitch = conf.get(CONF_PITCH)
        self._rate = conf.get(CONF_RATE)
        self._voice = conf.get(CONF_VOICE)
        self._volume = conf.get(CONF_VOLUME)
        self._timeout = conf.get(CONF_TIMEOUT)

        for language, voices in SUPPORTED_LANGUAGES.items():
            if self._voice in voices:
                self._language = language
                break

    @property
    def default_language(self):
        """Return the default language."""
        return self._language

    @property
    def supported_languages(self):
        """Return list of supported languages."""
        return list(SUPPORTED_LANGUAGES.keys())

    @property
    def supported_options(self):
        """Return list of supported options."""
        return SUPPORTED_OPTIONS

    async def async_get_tts_audio(self, message, language, options=None):
        """Load TTS from RHVoice."""
        websession = async_get_clientsession(self.hass)
        options_schema = vol.Schema(
            {
                vol.Optional(CONF_FORMAT, default=self._encoding): FORMAT_SCHEMA,
                vol.Optional(CONF_PITCH, default=self._pitch): PITCH_SCHEMA,
                vol.Optional(CONF_RATE, default=self._rate): RATE_SCHEMA,
                vol.Optional(CONF_VOICE, default=self._voice): VOICE_SCHEMA,
                vol.Optional(CONF_VOLUME, default=self._volume): VOLUME_SCHEMA,
            }
        )
        options = options_schema(options or {})
        options.update({"text": message})

        if not message:
            _LOGGER.warning("The message text can't be empty")
            message = " "

        try:
            with async_timeout.timeout(self._timeout):
                request = await websession.get(
                    self._url, params=options, verify_ssl=self._verify_ssl
                )

                if request.status != HTTPStatus.OK:
                    _LOGGER.error(
                        "Error %d on load URL %s", request.status, request.url
                    )
                    return None, None
                data = await request.read()

        except (aioTimeoutError, ClientError):
            _LOGGER.error("Timeout for RHVoice API")
            return None, None

        return self._encoding, data
