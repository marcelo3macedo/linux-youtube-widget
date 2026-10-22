"""
MPRIS and System Volume Controller for YouTube Widget
Handles D-Bus communication with media players (browsers, Spotify, etc.)
and system volume management via PipeWire (wpctl) / PulseAudio (amixer).
"""

import subprocess
import urllib.parse
import webbrowser
import logging

try:
    import gi
    gi.require_version('Gio', '2.0')
    gi.require_version('GLib', '2.0')
    from gi.repository import Gio, GLib
    HAS_GIO = True
except Exception:
    HAS_GIO = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mpris_controller")


class MediaController:
    def __init__(self):
        self._bus = None
        self._init_bus()

    def _init_bus(self):
        if not HAS_GIO:
            return
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception as e:
            logger.debug(f"Could not connect to session bus: {e}")
            self._bus = None

    def get_active_players(self):
        """Returns list of DBus names for active MPRIS players."""
        if not self._bus:
            self._init_bus()
        if not self._bus:
            return []

        try:
            proxy = Gio.DBusProxy.new_sync(
                self._bus,
                Gio.DBusProxyFlags.NONE,
                None,
                'org.freedesktop.DBus',
                '/org/freedesktop/DBus',
                'org.freedesktop.DBus',
                None
            )
            names_variant = proxy.call_sync(
                'ListNames', None, Gio.DBusCallFlags.NONE, -1, None
            )
            all_names = names_variant.unpack()[0]
            players = [n for n in all_names if n.startswith('org.mpris.MediaPlayer2.')]
            
            # Prioritize browser / youtube players
            def sort_key(name):
                lower = name.lower()
                if 'youtube' in lower:
                    return 0
                if 'chrome' in lower or 'chromium' in lower or 'brave' in lower:
                    return 1
                if 'firefox' in lower:
                    return 2
                return 3

            players.sort(key=sort_key)
            return players
        except Exception as e:
            logger.debug(f"Error fetching active players: {e}")
            return []

    def _call_player_method(self, method_name):
        players = self.get_active_players()
        if not players:
            return False

        success = False
        for player in players:
            try:
                proxy = Gio.DBusProxy.new_sync(
                    self._bus,
                    Gio.DBusProxyFlags.NONE,
                    None,
                    player,
                    '/org/mpris/MediaPlayer2',
                    'org.mpris.MediaPlayer2.Player',
                    None
                )
                proxy.call_sync(method_name, None, Gio.DBusCallFlags.NONE, -1, None)
                success = True
                break
            except Exception as e:
                logger.debug(f"Error calling {method_name} on {player}: {e}")
                continue
        return success

    def play_pause(self):
        return self._call_player_method('PlayPause')

    def next(self):
        return self._call_player_method('Next')

    def previous(self):
        return self._call_player_method('Previous')

    def get_playback_info(self):
        """Returns {title, artist, status, player} of the current playing media."""
        players = self.get_active_players()
        if not players:
            return {
                'title': 'Nenhuma reprodução ativa',
                'artist': 'Abra o YouTube no navegador',
                'status': 'Stopped',
                'player': None
            }

        for player in players:
            try:
                props = Gio.DBusProxy.new_sync(
                    self._bus,
                    Gio.DBusProxyFlags.NONE,
                    None,
                    player,
                    '/org/mpris/MediaPlayer2',
                    'org.freedesktop.DBus.Properties',
                    None
                )
                
                status_v = props.call_sync(
                    'Get',
                    GLib.Variant('(ss)', ('org.mpris.MediaPlayer2.Player', 'PlaybackStatus')),
                    Gio.DBusCallFlags.NONE,
                    -1,
                    None
                )
                status = status_v.unpack()[0]

                meta_v = props.call_sync(
                    'Get',
                    GLib.Variant('(ss)', ('org.mpris.MediaPlayer2.Player', 'Metadata')),
                    Gio.DBusCallFlags.NONE,
                    -1,
                    None
                )
                metadata = meta_v.unpack()[0]
                
                title = metadata.get('xesam:title', 'Sem título')
                artists = metadata.get('xesam:artist', [])
                if isinstance(artists, (list, tuple)) and len(artists) > 0:
                    artist = ", ".join(artists)
                elif isinstance(artists, str):
                    artist = artists
                else:
                    artist = player.split('.')[-1].capitalize()

                # Clean player name
                player_display = player.replace('org.mpris.MediaPlayer2.', '')
                if '.' in player_display:
                    player_display = player_display.split('.')[0]

                return {
                    'title': str(title),
                    'artist': str(artist),
                    'status': str(status),
                    'player': player_display.capitalize()
                }
            except Exception:
                continue

        return {
            'title': 'YouTube / Mídia pausada',
            'artist': '',
            'status': 'Paused',
            'player': None
        }


class VolumeController:
    """Controls system volume via wpctl (PipeWire) or amixer (ALSA/Pulse)."""

    @staticmethod
    def get_volume():
        """Returns (volume_float_0_to_1, is_muted_bool)."""
        # Try wpctl
        try:
            res = subprocess.run(
                ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
                capture_output=True,
                text=True,
                check=False
            )
            if res.returncode == 0 and res.stdout:
                line = res.stdout.strip()
                # Output format: "Volume: 0.65" or "Volume: 0.65 [MUTED]"
                parts = line.split()
                if len(parts) >= 2:
                    vol = float(parts[1])
                    muted = "[MUTED]" in line
                    return max(0.0, min(1.0, vol)), muted
        except Exception:
            pass

        # Fallback amixer
        try:
            res = subprocess.run(
                ["amixer", "-D", "pulse", "sget", "Master"],
                capture_output=True,
                text=True,
                check=False
            )
            if res.returncode != 0:
                res = subprocess.run(
                    ["amixer", "sget", "Master"],
                    capture_output=True,
                    text=True,
                    check=False
                )
            if res.returncode == 0 and res.stdout:
                import re
                vol_match = re.search(r'\[(\d+)%\]', res.stdout)
                mute_match = re.search(r'\[(on|off)\]', res.stdout)
                vol = float(vol_match.group(1)) / 100.0 if vol_match else 0.5
                muted = (mute_match.group(1) == 'off') if mute_match else False
                return max(0.0, min(1.0, vol)), muted
        except Exception:
            pass

        return 0.5, False

    @staticmethod
    def set_volume(level):
        """Sets volume to level (0.0 to 1.0)."""
        level = max(0.0, min(1.0, float(level)))
        try:
            subprocess.run(
                ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{level:.2f}"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return True
        except Exception:
            pass

        try:
            percent = int(level * 100)
            subprocess.run(
                ["amixer", "-D", "pulse", "sset", "Master", f"{percent}%"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return True
        except Exception:
            return False

    @staticmethod
    def toggle_mute():
        try:
            subprocess.run(
                ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return True
        except Exception:
            pass

        try:
            subprocess.run(
                ["amixer", "-D", "pulse", "sset", "Master", "toggle"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return True
        except Exception:
            return False


def open_youtube(query=None, is_music=False):
    """Opens YouTube or YouTube Music with an optional search query."""
    if is_music:
        if query and query.strip():
            url = f"https://music.youtube.com/search?q={urllib.parse.quote_plus(query.strip())}"
        else:
            url = "https://music.youtube.com"
    else:
        if query and query.strip():
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query.strip())}"
        else:
            url = "https://www.youtube.com"

    try:
        if HAS_GIO:
            Gio.AppInfo.launch_default_for_uri(url, None)
            return url
    except Exception:
        pass

    try:
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return url
    except Exception:
        webbrowser.open(url)
        return url
