"""
YouTube Music Search and Metadata API
Fetches tracks, artists, and video IDs directly from YouTube Music InnerTube API.
"""

import json
import urllib.request
import urllib.parse
import re
import logging

logger = logging.getLogger("ytmusic_api")


def search_youtube_music(query, limit=15):
    """
    Searches YouTube Music for tracks and returns a list of dictionaries:
    [{'videoId': str, 'title': str, 'artist': str, 'thumbnail': str}]
    """
    if not query or not query.strip():
        return []

    query = query.strip()
    payload = {
        "context": {
            "client": {
                "clientName": "WEB_REMIX",
                "clientVersion": "1.20240101.01.00",
                "hl": "pt",
                "gl": "BR"
            }
        },
        "query": query
    }

    req = urllib.request.Request(
        "https://music.youtube.com/youtubei/v1/search",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        logger.error(f"Error querying YouTube Music API: {e}")
        # Try fallback via standard scrape
        return _fallback_search(query, limit)

    songs = []
    seen_ids = set()

    def walk(obj):
        if len(songs) >= limit:
            return
        if isinstance(obj, dict):
            if "musicResponsiveListItemRenderer" in obj:
                renderer = obj["musicResponsiveListItemRenderer"]
                flex = renderer.get("flexColumns", [])
                title = "Música Desconhecida"
                artist = "YouTube Music"
                video_id = None

                # Check playlistItemData
                if "playlistItemData" in renderer:
                    video_id = renderer["playlistItemData"].get("videoId")

                if flex:
                    try:
                        title_col = flex[0]["musicResponsiveListItemFlexColumnRenderer"]
                        runs = title_col.get("text", {}).get("runs", [])
                        if runs:
                            title = runs[0].get("text", title)
                            if not video_id:
                                ep = runs[0].get("navigationEndpoint", {})
                                video_id = ep.get("watchEndpoint", {}).get("videoId")
                    except Exception:
                        pass

                    if len(flex) > 1:
                        try:
                            artist_col = flex[1]["musicResponsiveListItemFlexColumnRenderer"]
                            runs = artist_col.get("text", {}).get("runs", [])
                            if runs:
                                artist_texts = [r.get("text", "") for r in runs]
                                artist = "".join(artist_texts)
                        except Exception:
                            pass

                # Check thumbnails
                thumbnail = None
                try:
                    thumbs = renderer.get("thumbnail", {}).get("musicThumbnailRenderer", {}).get("thumbnail", {}).get("thumbnails", [])
                    if thumbs:
                        thumbnail = thumbs[-1].get("url")
                except Exception:
                    pass

                if video_id and video_id not in seen_ids:
                    seen_ids.add(video_id)
                    songs.append({
                        "videoId": video_id,
                        "title": title,
                        "artist": artist,
                        "thumbnail": thumbnail
                    })
            else:
                for v in obj.values():
                    walk(v)
        elif isinstance(obj, list):
            for i in obj:
                walk(i)

    walk(data)

    if not songs:
        return _fallback_search(query, limit)

    return songs


def _fallback_search(query, limit=15):
    """Fallback search using YouTube scrape if InnerTube returns empty."""
    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query + ' audio')}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        matches = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})".+?"title":\{"runs":\[\{"text":"([^"]+)"\}', html)
        songs = []
        seen = set()
        for vid, title in matches:
            if vid not in seen:
                seen.add(vid)
                songs.append({
                    "videoId": vid,
                    "title": title,
                    "artist": "YouTube Music",
                    "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
                })
                if len(songs) >= limit:
                    break
        return songs
    except Exception as e:
        logger.error(f"Fallback search failed: {e}")
        return []
