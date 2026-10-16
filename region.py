"""A local preview of the already consented window. Never captures or saves."""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib
from frames import frame_quality


class RegionPicker(Gtk.Window):
    def __init__(self, parent, image, chosen, cancelled):
        super().__init__(title='Marque a área do texto dentro da janela compartilhada',
                         transient_for=parent, modal=True)
        self.image, self.chosen, self.cancelled = image, chosen, cancelled
        self.set_default_size(1000, 700)
        self.rectangle = None
        self.finished = False
        self.transform = (1, 0, 0)
        self.quality = frame_quality(image)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_child(box)
        self.message = Gtk.Label(label='Confira que esta é a janela do jogo. Arraste só a área do texto. Se for outra aplicação, cancele; nenhum OCR começou.', wrap=True)
        box.append(self.message)
        self.area = Gtk.Overlay(hexpand=True, vexpand=True)
        self.picture = Gtk.Picture()
        self.picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.picture.set_can_shrink(True)
        self.area.set_child(self.picture)
        self.selection = Gtk.Frame(halign=Gtk.Align.START, valign=Gtk.Align.START)
        self.selection.add_css_class('eve-region-selection')
        css = Gtk.CssProvider()
        css.load_from_data(b'.eve-region-selection { border: 3px solid #00ee66; background: transparent; }')
        Gtk.StyleContext.add_provider_for_display(self.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.selection.set_can_target(False)
        self.selection.set_visible(False)
        self.area.add_overlay(self.selection)
        drag = Gtk.GestureDrag()
        drag.connect('drag-begin', self.begin)
        drag.connect('drag-update', self.update)
        self.area.add_controller(drag)
        box.append(self.area)
        row = Gtk.Box(spacing=8)
        self.confirm = Gtk.Button(label='Usar esta área do jogo')
        self.confirm.set_sensitive(False)
        self.confirm.connect('clicked', self.accept)
        cancel = Gtk.Button(label='Cancelar compartilhamento')
        cancel.connect('clicked', lambda _: self.close())
        row.append(self.confirm)
        row.append(cancel)
        box.append(row)
        self.connect('close-request', self.closed)
        self.update_image(image)

    def update_image(self, image):
        changed_size = image.size != self.image.size
        self.image = image
        self.quality = frame_quality(image)
        # RGBA gives the UI a conventional aligned texture; no Python Cairo bridge needed.
        self.texture = Gdk.MemoryTexture.new(image.width, image.height, Gdk.MemoryFormat.R8G8B8A8,
                            GLib.Bytes.new(image.convert('RGBA').tobytes()), image.width * 4)
        self.picture.set_paintable(self.texture)
        if changed_size:
            self.rectangle = None
            self.selection.set_visible(False)
        if self.quality['black'] or self.quality['uniform']:
            self.confirm.set_sensitive(False)
            self.message.set_text('O vídeo recebido está preto ou uniforme. A prévia continua atualizando. Não haverá OCR; mantenha o jogo visível.')
        else:
            self.message.set_text('Prévia ao vivo: confira a janela do jogo e marque a área do texto. Só depois clique em “Usar esta área do jogo”.')
            self.confirm.set_sensitive(bool(self.rectangle and abs(self.rectangle[2]) > 20 and abs(self.rectangle[3]) > 20))

    def begin(self, gesture, x, y):
        self.rectangle = (x, y, 0, 0)
        self.confirm.set_sensitive(False)

    def update(self, gesture, dx, dy):
        if self.rectangle:
            self.rectangle = (*self.rectangle[:2], dx, dy)
            self.confirm.set_sensitive(abs(dx) > 20 and abs(dy) > 20 and not (self.quality['black'] or self.quality['uniform']))
            x, y = self.rectangle[:2]
            self.selection.set_margin_start(max(0, round(min(x, x + dx))))
            self.selection.set_margin_top(max(0, round(min(y, y + dy))))
            self.selection.set_size_request(round(abs(dx)), round(abs(dy)))
            self.selection.set_visible(True)

    def accept(self, _):
        if self.quality['black'] or self.quality['uniform']:
            return
        x, y, dx, dy = self.rectangle
        width, height = self.area.get_allocated_width(), self.area.get_allocated_height()
        scale = min(width / self.image.width, height / self.image.height)
        ox, oy = (width - self.image.width * scale) / 2, (height - self.image.height * scale) / 2
        x1, x2 = sorted(((x - ox) / scale, (x + dx - ox) / scale))
        y1, y2 = sorted(((y - oy) / scale, (y + dy - oy) / scale))
        x1, x2 = max(0, x1), min(self.image.width, x2)
        y1, y2 = max(0, y1), min(self.image.height, y2)
        if x2 - x1 < 20 or y2 - y1 < 20:
            return
        self.finished = True
        self.chosen((round(x1), round(y1), round(x2), round(y2)), self.image.size)
        self.destroy()

    def closed(self, _):
        if not self.finished:
            self.finished = True
            self.cancelled()
        return False
