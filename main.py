#!/usr/bin/env python3
"""Consent-based live text pilot. Does not start capture until explicit user action."""
import fcntl
import json
import os
import signal
import threading
import time
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib
from text_app import App
from core import Pilot, Cancelled
from settings import STATE_DIR as ROOT, CODE_DIR, write_private
from frames import FrameGate, frame_quality
from portal import PortalCapture
from region import RegionPicker


class LiveApp(App):
    def __init__(self):
        super().__init__()
        self.capture = None
        self.picker = None
        self.roi = None
        self.frame_size = None
        self.gate = FrameGate()
        self.pending_frame = None
        self.live_worker = False
        self.active_generation = None
        self.frame_queued = False
        self.latest_frame = None
        self.epoch = 0

    def do_activate(self):
        super().do_activate()
        self.window.set_title('Tradutor de Jogos — Tradução de texto')
        box = self.window.get_child()
        box.get_first_child().set_text('Compartilhe somente a janela do jogo pelo GNOME. Depois marque a área do texto; as mudanças serão lidas localmente, sem voz.')
        self.open_button.set_label('Imagem salva (diagnóstico)…')
        row = Gtk.Box(spacing=8)
        self.share_button = Gtk.Button(label='Compartilhar janela do jogo…')
        self.share_button.connect('clicked', self.share)
        self.stop_button = Gtk.Button(label='Parar compartilhamento')
        self.stop_button.set_sensitive(False)
        self.stop_button.connect('clicked', lambda _: self.stop_live())
        row.append(self.share_button)
        row.append(self.stop_button)
        box.prepend(row)
        self.status.set_text('Pronto. Compartilhar abrirá o consentimento nativo do GNOME; nenhuma captura começou.')

    def share(self, _):
        if self.worker or self.capture:
            return
        self.epoch += 1
        epoch = self.epoch
        self.share_button.set_sensitive(False)
        self.open_button.set_sensitive(False)
        self.stop_button.set_sensitive(True)
        self.names.set_sensitive(False)
        self.roi = None
        self.gate = FrameGate()
        try:
            self.capture = PortalCapture(lambda frame: self.offer_frame(epoch, frame), self.set_status,
                        lambda message: self.capture_error(epoch, message))
            self.capture.start()
        except Exception as exc:
            self.capture_error(epoch, str(exc))

    def offer_frame(self, epoch, frame):
        # At most one frame waits for the GTK thread. Never accumulate a video queue.
        self.latest_frame = epoch, frame
        if not self.frame_queued:
            self.frame_queued = True
            GLib.idle_add(self.drain_frame)

    def drain_frame(self):
        self.frame_queued = False
        current, self.latest_frame = self.latest_frame, None
        if not current:
            return False
        epoch, frame = current
        if epoch != self.epoch or not self.capture:
            return False
        if self.roi is None:
            if self.picker is None:
                self.picker = RegionPicker(self.window, frame, self.region_chosen, self.stop_live)
                self.picker.present()
            else:
                self.picker.update_image(frame)
            return False
        if frame.size != self.frame_size:
            self.stop_live('O tamanho da janela mudou. Compartilhe novamente e marque a área do texto.')
            return False
        crop = frame.crop(self.roi)
        quality = frame_quality(crop)
        if quality['black'] or quality['uniform']:
            self.original.set_text('')
            self.translated.set_text('')
            self.pending_frame = None
            self.gate = FrameGate()
            if self.pilot and self.worker:
                self.pilot.cancel()
            self.status.set_text('Área preta ou sem conteúdo: OCR suspenso. Aguardando texto visível.')
            return False
        previous = self.gate.generation
        accepted = self.gate.offer(crop)
        if self.gate.generation != previous:
            self.status.set_text('A imagem mudou; verificando o texto. A última tradução continua identificada pela leitura original.')
            self.pending_frame = None
        if accepted:
            self.pending_frame = accepted
        if self.pending_frame and not self.worker:
            self.start_latest()
        return False

    def region_chosen(self, roi, size):
        self.roi, self.frame_size, self.picker = roi, size, None
        self.capture.record('region_confirmed_by_user', {'region': list(roi), 'frame_size': list(size)})
        self.status.set_text('Área selecionada. Lendo mudanças a até 2 quadros por segundo…')

    def start_latest(self):
        generation, frame = self.pending_frame
        self.pending_frame = None
        self.active_generation = self.epoch, generation
        self.live_worker = True
        self.pilot = Pilot()
        self.cancel_button.set_sensitive(True)
        names = [s.strip() for s in self.names.get_text().split(';') if s.strip()]
        self.status.set_text('Reconhecendo e traduzindo a área escolhida…')
        def work():
            try:
                result = self.pilot.run(frame, names)
                GLib.idle_add(self.done, result, None)
            except Exception as exc:
                GLib.idle_add(self.done, None, str(exc))
        self.worker = threading.Thread(target=work, name='eve-live-text-worker', daemon=False)
        self.worker.start()

    def done(self, result, error):
        if not self.live_worker:
            return super().done(result, error)
        self.live_worker = False
        self.worker = None
        self.cancel_button.set_sensitive(False)
        if self.closing:
            self.window.destroy()
            self.quit()
            return False
        # Animated backgrounds must not discard a completed translation. Show its
        # exact source beside it and identify it as the latest completed reading.
        valid = self.capture and self.active_generation[0] == self.epoch
        if valid:
            if error:
                self.status.set_text(error + ' Aguardando próxima mudança de texto.')
            else:
                self.original.set_text(result['input'])
                self.translated.set_text(result['translation'])
                self.status.set_text(f"Última leitura concluída em {result['total_seconds']:.2f} s; compare com o original à esquerda. Pode haver atraso.")
                write_private(ROOT / 'ultimo-texto-ao-vivo.json', result)
        if self.pending_frame and self.capture:
            self.start_latest()
        if not self.capture:
            self.share_button.set_sensitive(True)
            self.open_button.set_sensitive(True)
            self.names.set_sensitive(True)
        return False

    def cancel(self, _=None):
        if self.capture:
            self.stop_live()
        else:
            super().cancel(_)

    def capture_error(self, epoch, message):
        if epoch == self.epoch:
            self.stop_live(message)

    def stop_live(self, message='Compartilhamento parado. Nenhuma captura ativa.'):
        self.epoch += 1
        if self.capture:
            self.capture.stop()
            self.capture = None
        if self.picker:
            self.picker.finished = True
            self.picker.destroy()
            self.picker = None
        self.roi = self.latest_frame = self.pending_frame = None
        if self.pilot and self.worker:
            self.pilot.cancel()
        self.stop_button.set_sensitive(False)
        self.share_button.set_sensitive(not bool(self.worker))
        self.open_button.set_sensitive(not bool(self.worker))
        self.names.set_sensitive(not bool(self.worker))
        self.status.set_text(message)

    def close_requested(self, window):
        if self.capture:
            self.stop_live('Encerrando compartilhamento e liberando o modelo…')
        return super().close_requested(window)


if __name__ == '__main__':
    lock = open(ROOT / '.tradutor.lock', 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        # A second launcher activation presents the result viewer, never a second capture.
        os.execve('/usr/bin/python3', ['/usr/bin/python3', str(CODE_DIR / 'viewer.py')],
                  {**os.environ, 'GSK_RENDERER': 'cairo'})
    (ROOT / '.tradutor.pid').write_text(str(os.getpid()))
    app = LiveApp()
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, app.request_exit)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, app.request_exit)
    try:
        app.run([])
    finally:
        (ROOT / '.tradutor.pid').unlink(missing_ok=True)
