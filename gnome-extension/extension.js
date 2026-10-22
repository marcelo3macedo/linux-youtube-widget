/* extension.js
 * YouTube Music Widget & Controller for GNOME Shell (45+)
 */

import GObject from 'gi://GObject';
import St from 'gi://St';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Clutter from 'gi://Clutter';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import { Extension, gettext as _ } from 'resource:///org/gnome/shell/extensions/extension.js';

function getActiveMprisPlayers() {
    try {
        const bus = Gio.bus_get_sync(Gio.BusType.SESSION, null);
        const proxy = Gio.DBusProxy.new_sync(
            bus,
            Gio.DBusProxyFlags.NONE,
            null,
            'org.freedesktop.DBus',
            '/org/freedesktop/DBus',
            'org.freedesktop.DBus',
            null
        );
        const reply = proxy.call_sync('ListNames', null, Gio.DBusCallFlags.NONE, -1, null);
        const names = reply.recursiveUnpack()[0];
        const players = names.filter(n => n.startsWith('org.mpris.MediaPlayer2.'));
        
        // Prioritize youtube_widget first, then other media players
        players.sort((a, b) => {
            if (a.includes('youtube_widget')) return -1;
            if (b.includes('youtube_widget')) return 1;
            const aYt = a.toLowerCase().includes('music') || a.toLowerCase().includes('youtube') || a.toLowerCase().includes('chrome');
            const bYt = b.toLowerCase().includes('music') || b.toLowerCase().includes('youtube') || b.toLowerCase().includes('chrome');
            if (aYt && !bYt) return -1;
            if (!aYt && bYt) return 1;
            return 0;
        });
        return players;
    } catch (e) {
        return [];
    }
}

function sendMprisCommand(method) {
    const players = getActiveMprisPlayers();
    if (!players || players.length === 0) return;
    try {
        const bus = Gio.bus_get_sync(Gio.BusType.SESSION, null);
        for (const player of players) {
            const proxy = Gio.DBusProxy.new_sync(
                bus,
                Gio.DBusProxyFlags.NONE,
                null,
                player,
                '/org/mpris/MediaPlayer2',
                'org.mpris.MediaPlayer2.Player',
                null
            );
            proxy.call_sync(method, null, Gio.DBusCallFlags.NONE, -1, null);
            break;
        }
    } catch (e) {
        console.error(`[YouTubeMusic] Error sending ${method}:`, e);
    }
}

