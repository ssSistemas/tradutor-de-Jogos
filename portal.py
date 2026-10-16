"""Only the native consent-based ScreenCast portal; no fallback capture API."""
import os
import secrets
import json
from pathlib import Path
from collections import deque
from settings import STATE_DIR, write_private
import time
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstVideo', '1.0')
from gi.repository import Gio, GLib, Gst, GstVideo
from PIL import Image
from frames import frame_quality

DEST = 'org.freedesktop.portal.Desktop'
PATH = '/org/freedesktop/portal/desktop'
IFACE = 'org.freedesktop.portal.ScreenCast'


class PortalCapture:
    def __init__(self, on_frame, on_status, on_error):
        self.on_frame, self.on_status, self.on_error = on_frame, on_status, on_error
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.session = None
        self.request = None
        self.subscription = None
        self.session_subscription = None
        self.pipeline = None
        self.remote_fd = None
        self.closed = False
        self.generation = 0
        self.events = deque(maxlen=128)
        self.first_frame = False
        self.frame_count = 0
        self.last_quality_state = None
        self.last_quality_report = 0
        self.last_sample = 0

    def record(self, event, details=None):
        self.events.append({'event': event, 'time_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                            'details': details or {}})
        write_private(STATE_DIR / 'captura-consentimento.json', list(self.events))

    def start(self):
        # Called ONLY by the user's own button, never at application startup.
        self._request('CreateSession', lambda options: GLib.Variant('(a{sv})', (options,)),
                      {'session_handle_token': GLib.Variant('s', 'eve' + secrets.token_hex(12))},
                      self._created)

    def _request(self, method, parameters, options, success):
        if self.closed:
            return
        token = 'evetext' + secrets.token_hex(12)
        options['handle_token'] = GLib.Variant('s', token)
        sender = self.bus.get_unique_name().lstrip(':').replace('.', '_')
        predicted = f'{PATH}/request/{sender}/{token}'
        self.request = predicted
        def response(conn, sender, path, interface, signal, params, data):
            if self.closed:
                return
            self.bus.signal_unsubscribe(self.subscription)
            self.subscription = None
            self.request = None
            code, results = params.unpack()
            self.record(method + '_response', {'response': code})
            if code != 0:
                self.fail('Compartilhamento cancelado ou recusado pelo GNOME. A captura não será repetida automaticamente.')
                return
            try:
                success(results)
            except Exception as exc:
                self.fail(str(exc))
        self.subscription = self.bus.signal_subscribe(DEST, 'org.freedesktop.portal.Request',
                'Response', predicted, None, Gio.DBusSignalFlags.NONE, response, None)
        def returned(conn, result, data):
            if self.closed:
                return
            try:
                actual = conn.call_finish(result).unpack()[0]
                if actual != predicted:
                    # Modern portal v5 promises predictable handles. Fail rather than retry.
                    self.fail('O portal devolveu um identificador inesperado. Sessão encerrada, sem captura.')
            except Exception as exc:
                self.fail(str(exc))
        self.bus.call(DEST, PATH, IFACE, method, parameters(options), GLib.VariantType('(o)'),
                      Gio.DBusCallFlags.NONE, 10000, None, returned, None)

    def _created(self, results):
        self.session = results['session_handle']
        self.session_subscription = self.bus.signal_subscribe(DEST, 'org.freedesktop.portal.Session',
            'Closed', self.session, None, Gio.DBusSignalFlags.NONE,
            lambda *args: self.fail('O compartilhamento foi encerrado pelo GNOME.'), None)
        options = {'types': GLib.Variant('u', 2), 'multiple': GLib.Variant('b', False),
                   'cursor_mode': GLib.Variant('u', 1), 'persist_mode': GLib.Variant('u', 0)}
        self._request('SelectSources', lambda opts: GLib.Variant('(oa{sv})', (self.session, opts)),
                      options, self._selected)

    def _selected(self, results):
        self.on_status('No GNOME, selecione somente a janela do jogo e clique em Compartilhar. Cancelar será respeitado.')
        self._request('Start', lambda opts: GLib.Variant('(osa{sv})', (self.session, '', opts)),
                      {}, self._started)

    def _started(self, results):
        streams = results.get('streams', [])
        if len(streams) != 1 or streams[0][1].get('source_type') != 2:
            raise RuntimeError('O portal não confirmou uma única janela. Captura recusada; não usarei monitor inteiro.')
        node_id = int(streams[0][0])
        self.record('window_stream_granted', {'source_type': 2, 'stream_count': 1,
                    'persist_mode': 0, 'audio_requested': False})
        reply, descriptors = self.bus.call_with_unix_fd_list_sync(DEST, PATH, IFACE,
            'OpenPipeWireRemote', GLib.Variant('(oa{sv})', (self.session, {})),
            GLib.VariantType('(h)'), Gio.DBusCallFlags.NONE, 10000, None, None)
        self.remote_fd = descriptors.get(reply.unpack()[0])
        self._start_pipewire(node_id)

    def _start_pipewire(self, node_id):
        Gst.init(None)
        # The FD is restricted by the portal to streams explicitly shared by the user.
        self.pipeline = Gst.parse_launch(
            f'pipewiresrc fd={self.remote_fd} path={node_id} do-timestamp=true ! '
            'videorate drop-only=true ! video/x-raw,framerate=2/1 ! videoconvert ! video/x-raw,format=RGB ! '
            'appsink name=frames emit-signals=true max-buffers=1 drop=true sync=false')
        sink = self.pipeline.get_by_name('frames')
        sink.connect('new-sample', self._sample)
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message', self._message)
        if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError('Não foi possível receber vídeo da janela compartilhada.')
        self.on_status('Janela compartilhada. Aguardando a primeira imagem para escolher a área do texto…')

    @staticmethod
    def sample_image(sample):
        info = GstVideo.VideoInfo.new_from_caps(sample.get_caps())
        if info.width * info.height > 24_000_000:
            raise ValueError('Janela maior que o limite de 24 milhões de pixels.')
        buffer = sample.get_buffer()
        ok, mapped = buffer.map(Gst.MapFlags.READ)
        if not ok:
            raise RuntimeError('Não foi possível ler o quadro de vídeo.')
        try:
            image = Image.frombytes('RGB', (info.width, info.height), bytes(mapped.data),
                                    'raw', 'RGB', info.stride[0], 1)
            return image
        finally:
            buffer.unmap(mapped)

    def _sample(self, sink):
        sample = sink.emit('pull-sample')
        if self.closed or sample is None:
            return Gst.FlowReturn.FLUSHING
        now = time.monotonic()
        if now - self.last_sample < 0.5:
            return Gst.FlowReturn.OK
        self.last_sample = now
        try:
            image = self.sample_image(sample)
            self.frame_count += 1
            quality = frame_quality(image)
            state = quality['black'], quality['uniform']
            if state != self.last_quality_state or time.monotonic() - self.last_quality_report > 10:
                self.last_quality_state = state
                self.last_quality_report = time.monotonic()
                GLib.idle_add(self.record, 'video_quality', {'frames_received': self.frame_count,
                              'size': list(image.size), **quality})
            if not self.first_frame:
                self.first_frame = True
                GLib.idle_add(self.record, 'first_video_frame', {'size': list(image.size)})
            self.on_frame(image)
            return Gst.FlowReturn.OK
        except Exception as exc:
            GLib.idle_add(self.fail, str(exc))
            return Gst.FlowReturn.ERROR

    def _message(self, bus, message):
        if message.type == Gst.MessageType.ERROR:
            error, debug = message.parse_error()
            self.fail('Erro no vídeo compartilhado: ' + str(error))
        elif message.type == Gst.MessageType.EOS:
            self.fail('A janela deixou de fornecer imagens. Compartilhamento encerrado.')

    def fail(self, message):
        if not self.closed:
            self.stop()
            self.on_error(message)
        return False

    def stop(self):
        if self.closed:
            return
        self.closed = True
        if self.pipeline:
            bus = self.pipeline.get_bus()
            bus.remove_signal_watch()
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
        if self.remote_fd is not None:
            try:
                os.close(self.remote_fd)
            except OSError:
                pass
            self.remote_fd = None
        if self.subscription:
            self.bus.signal_unsubscribe(self.subscription)
            self.subscription = None
        if self.session_subscription:
            self.bus.signal_unsubscribe(self.session_subscription)
            self.session_subscription = None
        for path, interface in [(self.request, 'org.freedesktop.portal.Request'),
                                (self.session, 'org.freedesktop.portal.Session')]:
            if path:
                self.bus.call(DEST, path, interface, 'Close', None, None,
                              Gio.DBusCallFlags.NONE, 5000, None, None, None)
        self.request = self.session = None
        self.record('stopped')
