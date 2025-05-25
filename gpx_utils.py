# projekt_gpx_viewer/gpx_utils.py
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime # datetime direkt importieren
import gpxpy
import gpxpy.gpx # Für GPXXMLSyntaxException
import traceback # Für detaillierte Fehlerausgabe

# Hilfsfunktion zur sicheren Extraktion von Zeitstempeln
def _get_time_from_gpx_element(element: Any) -> Optional[datetime]:
    """Extrahiert und konvertiert Zeitstempel sicher."""
    if hasattr(element, 'time') and element.time:
        # Konvertiere zu naivem datetime, falls Zeitzoneninfo vorhanden ist
        # SQLAlchemy mit SQLite erwartet oft naive datetimes
        return element.time.replace(tzinfo=None)
    return None

def parse_gpx_data_from_content(original_filename: str, file_content_bytes: bytes) -> Optional[Dict[str, Any]]:
    """
    Parst GPX-Daten aus Bytes und gibt ein strukturiertes Dictionary zurück.
    Beinhaltet: track_name, distance_km, track_date (datetime), total_ascent, total_descent,
                 original_filename, points (List[List[float]]).
    Das Feld 'elevation_data' für das Chart wird separat über get_elevation_data_for_chart geholt.
    """
    try:
        gpx_content_str = file_content_bytes.decode('utf-8', errors='replace') # replace für ungültige Bytes
        gpx = gpxpy.parse(gpx_content_str)

        if not gpx.tracks and not gpx.routes:
            print(f"Warnung: Keine Tracks oder Routen in Datei {original_filename} gefunden.")
            return None

        # Track-Namen extrahieren
        track_name = gpx.name
        if not track_name and gpx.tracks and gpx.tracks[0].name:
            track_name = gpx.tracks[0].name
        if not track_name and gpx.routes and gpx.routes[0].name:
            track_name = gpx.routes[0].name
        if not track_name: # Fallback auf Dateinamen ohne Extension
            track_name = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename
        
        # Gesamtdistanz
        # gpx.length_3d() ist präferiert, dann gpx.length_2d()
        distance_m = gpx.length_3d() if gpx.length_3d() is not None else (gpx.length_2d() if gpx.length_2d() is not None else 0.0)
        distance_km = distance_m / 1000.0

        # Track-Datum (erster Zeitstempel im Track oder GPX-Metadaten)
        track_date_obj: Optional[datetime] = None
        if gpx.time:
            track_date_obj = _get_time_from_gpx_element(gpx)
        
        if not track_date_obj: # Suche in Tracks/Routen, falls gpx.time nicht gesetzt
            point_sources = gpx.tracks + gpx.routes
            for item in point_sources:
                if hasattr(item, 'segments'): # Für Tracks
                    for segment in item.segments:
                        if segment.points:
                            track_date_obj = _get_time_from_gpx_element(segment.points[0])
                            if track_date_obj: break
                    if track_date_obj: break
                elif hasattr(item, 'points') and item.points: # Für Routen
                    track_date_obj = _get_time_from_gpx_element(item.points[0])
                    if track_date_obj: break
        
        # Anstieg und Abstieg
        uphill, downhill = 0.0, 0.0
        try:
            # Diese Methode kann fehlschlagen, wenn Höhendaten fehlen oder inkonsistent sind
            raw_uphill, raw_downhill = gpx.get_uphill_downhill()
            uphill = raw_uphill if raw_uphill is not None else 0.0
            downhill = raw_downhill if raw_downhill is not None else 0.0
        except Exception as e_ele:
            print(f"Warnung: Konnte Anstieg/Abstieg für {original_filename} nicht berechnen: {e_ele}")

        # Geographische Punkte für die Kartenanzeige sammeln
        points_list: List[List[float]] = []
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    points_list.append([point.latitude, point.longitude])
        if not points_list and gpx.routes: # Fallback auf Routenpunkte
            for route in gpx.routes:
                for point in route.points:
                    points_list.append([point.latitude, point.longitude])
        
        parsed_result = {
            "original_filename": original_filename,
            "track_name": track_name or "Unbenannter Track",
            "distance_km": round(distance_km, 2),
            "track_date": track_date_obj, # Kann None sein, DB sollte das erlauben (nullable=True)
            "total_ascent": round(uphill, 2),
            "total_descent": round(downhill, 2),
            "points": points_list, # Für Karten-Polyline
            # "labels_list": [] # Wird initial leer sein, Bearbeitung später
        }
        # print(f"DEBUG gpx_utils: Parsed data for {original_filename}: {parsed_result}")
        return parsed_result

    except gpxpy.gpx.GPXXMLSyntaxException as e_gpx_syntax:
        print(f"GPX Syntax Fehler in Datei {original_filename}: {e_gpx_syntax}")
        # ui.notify aus main.py aufrufen, nicht hier direkt
        return None # Signalisiert einen Fehler
    except Exception as e:
        print(f"Allgemeiner Fehler beim Parsen von GPX {original_filename}: {e}")
        traceback.print_exc()
        return None


