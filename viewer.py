"""Viewer only: reads the running pilot's completed output, never captures/loads models."""
import json
from pathlib import Path
import time
import os
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, GLib, Gdk, Gio

from settings import STATE_DIR as ROOT, write_private


class Viewer(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='local.tradutordejogos.resultado')
        self.window=None
        self.stamp=0
        self.updates=0
        self.last_error=None
        self.timer=None

    def do_activate(self):
        if self.window is not None:
            self.window.present()
            return
        self.window=Gtk.ApplicationWindow(application=self,title='TRADUÇÃO PT-BR — Tradutor de Jogos')
        self.window.add_css_class('eve-result-window')
        self.window.set_decorated(False)
        self.window.set_default_size(960,220)
        self.window.set_size_request(300,100)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        for side in ['top','bottom','start','end']:getattr(box,'set_margin_'+side)(12)
        self.window.set_child(box)
        self.label=Gtk.Label(xalign=0,wrap=True)
        self.label.set_visible(False)
        box.append(self.label)
        view=Gtk.TextView(editable=False,wrap_mode=Gtk.WrapMode.WORD_CHAR)
        view.add_css_class('eve-result')
        view.set_left_margin(14);view.set_right_margin(14)
        css=Gtk.CssProvider()
        css.load_from_data(b'window.eve-result-window { border: none; box-shadow: none; } window.eve-result-window, .eve-result-window box, .eve-result-window scrolledwindow, .eve-result-window windowhandle, textview.eve-result, textview.eve-result text { color: #FFFFFF; background-color: #000000; } .eve-result-window label { color: #FFFFFF; } .eve-result-window button, .eve-result-window menubutton button { color: #FFFFFF; background-color: #263343; background-image: none; border: 1px solid #718096; box-shadow: none; } .eve-result-window button:hover { background-color: #394D65; } .eve-result-window button label { color: #FFFFFF; } .eve-result-window button.eve-close-compact, .eve-result-window menubutton button { padding: 1px 5px; min-height: 0; min-width: 0; font-size: 10px; } textview.eve-result text { font-size: 22px; } textview.eve-result text selection { color: #FFFFFF; background-color: #275D88; }')
        Gtk.StyleContext.add_provider_for_display(self.window.get_display(),css,Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self.buffer=view.get_buffer()
        self.white_tag=self.buffer.create_tag('texto-branco-explicito',foreground='#FFFFFF',background='#000000')
        scroll=Gtk.ScrolledWindow(vexpand=True,hexpand=True);scroll.set_child(view);box.append(scroll)
        footer=Gtk.Box(spacing=4)
        self.move_handle=Gtk.WindowHandle(hexpand=True)
        move_label=Gtk.Label(xalign=0)
        move_label.set_markup('<span foreground="#FFFFFF" size="small">⋮⋮</span>')
        self.move_handle.set_child(move_label)
        self.move_handle.set_cursor_from_name('move')
        self.move_handle.set_tooltip_text('Arraste esta alça para mover. Botão direito abre o menu nativo da janela. Esc fecha só a legenda.')
        footer.append(self.move_handle)
        menu=Gio.Menu()
        menu.append('Mostrar barra da janela','app.decoracao')
        menu.append('Fechar legenda','app.fechar')
        for name in ['decoracao']:
            action=Gio.SimpleAction.new_stateful(name,None,GLib.Variant('b',False))
            action.connect('activate',self.toggle_view)
            self.add_action(action)
        action=Gio.SimpleAction.new('fechar',None)
        action.connect('activate',lambda *args:self.close_viewer());self.add_action(action)
        options=Gtk.MenuButton(label='⋮',menu_model=menu)
        options.set_tooltip_text('Opções da legenda')
        footer.append(options)
        self.close_button=Gtk.Button()
        self.close_button.add_css_class('eve-close-compact')
        self.close_button.set_halign(Gtk.Align.END)
        close_label=Gtk.Label()
        close_label.set_markup('<span foreground="#FFFFFF" size="small">Fechar legenda</span>')
        self.close_button.set_child(close_label)
        self.close_button.connect('clicked',lambda _:self.close_viewer());footer.append(self.close_button)
        box.append(footer)
        keys=Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed',self.key_pressed);self.window.add_controller(keys)
        self.tick()
        if not os.environ.get('TG_VIEWER_TEST'):
            self.timer=GLib.timeout_add(500,self.tick)
            self.window.present()
            GLib.idle_add(self.write_state)

    def close_viewer(self):
        self.window.close()

    def key_pressed(self,controller,keyval,keycode,state):
        if keyval==Gdk.KEY_Escape or (keyval in [Gdk.KEY_q,Gdk.KEY_Q] and state&Gdk.ModifierType.CONTROL_MASK):
            self.close_viewer();return True
        return False

    def toggle_view(self,action,param):
        value=not action.get_state().get_boolean()
        action.set_state(GLib.Variant('b',value))
        self.window.set_decorated(value)

    def tick(self):
        p=ROOT/'ultimo-texto-ao-vivo.json'
        try:
            stamp=p.stat().st_mtime
            if stamp!=self.stamp:
                d=json.loads(p.read_text())
                self.buffer.set_text(d['translation'])
                self.buffer.apply_tag(self.white_tag,self.buffer.get_start_iter(),self.buffer.get_end_iter())
                self.set_status('Última leitura concluída às '+time.strftime('%H:%M:%S UTC',time.gmtime(stamp))+
                    f" — {d['total_seconds']:.1f} s. Pode estar atrasada em relação à página atual.")
                self.stamp=stamp
                self.updates+=1
                self.last_error=None
        except (OSError,ValueError,KeyError) as exc:
            self.last_error=type(exc).__name__+': '+str(exc)
            self.set_status('Aguardando tradução concluída. '+self.last_error)
        self.write_state()
        return True

    def set_status(self,text):
        self.label.set_markup('<span foreground="#FFFFFF">'+GLib.markup_escape_text(text)+'</span>')

    def write_state(self):
        if os.environ.get('TG_VIEWER_TEST'):return False
        state={'pid':__import__('os').getpid(),'title':self.window.get_title(),
               'visible':self.window.get_visible(),'mapped':self.window.get_mapped(),
               'active':self.window.is_active(),'width':self.window.get_width(),
               'height':self.window.get_height(),'characters_in_buffer':self.buffer.get_char_count(),
               'updates':self.updates,'source_mtime':self.stamp,'error':self.last_error,
               'text_foreground':'#FFFFFF','text_background':'#000000',
               'decorated':self.window.get_decorated(),'move_handle':'Gtk.WindowHandle',
               'close_shortcut':'Esc / Ctrl+Q (only this window)',
               'button_foreground':'#FFFFFF','button_background':'#263343',
               'explicit_foreground_tag':self.white_tag.get_property('foreground-set'),
               'time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
        p=ROOT/'estado-visor.json'
        write_private(p,state)
        return False

    def do_shutdown(self):
        if self.timer:GLib.source_remove(self.timer)
        p=ROOT/'estado-visor.json'
        try:
            d=json.loads(p.read_text());d.update({'shutdown':True,'visible':False,'mapped':False})
            write_private(p,d)
        except (OSError,ValueError):pass
        Gtk.Application.do_shutdown(self)


if __name__=='__main__':
    Viewer().run(None)
