"""
MPRIS2 D-Bus Service for YouTube Music Widget
Allows the GNOME Top Bar Extension and system media controls to control the widget.
"""

import logging
import gi

gi.require_version('Gio', '2.0')
gi.require_version('GLib', '2.0')
from gi.repository import Gio, GLib

logger = logging.getLogger("mpris_server")

MPRIS_XML = """
<node>
  <interface name='org.mpris.MediaPlayer2'>
    <method name='Raise'/>
    <method name='Quit'/>
    <property name='CanQuit' type='b' access='read'/>
    <property name='CanRaise' type='b' access='read'/>
    <property name='Identity' type='s' access='read'/>
    <property name='SupportedUriSchemes' type='as' access='read'/>
    <property name='SupportedMimeTypes' type='as' access='read'/>
  </interface>
  <interface name='org.mpris.MediaPlayer2.Player'>
    <method name='Next'/>
    <method name='Previous'/>
    <method name='Pause'/>
    <method name='PlayPause'/>
    <method name='Stop'/>
    <method name='Play'/>
    <method name='Search'>
      <arg type='s' name='query' direction='in'/>
    </method>
    <property name='PlaybackStatus' type='s' access='read'/>
    <property name='Metadata' type='a{sv}' access='read'/>
    <property name='CanControl' type='b' access='read'/>
    <property name='CanPlay' type='b' access='read'/>
    <property name='CanPause' type='b' access='read'/>
    <property name='CanGoNext' type='b' access='read'/>
    <property name='CanGoPrevious' type='b' access='read'/>
  </interface>
</node>
"""


class MPRISService:
    def __init__(self, widget):
        self.widget = widget
        self._owner_id = 0
        self._connection = None
        self._node_info = Gio.DBusNodeInfo.new_for_xml(MPRIS_XML)

        try:
            self._owner_id = Gio.bus_own_name(
                Gio.BusType.SESSION,
                "org.mpris.MediaPlayer2.youtube_widget",
                Gio.BusNameOwnerFlags.NONE,
                self._on_bus_acquired,
                self._on_name_acquired,
                self._on_name_lost
            )
        except Exception as e:
            logger.debug(f"Could not own MPRIS name: {e}")

    def _on_bus_acquired(self, connection, name):
        self._connection = connection
        for iface in self._node_info.interfaces:
            connection.register_object(
                "/org/mpris/MediaPlayer2",
                iface,
                self._handle_method_call,
                self._handle_get_property,
                None
            )

    def _on_name_acquired(self, connection, name):
        logger.info(f"MPRIS name {name} acquired successfully")

    def _on_name_lost(self, connection, name):
        logger.warning(f"MPRIS name {name} lost or already owned")

    def _handle_method_call(self, conn, sender, path, iface_name, method_name, params, invocation):
        if iface_name == "org.mpris.MediaPlayer2":
            if method_name == "Raise":
                GLib.idle_add(self.widget.present)
                invocation.return_value(None)
            elif method_name == "Quit":
                GLib.idle_add(self.widget.do_destroy)
                invocation.return_value(None)
            else:
                invocation.return_value(None)

        elif iface_name == "org.mpris.MediaPlayer2.Player":
            if method_name == "PlayPause":
                GLib.idle_add(self.widget.player.toggle)
                invocation.return_value(None)
            elif method_name == "Play":
                GLib.idle_add(self.widget.player.resume)
                invocation.return_value(None)
            elif method_name == "Pause":
                GLib.idle_add(self.widget.player.pause)
                invocation.return_value(None)
            elif method_name == "Stop":
                GLib.idle_add(self.widget.player.stop)
                invocation.return_value(None)
            elif method_name == "Next":
                GLib.idle_add(self.widget.play_next)
                invocation.return_value(None)
            elif method_name == "Previous":
                GLib.idle_add(self.widget.play_previous)
                invocation.return_value(None)
            elif method_name == "Search":
                query = params.unpack()[0]
                if query:
                    GLib.idle_add(self._trigger_search, query)
                invocation.return_value(None)
            else:
                invocation.return_value(None)

    def _trigger_search(self, query):
        self.widget.search_entry.set_text(query)
        self.widget._start_search(query)
        self.widget.present()

    def _handle_get_property(self, conn, sender, path, iface_name, prop_name):
        if iface_name == "org.mpris.MediaPlayer2":
            if prop_name == "Identity":
                return GLib.Variant('s', "YouTube Music Widget")
            elif prop_name in ("CanQuit", "CanRaise"):
                return GLib.Variant('b', True)
            elif prop_name in ("SupportedUriSchemes", "SupportedMimeTypes"):
                return GLib.Variant('as', [])

        elif iface_name == "org.mpris.MediaPlayer2.Player":
            if prop_name == "PlaybackStatus":
                status = "Playing" if self.widget.player.is_playing() else (
                    "Paused" if self.widget.current_index >= 0 else "Stopped"
                )
                return GLib.Variant('s', status)
            elif prop_name == "Metadata":
                meta = {}
                if self.widget.results and 0 <= self.widget.current_index < len(self.widget.results):
                    song = self.widget.results[self.widget.current_index]
                    meta["xesam:title"] = GLib.Variant('s', song.get("title", "YouTube Music"))
                    artist = song.get("artist", "")
                    meta["xesam:artist"] = GLib.Variant('as', [artist] if artist else [])
                else:
                    meta["xesam:title"] = GLib.Variant('s', "YouTube Music")
                    meta["xesam:artist"] = GLib.Variant('as', ["Pronto para reproduzir"])
                return GLib.Variant('a{sv}', meta)
            elif prop_name in ("CanControl", "CanPlay", "CanPause", "CanGoNext", "CanGoPrevious"):
                return GLib.Variant('b', True)

        return None
