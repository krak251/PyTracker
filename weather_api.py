import aiohttp
import asyncio


async def get_city_coordinates(city_name: str):
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&language=ru"

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if "results" in data and len(data["results"]) > 0:
                        location = data["results"][0]
                        return location["latitude"], location["longitude"], location["name"]
                    else:
                        print(f"Город '{city_name}' не найден в API.")
                else:
                    print(f"Ошибка Geocoding API: статус {response.status}")

    except asyncio.TimeoutError:
        print("Ошибка: Таймаут при поиске координат города.")
    except aiohttp.ClientError as e:
        print(f"Сетевая ошибка при поиске координат: {e}")
    except Exception as e:
        print(f"Непредвиденная ошибка в get_city_coordinates: {e}")

    return None, None, None


async def get_current_weather(lat: float, lon: float):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if "current_weather" in data:
                        return data["current_weather"]
                    else:
                        print("В ответе API погоды отсутствуют данные current_weather.")
                else:
                    print(f"Ошибка Weather API: статус {response.status}")

    except asyncio.TimeoutError:
        print("Ошибка: Таймаут при получении данных о погоде.")
    except aiohttp.ClientError as e:
        print(f"Сетевая ошибка при получении погоды: {e}")
    except Exception as e:
        print(f"Непредвиденная ошибка в get_current_weather: {e}")

    return None
