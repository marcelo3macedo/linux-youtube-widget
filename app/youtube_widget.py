#!/usr/bin/env python3
"""
YouTube Music Dedicated Linux Widget
Features:
- 100% focused on YouTube Music
- Inline search (shows results right inside the widget, no extra windows)
- Automatically selects and plays the first result
- Native audio playback via GStreamer (PipeWire/PulseAudio)
- Next (próxima) and Previous (volta) track navigation
- Auto-advances to the next song when current one finishes (EOS)
- Song progress indicator and time display
- Real-time PipeWire / PulseAudio system volume slider
"""

import os
import sys

# Ensure local modules can always be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import threading
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

from ytmusic_api import search_youtube_music
from audio_player import AudioPlayer
from mpris_controller import VolumeController
from mpris_server import MPRISService


def format_time(seconds):
    seconds = int(max(0, seconds))
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"


class YouTubeMusicWidget(Gtk.Window):
    def __init__(self):
        super().__init__(title="YouTube Music")

        self.set_default_size(380, 580)
        self.set_position(Gtk.WindowPosition.CENTER)

        # Force dark theme for YouTube Music aesthetic
        gtk_settings = Gtk.Settings.get_default()
        if gtk_settings:
            gtk_settings.set_property("gtk-application-prefer-dark-theme", True)

        self.vol_ctrl = VolumeController()
        self.results = []
        self.current_index = -1
        self._updating_volume = False

        # Initialize native audio player
        self.player = AudioPlayer(
            on_eos=self._on_track_finished,
            on_error=self._on_player_error,
            on_state_changed=self._on_player_state_changed
        )

        # Register MPRIS D-Bus interface for GNOME top bar & media keys integration
        self.mpris_service = MPRISService(self)

        self._load_css()
        self._setup_ui()
        self._init_volume()

        # Timer for progress bar updates
        GLib.timeout_add(500, self._update_progress)

        # Handle command-line query if provided
        if len(sys.argv) > 1:
            initial_query = " ".join(sys.argv[1:])
            self.search_entry.set_text(initial_query)
            self._start_search(initial_query)

    def _load_css(self):
        css_file = os.path.join(os.path.dirname(__file__), "style.css")
        if os.path.exists(css_file):
            try:
                provider = Gtk.CssProvider()
                provider.load_from_path(css_file)
                screen = Gdk.Screen.get_default()
                if screen:
                    Gtk.StyleContext.add_provider_for_screen(
                        screen,
                        provider,
                        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                    )
            except Exception as e:
                print(f"[Aviso CSS] {e}", file=sys.stderr)

    def _setup_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_top(12)
        main_box.set_margin_bottom(12)
        main_box.set_margin_start(14)
        main_box.set_margin_end(14)
        self.add(main_box)

        # 1. Header (Logo + Title + Pin Toggle)
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header_box.get_style_context().add_class("ytm-header")

        logo_lbl = Gtk.Label(label="🎵")
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        title_lbl = Gtk.Label(label="YouTube Music")
        title_lbl.get_style_context().add_class("ytm-title")
        title_lbl.set_halign(Gtk.Align.START)

        sub_lbl = Gtk.Label(label="Mini Player & Search")
        sub_lbl.get_style_context().add_class("ytm-subtitle")
        sub_lbl.set_halign(Gtk.Align.START)

        title_box.pack_start(title_lbl, False, False, 0)
        title_box.pack_start(sub_lbl, False, False, 0)

        header_box.pack_start(logo_lbl, False, False, 0)
        header_box.pack_start(title_box, False, False, 0)

        # Spacer
        spacer = Gtk.Box()
        header_box.pack_start(spacer, True, True, 0)

        # Pin / Always on top toggle
        self.pin_btn = Gtk.ToggleButton(label="📌")
        self.pin_btn.set_tooltip_text("Fixar no topo da tela")
        self.pin_btn.connect("toggled", lambda b: self.set_keep_above(b.get_active()))
        header_box.pack_end(self.pin_btn, False, False, 0)

        main_box.pack_start(header_box, False, False, 0)

        # 2. Search Bar
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        search_box.get_style_context().add_class("search-box")

        self.search_entry = Gtk.Entry()
        self.search_entry.get_style_context().add_class("search-entry")
        self.search_entry.set_placeholder_text("Pesquisar no YouTube Music...")
        self.search_entry.connect("activate", self._on_search_activated)
        search_box.pack_start(self.search_entry, True, True, 0)

        search_btn = Gtk.Button(label="🔍")
        search_btn.get_style_context().add_class("btn-search")
        search_btn.set_tooltip_text("Pesquisar e tocar primeiro resultado")
        search_btn.connect("clicked", self._on_search_activated)
        search_box.pack_end(search_btn, False, False, 0)

        main_box.pack_start(search_box, False, False, 0)

        # 3. Now Playing Card
        self.player_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.player_card.get_style_context().add_class("player-card")

        # Track info
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.now_title_lbl = Gtk.Label(label="Pronto para tocar")
        self.now_title_lbl.get_style_context().add_class("now-playing-title")
        self.now_title_lbl.set_halign(Gtk.Align.CENTER)
        self.now_title_lbl.set_ellipsize(3)

        self.now_artist_lbl = Gtk.Label(label="Pesquise uma música acima")
        self.now_artist_lbl.get_style_context().add_class("now-playing-artist")
        self.now_artist_lbl.set_halign(Gtk.Align.CENTER)
        self.now_artist_lbl.set_ellipsize(3)

        self.status_lbl = Gtk.Label(label="")
        self.status_lbl.set_halign(Gtk.Align.CENTER)
        self.status_lbl.get_style_context().add_class("ytm-subtitle")

        info_box.pack_start(self.now_title_lbl, False, False, 0)
        info_box.pack_start(self.now_artist_lbl, False, False, 0)
        info_box.pack_start(self.status_lbl, False, False, 0)
        self.player_card.pack_start(info_box, False, False, 0)

        # Progress bar & Time label
        progress_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_hexpand(True)
        self.progress_bar.set_fraction(0.0)
        progress_box.pack_start(self.progress_bar, True, True, 0)

        self.time_lbl = Gtk.Label(label="00:00 / 00:00")
        self.time_lbl.get_style_context().add_class("ytm-subtitle")
        progress_box.pack_end(self.time_lbl, False, False, 0)
        self.player_card.pack_start(progress_box, False, False, 0)

        # Playback Controls (Previous, Play/Pause, Next)
        controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        controls_box.set_halign(Gtk.Align.CENTER)

        # Previous (Voltar)
        self.prev_btn = Gtk.Button(label="⏮")
        self.prev_btn.get_style_context().add_class("control-btn")
        self.prev_btn.set_tooltip_text("Voltar / Música Anterior")
        self.prev_btn.connect("clicked", lambda _: self.play_previous())
        controls_box.pack_start(self.prev_btn, False, False, 0)

        # Play / Pause
        self.play_btn = Gtk.Button(label="▶")
        self.play_btn.get_style_context().add_class("play-main-btn")
        self.play_btn.set_tooltip_text("Play / Pause")
        self.play_btn.connect("clicked", lambda _: self.player.toggle())
        controls_box.pack_start(self.play_btn, False, False, 0)

        # Next (Próxima)
        self.next_btn = Gtk.Button(label="⏭")
        self.next_btn.get_style_context().add_class("control-btn")
        self.next_btn.set_tooltip_text("Avançar / Próxima Música")
        self.next_btn.connect("clicked", lambda _: self.play_next())
        controls_box.pack_start(self.next_btn, False, False, 0)

        self.player_card.pack_start(controls_box, False, False, 0)
        main_box.pack_start(self.player_card, False, False, 0)

        # 4. Volume Control
        vol_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        vol_box.get_style_context().add_class("vol-container")

        self.mute_btn = Gtk.Button(label="🔊")
        self.mute_btn.set_relief(Gtk.ReliefStyle.NONE)
        self.mute_btn.set_tooltip_text("Mudo / Desmudo")
        self.mute_btn.connect("clicked", self._on_toggle_mute)
        vol_box.pack_start(self.mute_btn, False, False, 0)

        self.vol_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.vol_scale.set_draw_value(False)
        self.vol_scale.connect("value-changed", self._on_volume_changed)
        vol_box.pack_start(self.vol_scale, True, True, 0)

        self.vol_lbl = Gtk.Label(label="50%")
        self.vol_lbl.set_width_chars(5)
        vol_box.pack_end(self.vol_lbl, False, False, 0)

        main_box.pack_start(vol_box, False, False, 0)

        # 5. Search Results Area ("Mostrar ali mesmo")
        results_header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.results_title_lbl = Gtk.Label(label="Músicas Encontradas")
        self.results_title_lbl.get_style_context().add_class("results-header")
        self.results_title_lbl.set_halign(Gtk.Align.START)
        results_header_box.pack_start(self.results_title_lbl, True, True, 0)

        self.spinner = Gtk.Spinner()
        results_header_box.pack_end(self.spinner, False, False, 0)
        main_box.pack_start(results_header_box, False, False, 0)

        # Scrolled Results List
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.get_style_context().add_class("results-scroll")
        scrolled.set_vexpand(True)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.connect("row-activated", self._on_row_activated)
        scrolled.add(self.listbox)

        main_box.pack_start(scrolled, True, True, 0)

    def _init_volume(self):
        vol_float, muted = self.vol_ctrl.get_volume()
        self._updating_volume = True
        pct = int(vol_float * 100)
        self.vol_scale.set_value(pct)
        self.vol_lbl.set_text(f"{pct}%")
        self.mute_btn.set_label("🔇" if muted else ("🔈" if pct < 33 else ("🔉" if pct < 66 else "🔊")))
        self._updating_volume = False

    def _on_volume_changed(self, scale):
        if self._updating_volume:
            return
        val = scale.get_value()
        self.vol_ctrl.set_volume(val / 100.0)
        pct = int(val)
        self.vol_lbl.set_text(f"{pct}%")
        self.mute_btn.set_label("🔈" if pct < 33 else ("🔉" if pct < 66 else "🔊"))

    def _on_toggle_mute(self, btn):
        self.vol_ctrl.toggle_mute()
        self._init_volume()

    def _on_search_activated(self, widget):
        query = self.search_entry.get_text().strip()
        if query:
            self._start_search(query)

    def _start_search(self, query):
        self.spinner.start()
        self.results_title_lbl.set_text(f"Buscando: {query}...")

        def run_query():
            songs = search_youtube_music(query, limit=12)
            GLib.idle_add(self._on_search_finished, songs, query)

        threading.Thread(target=run_query, daemon=True).start()

    def _on_search_finished(self, songs, query):
        self.spinner.stop()
        self.results = songs

        # Clear existing list
        for child in self.listbox.get_children():
            self.listbox.remove(child)

        if not songs:
            self.results_title_lbl.set_text("Nenhuma música encontrada")
            row = Gtk.ListBoxRow()
            lbl = Gtk.Label(label="Tente pesquisar com outros termos.")
            lbl.set_margin_top(14)
            lbl.set_margin_bottom(14)
            row.add(lbl)
            self.listbox.add(row)
            self.listbox.show_all()
            return

        self.results_title_lbl.set_text(f"{len(songs)} Músicas Encontradas")

        for idx, song in enumerate(songs):
            row = Gtk.ListBoxRow()
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row_box.get_style_context().add_class("song-row")

            num_lbl = Gtk.Label(label=f"{idx + 1}")
            num_lbl.set_width_chars(2)
            num_lbl.set_halign(Gtk.Align.CENTER)
            row_box.pack_start(num_lbl, False, False, 0)

            text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            t_lbl = Gtk.Label(label=song["title"])
            t_lbl.get_style_context().add_class("song-title")
            t_lbl.set_halign(Gtk.Align.START)
            t_lbl.set_ellipsize(3)

            a_lbl = Gtk.Label(label=song["artist"])
            a_lbl.get_style_context().add_class("song-artist")
            a_lbl.set_halign(Gtk.Align.START)
            a_lbl.set_ellipsize(3)

            text_box.pack_start(t_lbl, False, False, 0)
            text_box.pack_start(a_lbl, False, False, 0)
            row_box.pack_start(text_box, True, True, 0)

            play_icon_lbl = Gtk.Label(label="▶")
            play_icon_lbl.set_halign(Gtk.Align.END)
            row_box.pack_end(play_icon_lbl, False, False, 0)

            row.add(row_box)
            self.listbox.add(row)

        self.listbox.show_all()

        # Selecionar e tocar automaticamente o PRIMEIRO resultado!
        if songs:
            self.select_and_play(0)

    def _on_row_activated(self, listbox, row):
        idx = row.get_index()
        if 0 <= idx < len(self.results):
            self.select_and_play(idx)

    def select_and_play(self, index):
        if not self.results or index < 0 or index >= len(self.results):
            return

        self.current_index = index
        song = self.results[index]

        # Update highlighted row
        row = self.listbox.get_row_at_index(index)
        if row:
            self.listbox.select_row(row)

        # Update Now Playing labels
        self.now_title_lbl.set_text(song["title"])
        self.now_artist_lbl.set_text(song["artist"])
        self.status_lbl.set_text("Carregando áudio...")
        self.progress_bar.set_fraction(0.0)
        self.time_lbl.set_text("00:00 / 00:00")

        # Play native audio through GStreamer
        self.player.play(
            song["videoId"],
            title=song["title"],
            on_loading=self._on_loading_audio
        )

    def _on_loading_audio(self, is_loading):
        if is_loading:
            self.status_lbl.set_text("Conectando ao áudio...")
        else:
            self.status_lbl.set_text("")

    def _on_player_state_changed(self, is_playing):
        if is_playing:
            self.play_btn.set_label("⏸")
            self.status_lbl.set_text("▶ Reproduzindo")
        else:
            self.play_btn.set_label("▶")
            self.status_lbl.set_text("⏸ Pausado")

    def _on_track_finished(self):
        # Auto-advance to next track when song finishes!
        GLib.idle_add(self.play_next)

    def _on_player_error(self, error_msg):
        self.status_lbl.set_text(f"Erro: {error_msg}")
        self.play_btn.set_label("▶")

    def _update_progress(self):
        if self.player.is_playing():
            pos, dur = self.player.get_position_and_duration()
            if dur > 0:
                fraction = min(1.0, max(0.0, pos / dur))
                self.progress_bar.set_fraction(fraction)
                self.time_lbl.set_text(f"{format_time(pos)} / {format_time(dur)}")
        return True

    def play_next(self):
        if not self.results:
            return
        next_idx = (self.current_index + 1) % len(self.results)
        self.select_and_play(next_idx)

    def play_previous(self):
        if not self.results:
            return
        prev_idx = (self.current_index - 1) % len(self.results)
        self.select_and_play(prev_idx)

    def do_destroy(self):
        self.player.stop()
        Gtk.main_quit()


def main():
    Gtk.init(sys.argv)
    win = YouTubeMusicWidget()
    win.connect("destroy", lambda w: win.do_destroy())
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