def get_points_from_gpx_file(gpx_filepath_str: str) -> List[List[float]]:
    """Extrahiert alle geographischen Punkte [[lat, lon], ...] aus einer GPX-Datei."""
    points = []
    try:
        with open(gpx_filepath_str, 'r', encoding='utf-8') as f:
            gpx_file_content = f.read()
            if not gpx_file_content.strip(): return [] # Leere Datei
            gpx = gpxpy.parse(gpx_file_content)

        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    points.append([point.latitude, point.longitude])
        if not points and gpx.routes:
             for route in gpx.routes:
                for point in route.points:
                    points.append([point.latitude, point.longitude])
        return points
    except FileNotFoundError:
        print(f"Fehler: GPX-Datei nicht gefunden unter {gpx_filepath_str}")
        return []
    except gpxpy.gpx.GPXXMLSyntaxException as e_gpx_syntax:
        print(f"GPX Syntax Fehler beim Lesen der Punkte aus {gpx_filepath_str}: {e_gpx_syntax}")
        return []
    except Exception as e:
        print(f"Fehler beim Extrahieren der Punkte aus {gpx_filepath_str}: {e}")
        traceback.print_exc()
        return []

def get_bounds_for_points(points_list: List[List[float]]) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Berechnet die Bounding Box ((min_lat, min_lon), (max_lat, max_lon)) für eine Liste von Punkten."""
    if not points_list or not all(isinstance(p, list) and len(p) == 2 for p in points_list):
        return None
    try:
        # Filtere ungültige Punkte heraus (z.B. None oder falsche Typen, obwohl points_list List[List[float]] sein sollte)
        valid_points = [p for p in points_list if isinstance(p[0], (int, float)) and isinstance(p[1], (int, float))]
        if not valid_points:
            return None

        min_lat = min(p[0] for p in valid_points)
        max_lat = max(p[0] for p in valid_points)
        min_lon = min(p[1] for p in valid_points)
        max_lon = max(p[1] for p in valid_points)

        # Wenn alle Punkte identisch sind oder auf einer exakten Linie liegen,
        # erweitere die Bounds leicht, damit Leaflet eine Fläche zoomen kann.
        padding = 0.0001 # Kleiner Wert
        if min_lat == max_lat:
            min_lat -= padding
            max_lat += padding
        if min_lon == max_lon:
            min_lon -= padding
            max_lon += padding
            
        # Zusätzliche Sicherheitsprüfung für gültige geographische Bereiche
        if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90 and
                -180 <= min_lon <= 180 and -180 <= max_lon <= 180 and
                min_lat <= max_lat and min_lon <= max_lon):
            print(f"Warnung: Ungültige Bounds berechnet: Lat({min_lat}-{max_lat}), Lon({min_lon}-{max_lon})")
            return None # Ungültige Bounds nicht verwenden

        return ((min_lat, min_lon), (max_lat, max_lon))
    except Exception as e:
        print(f"Fehler bei get_bounds_for_points: {e}")
        traceback.print_exc()
        return None


def get_elevation_data_for_chart(gpx_filepath_str: str) -> Optional[Dict[str, Any]]:
    """
    Extrahiert Höhendaten entlang der Strecke für ein Chart.
    Gibt ein Dict zurück: {"categories": [distanzen_km], "series_data": [höhen_m]}
    """
    categories_dist_km: List[float] = []
    series_elev_m: List[float] = []
    current_total_distance_km = 0.0
    
    try:
        with open(gpx_filepath_str, 'r', encoding='utf-8') as f:
            gpx_file_content = f.read()
            if not gpx_file_content.strip(): return None
            gpx = gpxpy.parse(gpx_file_content)

        all_gpx_points_in_order = []
        for track in gpx.tracks:
            for segment in track.segments:
                all_gpx_points_in_order.extend(segment.points)
        if not all_gpx_points_in_order and gpx.routes: # Fallback
            for route in gpx.routes:
                all_gpx_points_in_order.extend(route.points)
        
        if not all_gpx_points_in_order:
            return None

        previous_point_for_dist_calc = None
        for point in all_gpx_points_in_order:
            if point.elevation is not None: # Nur Punkte mit Höhendaten berücksichtigen
                if previous_point_for_dist_calc:
                    # Berechne Distanzinkrement zum vorherigen Punkt (egal ob dieser Höhe hatte)
                    # distance_increment_m = point.distance_3d(previous_point_for_dist_calc) # 3D ist genauer
                    # Robuster für Chart: 2D-Distanz, da Höhen oft ungenau sind
                    distance_increment_m = point.distance_2d(previous_point_for_dist_calc)
                    if distance_increment_m is not None:
                         current_total_distance_km += distance_increment_m / 1000.0
                
                categories_dist_km.append(round(current_total_distance_km, 3))
                series_elev_m.append(round(point.elevation, 2))
            
            # Aktualisiere immer den previous_point_for_dist_calc, um die Distanz kontinuierlich zu machen
            previous_point_for_dist_calc = point 

        if categories_dist_km and series_elev_m:
            return {"categories": categories_dist_km, "series_data": series_elev_m}
        return None
        
    except FileNotFoundError:
        print(f"Fehler: GPX-Datei nicht gefunden für Höhenprofil: {gpx_filepath_str}")
        return None
    except gpxpy.gpx.GPXXMLSyntaxException as e_gpx_syntax:
        print(f"GPX Syntax Fehler beim Lesen der Höhendaten aus {gpx_filepath_str}: {e_gpx_syntax}")
        return None
    except Exception as e:
        print(f"Fehler beim Extrahieren der Höhendaten aus {gpx_filepath_str}: {e}")
        traceback.print_exc()
        return None