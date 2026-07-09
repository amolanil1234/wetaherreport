"""Open-Meteo geocoding and forecast client."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

from config import (
    DEFAULT_CITIES,
    FORECAST_API_URL,
    GEOCODING_API_URL,
    CityConfig,
    get_digest_timezone,
)

WMO_WEATHER_CODES: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


@dataclass(frozen=True)
class Coordinates:
    name: str
    latitude: float
    longitude: float
    country: str
    timezone: str
    elevation: float | None = None


@dataclass
class CurrentConditions:
    temperature_c: float | None
    apparent_temperature_c: float | None
    humidity_percent: float | None
    wind_speed_kmh: float | None
    wind_direction_deg: float | None
    precipitation_mm: float | None
    cloud_cover_percent: float | None
    weather_code: int | None
    weather_description: str
    observed_at: str | None


@dataclass
class DailyForecast:
    date: str
    temp_min_c: float | None
    temp_max_c: float | None
    precipitation_sum_mm: float | None
    wind_max_kmh: float | None
    weather_code: int | None
    weather_description: str
    sunrise: str | None
    sunset: str | None


@dataclass
class CityWeather:
    city_name: str
    coordinates: Coordinates | None = None
    current: CurrentConditions | None = None
    daily: list[DailyForecast] = field(default_factory=list)
    error: str | None = None


@dataclass
class WeatherReport:
    generated_at: str
    timezone: str
    cities: list[CityWeather]

    @property
    def has_any_success(self) -> bool:
        return any(city.error is None and city.current is not None for city in self.cities)

    @property
    def all_failed(self) -> bool:
        return not self.has_any_success


def wmo_description(code: int | None) -> str:
    if code is None:
        return "Unknown"
    return WMO_WEATHER_CODES.get(code, f"Code {code}")


def _request_json(url: str, params: dict[str, Any], retries: int = 1) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                if data.get("error"):
                    raise RuntimeError(data.get("reason", "Open-Meteo API error"))
                return data
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(1.5)
    assert last_error is not None
    raise last_error


def geocode_city(name: str, country_code: str = "IN") -> Coordinates:
    data = _request_json(
        GEOCODING_API_URL,
        {"name": name, "count": 5, "language": "en", "format": "json"},
    )
    results = data.get("results") or []
    if not results:
        raise ValueError(f"No geocoding results for '{name}'")

    match = next(
        (item for item in results if item.get("country_code") == country_code),
        results[0],
    )
    return Coordinates(
        name=match.get("name", name),
        latitude=float(match["latitude"]),
        longitude=float(match["longitude"]),
        country=match.get("country", country_code),
        timezone=match.get("timezone", get_digest_timezone()),
        elevation=float(match["elevation"]) if match.get("elevation") is not None else None,
    )


def fetch_forecast(coords: Coordinates) -> tuple[CurrentConditions, list[DailyForecast]]:
    data = _request_json(
        FORECAST_API_URL,
        {
            "latitude": coords.latitude,
            "longitude": coords.longitude,
            "timezone": coords.timezone,
            "current": [
                "temperature_2m",
                "apparent_temperature",
                "relative_humidity_2m",
                "precipitation",
                "weather_code",
                "cloud_cover",
                "wind_speed_10m",
                "wind_direction_10m",
            ],
            "daily": [
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "wind_speed_10m_max",
                "sunrise",
                "sunset",
            ],
            "forecast_days": 3,
        },
    )

    current_raw = data.get("current") or {}
    weather_code = current_raw.get("weather_code")
    current = CurrentConditions(
        temperature_c=current_raw.get("temperature_2m"),
        apparent_temperature_c=current_raw.get("apparent_temperature"),
        humidity_percent=current_raw.get("relative_humidity_2m"),
        wind_speed_kmh=current_raw.get("wind_speed_10m"),
        wind_direction_deg=current_raw.get("wind_direction_10m"),
        precipitation_mm=current_raw.get("precipitation"),
        cloud_cover_percent=current_raw.get("cloud_cover"),
        weather_code=weather_code,
        weather_description=wmo_description(weather_code),
        observed_at=current_raw.get("time"),
    )

    daily_raw = data.get("daily") or {}
    dates = daily_raw.get("time") or []
    daily_forecasts: list[DailyForecast] = []
    for index, date in enumerate(dates):
        code = _safe_index(daily_raw.get("weather_code"), index)
        daily_forecasts.append(
            DailyForecast(
                date=date,
                temp_min_c=_safe_index(daily_raw.get("temperature_2m_min"), index),
                temp_max_c=_safe_index(daily_raw.get("temperature_2m_max"), index),
                precipitation_sum_mm=_safe_index(daily_raw.get("precipitation_sum"), index),
                wind_max_kmh=_safe_index(daily_raw.get("wind_speed_10m_max"), index),
                weather_code=code,
                weather_description=wmo_description(code),
                sunrise=_safe_index(daily_raw.get("sunrise"), index),
                sunset=_safe_index(daily_raw.get("sunset"), index),
            )
        )

    return current, daily_forecasts


def _safe_index(values: list[Any] | None, index: int) -> Any | None:
    if not values or index >= len(values):
        return None
    return values[index]


def fetch_city_weather(city: CityConfig) -> CityWeather:
    result = CityWeather(city_name=city.name)
    try:
        coords = geocode_city(city.name, city.country_code)
        current, daily = fetch_forecast(coords)
        result.coordinates = coords
        result.current = current
        result.daily = daily
    except Exception as exc:
        result.error = str(exc)
    return result


def build_weather_report(
    cities: tuple[CityConfig, ...] | None = None,
    timezone: str | None = None,
) -> WeatherReport:
    tz = timezone or get_digest_timezone()
    city_list = cities or DEFAULT_CITIES
    city_results = [fetch_city_weather(city) for city in city_list]
    return WeatherReport(
        generated_at=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        timezone=tz,
        cities=city_results,
    )
