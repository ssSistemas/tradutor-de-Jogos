#!/usr/bin/env python3
"""Importação manual de imagens; sem captura de tela, microfone ou voz."""
import fcntl
import json
import os
from pathlib import Path
import signal
import threading
import time
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gio
from core import Pilot, Cancelled, DEFAULT_NAMES
from settings import STATE_DIR as ROOT, write_private


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='local.tradutordejogos.ptbr.texto', flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.worker = None
        self.pilot = None
        self.closing = False
        self.chooser = None

    def do_activate(self):
        self.window = Gtk.ApplicationWindow(application=self, title='Tradutor de Jogos — Texto em português')
        self.window.set_default_size(1100, 720)
        self.window.connect('close-request', self.close_requested)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for method in ['set_margin_top', 'set_margin_bottom', 'set_margin_start', 'set_margin_end']:
            getattr(box, method)(12)
        self.window.set_child(box)
        description = Gtk.Label(label='Salve manualmente um recorte do texto do jogo e escolha a imagem aqui. Sem captura automática e sem voz.', wrap=True, xalign=0)
        box.append(description)
        row = Gtk.Box(spacing=8)
        self.open_button = Gtk.Button(label='Abrir recorte…')
        self.open_button.connect('clicked', self.choose)
        self.cancel_button = Gtk.Button(label='Cancelar')
        self.cancel_button.set_sensitive(False)
        self.cancel_button.connect('clicked', self.cancel)
        exit_button = Gtk.Button(label='Sair')
        exit_button.connect('clicked', lambda _: self.window.close())
        row.append(self.open_button)
        row.append(self.cancel_button)
        row.append(exit_button)
        box.append(row)
        names_row = Gtk.Box(spacing=8)
        names_row.append(Gtk.Label(label='Nomes a preservar:'))
        self.names = Gtk.Entry(text='; '.join(DEFAULT_NAMES), hexpand=True)
        names_row.append(self.names)
        box.append(names_row)
        self.status = Gtk.Label(label='Pronto. Escolha um recorte salvo. A tradução é automática e pode conter erros.', wrap=True, xalign=0)
        box.append(self.status)
        panes = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True)
        panes.set_position(500)
        self.original = self.text_panel(panes, True, 'Texto reconhecido — confira se o OCR leu corretamente')
        self.translated = self.text_panel(panes, False, 'Português brasileiro — TranslateGemma 4B local')
        box.append(panes)
        box.append(Gtk.Label(label='Nomes e termos usam glossário local explícito. Repetições usam cache. O modelo é liberado após cada tradução.', wrap=True, xalign=0))
        self.window.present()

    def text_panel(self, panes, first, label):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.append(Gtk.Label(label=label, xalign=0, wrap=True))
        text = Gtk.TextView(editable=False, cursor_visible=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        text.set_left_margin(10)
        text.set_right_margin(10)
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroll.set_child(text)
        box.append(scroll)
        (panes.set_start_child if first else panes.set_end_child)(box)
        return text.get_buffer()

    def choose(self, _):
        if self.worker:
            return
        self.chooser = Gtk.FileChooserNative.new('Escolha um recorte salvo', self.window,
                                                Gtk.FileChooserAction.OPEN, 'Traduzir', 'Cancelar')
        f = Gtk.FileFilter()
        f.set_name('Imagens PNG, JPEG e WebP')
        for mime in ['image/png', 'image/jpeg', 'image/webp']:
            f.add_mime_type(mime)
        self.chooser.add_filter(f)
        self.chooser.connect('response', self.chosen)
        self.chooser.show()

    def chosen(self, chooser, response):
        path = chooser.get_file().get_path() if response == Gtk.ResponseType.ACCEPT and chooser.get_file() else None
        chooser.destroy()
        self.chooser = None
        if path:
            self.start(path)
        else:
            self.status.set_text('Seleção cancelada. Nenhuma imagem foi lida.')

    def start(self, path):
        self.original.set_text('')
        self.translated.set_text('')
        self.open_button.set_sensitive(False)
        self.names.set_sensitive(False)
        self.cancel_button.set_sensitive(True)
        names = [n.strip() for n in self.names.get_text().split(';') if n.strip()]
        self.pilot = Pilot()
        def work():
            try:
                result = self.pilot.run(path, names, lambda msg: GLib.idle_add(self.set_status, msg))
                GLib.idle_add(self.done, result, None)
            except Exception as exc:
                GLib.idle_add(self.done, None, str(exc))
        self.worker = threading.Thread(target=work, name='eve-text-worker', daemon=False)
        self.worker.start()

    def set_status(self, message):
        if not self.closing:
            self.status.set_text(message)
        return False

    def cancel(self, _=None):
        if self.pilot:
            self.pilot.cancel()
        self.cancel_button.set_sensitive(False)
        self.status.set_text('Cancelando e liberando o modelo… A carga inicial pode levar alguns segundos.')

    def done(self, result, error):
        self.worker = None
        if self.closing:
            self.window.destroy()
            self.quit()
            return False
        self.open_button.set_sensitive(True)
        self.names.set_sensitive(True)
        self.cancel_button.set_sensitive(False)
        if error:
            self.status.set_text(error)
        else:
            self.original.set_text(result['input'])
            self.translated.set_text(result['translation'])
            cache = ' — do cache' if result['translation_cached'] else ''
            self.status.set_text(f"Concluído em {result['total_seconds']:.2f} s{cache}. Tradução automática; confira nomes e instruções importantes.")
            # Export only this app's result, including raw automatic output. No manual revision.
            write_private(ROOT / 'ultimo-texto.json', result)
        return False

    def close_requested(self, _):
        if self.chooser:
            self.chooser.destroy()
            self.chooser = None
        if self.worker:
            self.closing = True
            self.cancel()
            self.status.set_text('Encerrando e liberando o modelo…')
            return True
        return False

    def request_exit(self):
        if not self.close_requested(self.window):
            self.window.destroy()
            self.quit()
        return False


if __name__ == '__main__':
    lock = open(ROOT / '.tradutor.lock', 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('O tradutor de texto já está aberto.')
    (ROOT / '.tradutor.pid').write_text(str(os.getpid()))
    app = App()
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM,
                         app.request_exit)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT,
                         app.request_exit)
    try:
        app.run(None)
    finally:
        (ROOT / '.tradutor.pid').unlink(missing_ok=True)