const YouTubeMusicIndicator = GObject.registerClass(
class YouTubeMusicIndicator extends PanelMenu.Button {
    _init(extension) {
        super._init(0.0, _('YouTube Music Widget'));
        this._extension = extension;
        this._timeoutId = null;

        // Panel Icon
        const icon = new St.Icon({
            icon_name: 'audio-x-generic-symbolic',
            style_class: 'system-status-icon yt-panel-icon',
        });
        this.add_child(icon);

        this._buildMenu();

        this.menu.connect('open-state-changed', (menu, open) => {
            if (open) {
                this._updateTrackInfo();
                if (!this._timeoutId) {
                    this._timeoutId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
                        this._updateTrackInfo();
                        return GLib.SOURCE_CONTINUE;
                    });
                }
            } else {
                if (this._timeoutId) {
                    GLib.Source.remove(this._timeoutId);
                    this._timeoutId = null;
                }
            }
        });
    }

    _buildMenu() {
        const section = new PopupMenu.PopupMenuSection();
        const mainContainer = new St.BoxLayout({
            vertical: true,
            style_class: 'yt-popup-box',
        });

        // 1. Header (Open Widget button)
        const headerBox = new St.BoxLayout({
            vertical: false,
            style: 'spacing: 8px;',
        });

        const openWidgetBtn = new St.Button({
            label: '🎵 Abrir YouTube Music Widget',
            style_class: 'yt-link-btn',
            x_expand: true,
        });
        openWidgetBtn.connect('clicked', () => {
            this.menu.close();
            GLib.spawn_command_line_async('youtube-widget');
        });
        headerBox.add_child(openWidgetBtn);

        mainContainer.add_child(headerBox);
        mainContainer.add_child(new PopupMenu.PopupSeparatorMenuItem());

        // 2. Search Section (Searches and plays 1st track directly)
        const searchBox = new St.BoxLayout({
            vertical: false,
            style: 'spacing: 6px;',
        });

        this._searchEntry = new St.Entry({
            hint_text: 'Buscar no YouTube Music...',
            style_class: 'yt-search-entry',
            can_focus: true,
            x_expand: true,
        });

        this._searchEntry.clutter_text.connect('activate', () => {
            this._doSearch();
        });
        searchBox.add_child(this._searchEntry);

        const searchBtn = new St.Button({
            style_class: 'button',
            child: new St.Icon({ icon_name: 'edit-find-symbolic' }),
        });
        searchBtn.connect('clicked', () => {
            this._doSearch();
        });
        searchBox.add_child(searchBtn);

        mainContainer.add_child(searchBox);
        mainContainer.add_child(new PopupMenu.PopupSeparatorMenuItem());

        // 3. Track Info
        this._titleLabel = new St.Label({
            text: 'YouTube Music',
            style_class: 'yt-track-title',
        });
        this._artistLabel = new St.Label({
            text: 'Pronto para reproduzir',
            style_class: 'yt-track-artist',
        });
        mainContainer.add_child(this._titleLabel);
        mainContainer.add_child(this._artistLabel);

        // 4. Media Controls (Previous, Play/Pause, Next)
        const controlsBox = new St.BoxLayout({
            vertical: false,
            style: 'spacing: 14px; margin-top: 6px; margin-bottom: 6px;',
            x_align: Clutter.ActorAlign.CENTER,
        });

        // Previous (Volta)
        const prevBtn = new St.Button({
            style_class: 'yt-media-btn',
            child: new St.Icon({ icon_name: 'media-skip-backward-symbolic' }),
        });
        prevBtn.connect('clicked', () => {
            sendMprisCommand('Previous');
            GLib.timeout_add(GLib.PRIORITY_DEFAULT, 300, () => {
                this._updateTrackInfo();
                return GLib.SOURCE_REMOVE;
            });
        });
        controlsBox.add_child(prevBtn);

        // Play / Pause
        this._playIcon = new St.Icon({ icon_name: 'media-playback-start-symbolic' });
        const playBtn = new St.Button({
            style_class: 'yt-play-btn',
            child: this._playIcon,
        });
        playBtn.connect('clicked', () => {
            sendMprisCommand('PlayPause');
            GLib.timeout_add(GLib.PRIORITY_DEFAULT, 300, () => {
                this._updateTrackInfo();
                return GLib.SOURCE_REMOVE;
            });
        });
        controlsBox.add_child(playBtn);

        // Next (Próxima)
        const nextBtn = new St.Button({
            style_class: 'yt-media-btn',
            child: new St.Icon({ icon_name: 'media-skip-forward-symbolic' }),
        });
        nextBtn.connect('clicked', () => {
            sendMprisCommand('Next');
            GLib.timeout_add(GLib.PRIORITY_DEFAULT, 300, () => {
                this._updateTrackInfo();
                return GLib.SOURCE_REMOVE;
            });
        });
        controlsBox.add_child(nextBtn);

        mainContainer.add_child(controlsBox);
        mainContainer.add_child(new PopupMenu.PopupSeparatorMenuItem());

        // 5. Volume Controls
        const volBox = new St.BoxLayout({
            vertical: false,
            style: 'spacing: 8px;',
            x_align: Clutter.ActorAlign.CENTER,
        });

        const volDownBtn = new St.Button({
            style_class: 'yt-vol-btn',
            child: new St.Icon({ icon_name: 'audio-volume-low-symbolic' }),
        });
        volDownBtn.connect('clicked', () => {
            GLib.spawn_command_line_async('wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%- || amixer -D pulse sset Master 5%-');
        });
        volBox.add_child(volDownBtn);

        const volMuteBtn = new St.Button({
            style_class: 'yt-vol-btn',
            label: 'Mudo',
        });
        volMuteBtn.connect('clicked', () => {
            GLib.spawn_command_line_async('wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle || amixer -D pulse sset Master toggle');
        });
        volBox.add_child(volMuteBtn);

        const volUpBtn = new St.Button({
            style_class: 'yt-vol-btn',
            child: new St.Icon({ icon_name: 'audio-volume-high-symbolic' }),
        });
        volUpBtn.connect('clicked', () => {
            GLib.spawn_command_line_async('wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+ || amixer -D pulse sset Master 5%+');
        });
        volBox.add_child(volUpBtn);

        mainContainer.add_child(volBox);

        section.actor.add_child(mainContainer);
        this.menu.addMenuItem(section);
    }

    _doSearch() {
        const text = this._searchEntry.get_text().trim();
        if (text) {
            this.menu.close();
            // Try sending search to running MPRIS player first
            let sent = false;
            try {
                const bus = Gio.bus_get_sync(Gio.BusType.SESSION, null);
                const proxy = Gio.DBusProxy.new_sync(
                    bus,
                    Gio.DBusProxyFlags.NONE,
                    null,
                    'org.mpris.MediaPlayer2.youtube_widget',
                    '/org/mpris/MediaPlayer2',
                    'org.mpris.MediaPlayer2.Player',
                    null
                );
                proxy.call_sync('Search', new GLib.Variant('(s)', [text]), Gio.DBusCallFlags.NONE, 2000, null);
                sent = true;
            } catch (e) {
                sent = false;
            }

            if (!sent) {
                // If not running, start the widget with the search query
                GLib.spawn_command_line_async(`youtube-widget "${text.replace(/"/g, '\\"')}"`);
            }

            this._searchEntry.set_text('');
        }
    }

    _updateTrackInfo() {
        const players = getActiveMprisPlayers();
        if (!players || players.length === 0) {
            this._titleLabel.set_text('YouTube Music');
            this._artistLabel.set_text('Pronto para reproduzir');
            this._playIcon.set_icon_name('media-playback-start-symbolic');
            return;
        }

        try {
            const bus = Gio.bus_get_sync(Gio.BusType.SESSION, null);
            const props = Gio.DBusProxy.new_sync(
                bus,
                Gio.DBusProxyFlags.NONE,
                null,
                players[0],
                '/org/mpris/MediaPlayer2',
                'org.freedesktop.DBus.Properties',
                null
            );

            // Read Status
            try {
                const statusVal = props.call_sync(
                    'Get',
                    new GLib.Variant('(ss)', ['org.mpris.MediaPlayer2.Player', 'PlaybackStatus']),
                    Gio.DBusCallFlags.NONE,
                    -1,
                    null
                );
                const status = statusVal.recursiveUnpack()[0];
                if (status === 'Playing') {
                    this._playIcon.set_icon_name('media-playback-pause-symbolic');
                } else {
                    this._playIcon.set_icon_name('media-playback-start-symbolic');
                }
            } catch (e) {
                this._playIcon.set_icon_name('media-playback-start-symbolic');
            }

            // Read Metadata
            const metaVal = props.call_sync(
                'Get',
                new GLib.Variant('(ss)', ['org.mpris.MediaPlayer2.Player', 'Metadata']),
                Gio.DBusCallFlags.NONE,
                -1,
                null
            );
            const meta = metaVal.recursiveUnpack()[0];
            const title = meta['xesam:title'] || 'YouTube Music';
            let artist = meta['xesam:artist'];
            if (Array.isArray(artist)) artist = artist.join(', ');

            this._titleLabel.set_text(String(title));
            this._artistLabel.set_text(artist ? String(artist) : 'Reproduzindo');
        } catch (e) {
            this._titleLabel.set_text('YouTube Music');
            this._artistLabel.set_text('Pronto para reproduzir');
            this._playIcon.set_icon_name('media-playback-start-symbolic');
        }
    }

    destroy() {
        if (this._timeoutId) {
            GLib.Source.remove(this._timeoutId);
            this._timeoutId = null;
        }
        super.destroy();
    }
});

export default class YouTubeMusicWidgetExtension extends Extension {
    enable() {
        this._indicator = new YouTubeMusicIndicator(this);
        Main.panel.addToStatusArea(this.uuid, this._indicator);
    }

    disable() {
        if (this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }
    }
}
