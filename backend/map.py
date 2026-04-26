from pathlib import Path

import folium
import requests
from geopy.geocoders import Nominatim


def find_nearby_pharmacies(limit=20):
    city = "Bangalore"
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": f"pharmacy {city}",
        "format": "json",
        "limit": limit,
    }
    headers = {"User-Agent": "aushadhi-saathi/1.0"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=20)
        response.raise_for_status()
        places = response.json()
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to fetch nearby pharmacies: {exc}") from exc

    geolocator = Nominatim(user_agent="aushadhi-saathi/1.0")
    location = geolocator.geocode(city)
    if location is None:
        raise ValueError(f"Could not geocode city '{city}'.")

    m = folium.Map(location=[location.latitude, location.longitude], zoom_start=13)

    for place in places:
        lat = place.get("lat")
        lon = place.get("lon")
        display_name = place.get("display_name", "Pharmacy")
        if not lat or not lon:
            continue

        folium.Marker(
            location=[float(lat), float(lon)],
            popup=display_name,
            tooltip="Click for details",
            icon=folium.Icon(color="red", icon="plus", prefix="fa"),
        ).add_to(m)

    output_dir = Path(__file__).resolve().parent / "templates"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "map.html"
    m.save(str(output_file))

    print(f"Found {len(places)} pharmacies. Map saved at: {output_file}")
    return places


if __name__ == "__main__":
    find_nearby_pharmacies()
