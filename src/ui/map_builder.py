"""
Folium interactive map builder for Birding Needs Finder.
"""
import folium
import pandas as pd
from folium.plugins import MarkerCluster

# Cap per-layer marker count to keep the map responsive
_MAP_CAP = 400

_SCOPE_COLORS = {
    "local": "orange",
    "state": "blue",
    "usa":   "green",
}

_SCOPE_LABELS = {
    "local": "Local birds",
    "state": "State birds",
    "usa":   "US birds",
}


def _popup_html(row: pd.Series) -> str:
    return f"""
    <div style="min-width:190px; font-family:sans-serif">
        <b style="font-size:14px">{row['Common Name']}</b><br>
        <i style="color:#666">{row['Scientific Name']}</i><br><br>
        📍 {row['Location']}<br>
        📅 Last seen: {row['Last Seen']}<br>
        📏 {row['Miles Away']:.1f} mi away<br>
        🔢 Count: {row['Count']}
    </div>"""


def build_needs_map(
    user_lat: float,
    user_lng: float,
    local_df: pd.DataFrame,
    state_df: pd.DataFrame,
    usa_df: pd.DataFrame,
) -> folium.Map:
    """Return a folium Map with clustered, layer-controlled bird markers."""
    m = folium.Map(
        location=[user_lat, user_lng],
        zoom_start=9,
        tiles=None,  # added manually so LayerControl includes them
    )

    # Tile layers
    folium.TileLayer("OpenStreetMap", name="Street map").add_to(m)
    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services"
            "/World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        attr="Esri World Imagery",
        name="Satellite",
    ).add_to(m)

    # Bird layers
    scope_dfs = {
        "local": local_df,
        "state": state_df,
        "usa":   usa_df,
    }
    for scope, df in scope_dfs.items():
        if df.empty:
            continue
        fg = folium.FeatureGroup(name=_SCOPE_LABELS[scope], show=True)
        cluster = MarkerCluster(
            options={"maxClusterRadius": 50, "spiderfyOnMaxZoom": True}
        )
        for _, row in df.head(_MAP_CAP).iterrows():
            folium.Marker(
                location=[row["lat"], row["lng"]],
                popup=folium.Popup(_popup_html(row), max_width=260),
                tooltip=f"{row['Common Name']} — {row['Miles Away']:.1f} mi",
                icon=folium.Icon(color=_SCOPE_COLORS[scope]),
            ).add_to(cluster)
        cluster.add_to(fg)
        fg.add_to(m)

    # User location — blue dot with white border (like iOS/Android maps)
    folium.CircleMarker(
        location=[user_lat, user_lng],
        radius=10,
        color="#ffffff",
        weight=2,
        fill=True,
        fill_color="#4285F4",
        fill_opacity=1.0,
        tooltip="Your location",
        popup="You are here",
    ).add_to(m)
    # Subtle accuracy halo
    folium.CircleMarker(
        location=[user_lat, user_lng],
        radius=22,
        color="#4285F4",
        weight=1,
        fill=True,
        fill_color="#4285F4",
        fill_opacity=0.15,
    ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m
