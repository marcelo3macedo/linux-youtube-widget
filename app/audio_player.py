"""
Native GStreamer Audio Player for YouTube Music Widget
Extracts direct audio streams via yt_dlp and plays natively through PipeWire/PulseAudio.
"""

import threading
import logging
import gi

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

import yt_dlp

logger = logging.getLogger("audio_player")


class AudioPlayer:
    def __init__(self, on_eos=None, on_error=None, on_state_changed=None):
        Gst.init(None)
        self.player = Gst.ElementFactory.make("playbin", "ytm_player")
        self.on_eos = on_eos
        self.on_error = on_error
        self.on_state_changed = on_state_changed

        self.current_video_id = None
        self.current_title = None
        self._is_playing = False
        self._url_cache = {}
        self._play_lock = threading.Lock()
        self._current_load_id = 0

        # Setup GStreamer bus watch
        bus = self.player.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus_message)

        # yt-dlp configuration optimized for fast audio extraction
        self.ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'noplaylist': True,
            'extract_flat': False,
            'socket_timeout': 10,
        }

    def _on_bus_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            logger.info("End of stream reached")
            self._is_playing = False
            if self.on_state_changed:
                GLib.idle_add(self.on_state_changed, False)
            if self.on_eos:
                GLib.idle_add(self.on_eos)
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            logger.error(f"GStreamer Error: {err} | Debug: {debug}")
            self.stop()
            if self.on_error:
                GLib.idle_add(self.on_error, str(err))
        elif t == Gst.MessageType.STATE_CHANGED:
            if message.src == self.player:
                old_state, new_state, pending_state = message.parse_state_changed()
                is_now_playing = (new_state == Gst.State.PLAYING)
                if is_now_playing != self._is_playing:
                    self._is_playing = is_now_playing
                    if self.on_state_changed:
                        GLib.idle_add(self.on_state_changed, self._is_playing)

    def play(self, video_id, title=None, on_loading=None):
        """Resolves audio stream URL in background and begins playback."""
        with self._play_lock:
            self._current_load_id += 1
            load_id = self._current_load_id
            self.current_video_id = video_id
            self.current_title = title

        # Notify UI that we are resolving/loading the stream
        if on_loading:
            GLib.idle_add(on_loading, True)

        def worker():
            stream_url = self._url_cache.get(video_id)
            if not stream_url:
                try:
                    yt_url = f"https://www.youtube.com/watch?v={video_id}"
                    with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                        info = ydl.extract_info(yt_url, download=False)
                        stream_url = info.get('url')
                        if stream_url:
                            self._url_cache[video_id] = stream_url
                except Exception as e:
                    logger.error(f"Failed to extract stream for {video_id}: {e}")
                    if on_loading:
                        GLib.idle_add(on_loading, False)
                    if self.on_error:
                        GLib.idle_add(self.on_error, f"Erro ao obter áudio: {e}")
                    return

            # Check if user clicked another track in the meantime
            with self._play_lock:
                if self._current_load_id != load_id:
                    return

            GLib.idle_add(self._start_stream, stream_url, on_loading)

        threading.Thread(target=worker, daemon=True).start()

    def _start_stream(self, stream_url, on_loading=None):
        if on_loading:
            on_loading(False)
        try:
            self.player.set_state(Gst.State.NULL)
            self.player.set_property("uri", stream_url)
            ret = self.player.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                logger.error("Failed to set GStreamer state to PLAYING")
                if self.on_error:
                    self.on_error("Falha ao iniciar reprodução de áudio")
            else:
                self._is_playing = True
                if self.on_state_changed:
                    self.on_state_changed(True)
        except Exception as e:
            logger.error(f"Error starting stream: {e}")
            if self.on_error:
                self.on_error(str(e))

    def pause(self):
        self.player.set_state(Gst.State.PAUSED)
        self._is_playing = False
        if self.on_state_changed:
            self.on_state_changed(False)

    def resume(self):
        self.player.set_state(Gst.State.PLAYING)
        self._is_playing = True
        if self.on_state_changed:
            self.on_state_changed(True)

    def toggle(self):
        if self._is_playing:
            self.pause()
        else:
            self.resume()

    def stop(self):
        self.player.set_state(Gst.State.NULL)
        self._is_playing = False
        if self.on_state_changed:
            self.on_state_changed(False)

    def is_playing(self):
        return self._is_playing

    def get_position_and_duration(self):
        """Returns (position_seconds, duration_seconds)."""
        try:
            success, pos = self.player.query_position(Gst.Format.TIME)
            success_d, dur = self.player.query_duration(Gst.Format.TIME)
            pos_sec = pos / Gst.SECOND if success and pos > 0 else 0
            dur_sec = dur / Gst.SECOND if success_d and dur > 0 else 0
            return pos_sec, dur_sec
        except Exception:
            return 0, 0

    def seek(self, seconds):
        try:
            self.player.seek_simple(
                Gst.Format.TIME,
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                int(seconds * Gst.SECOND)
            )
        except Exception as e:
            logger.error(f"Seek error: {e}")
