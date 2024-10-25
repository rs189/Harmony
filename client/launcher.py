import cairo
import colorsys
import _thread
import gi
import json
import os
import re
import subprocess
import sys
import threading
import time

from collections import Counter
from common import HarmonyClientCommon
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf
from logger import Logger
from PIL import Image

current_path = os.path.dirname(os.path.realpath(__file__))
logger = Logger(os.path.join(current_path, 'app.log'), False)

# Gtk application window
class HarmonyLauncherWindow(Gtk.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        application = kwargs.get('application')
        self.app_name = application.app_name
        self.app_splash = application.app_splash
        self.app_colour = application.app_colour
        self.harmony_client = None

        self.set_default_size(600, 280)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_resizable(False)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main_box.override_background_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(0.14, 0.14, 0.14, 1.0))
        self.add(main_box)

        # Create content box for the main content
        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        main_box.pack_start(content_box, True, True, 0)
        
        left_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        left_container.set_margin_start(20)
        left_container.set_margin_top(15)
        left_container.set_margin_bottom(10)
        content_box.pack_start(left_container, False, False, 0)
        
        image_path = os.path.join(current_path, 'apps', self.app_splash)
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)

        dominant_color = self.get_dominant_color(image_path)

        aspect_ratio = pixbuf.get_width() / pixbuf.get_height()
        target_height = 240
        target_width = int(target_height * aspect_ratio)
        
        scaled_pixbuf = pixbuf.scale_simple(target_width, target_height, GdkPixbuf.InterpType.BILINEAR)
        image = Gtk.Image.new_from_pixbuf(scaled_pixbuf)
        left_container.pack_start(image, False, False, 0)

        right_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        right_content.set_margin_top(15)
        right_content.set_margin_end(20)
        right_content.set_margin_bottom(10)
        content_box.pack_start(right_content, True, True, 0)
        
        title_label = Gtk.Label()
        title_label.set_markup(f'<span size="18432" weight="800" foreground="white">{self.app_name}</span>')
        title_label.set_halign(Gtk.Align.START)
        right_content.pack_start(title_label, False, False, 0)
        
        self.label = Gtk.Label()
        self.label.set_markup('<span foreground="gray" size="small">STARTING APP...</span>')
        self.label.set_halign(Gtk.Align.START)
        right_content.pack_start(self.label, False, False, 0)
        
        spacer = Gtk.Box()
        right_content.pack_start(spacer, True, True, 0)
        
        button = Gtk.Button(label="Cancel")
        button.set_halign(Gtk.Align.FILL)
        button.set_size_request(-1, 28)
        right_content.pack_end(button, False, False, 0)

        def on_cancel_button_clicked(button):
            if self.harmony_client is not None:
                self.harmony_client.cancel_start_app()

        button.connect("clicked", on_cancel_button_clicked)

        self.gradient_bar = Gtk.DrawingArea()
        self.gradient_bar.set_size_request(-1, 4)
        self.gradient_offset = 0.0
        self.gradient_bar.connect('draw', self.draw_gradient, dominant_color)
        main_box.pack_end(self.gradient_bar, False, False, 0)

        GLib.timeout_add(50, self.update_gradient) # Update every 50ms (20fps)

        self.setup_css()
        
        self.lg_ready = False
        self.connect("destroy", self.on_destroy)

    def get_dominant_color(self, image_path):
        if self.app_colour is not None and self.app_colour != "":
            self.app_colour = self.app_colour.lstrip('#')
            color = tuple(int(self.app_colour[i:i+2], 16) for i in (0, 2, 4))
            return color

        img = Image.open(image_path)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.thumbnail((100, 100))

        colors = img.getdata()
        filtered_colors = [color for color in colors 
                           if not (all(c > 240 for c in color) or all(c < 15 for c in color))]
        color_counts = Counter(filtered_colors)
        dominant_color = color_counts.most_common(1)[0][0]
        return dominant_color

    def darken_color(self, color, factor=0.75):
        r, g, b = [x/255.0 for x in color]
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        v = max(0, v * factor)
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return (r, g, b, 1.0)

    def update_gradient(self):
        self.gradient_offset += 0.01
        if self.gradient_offset >= 1.0:
            self.gradient_offset = 0.0
        
        self.gradient_bar.queue_draw()
        return True

    def draw_gradient(self, widget, cr, color):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()

        pat = cairo.LinearGradient(-width, 0, width * 2, 0)
        
        start_color = (*[x/255.0 for x in color], 1.0)
        end_color = self.darken_color(color)

        offset = self.gradient_offset
        
        # Add multiple color stops for smooth transition
        # Before visible area
        pat.add_color_stop_rgba(-0.5 + offset, *start_color)
        pat.add_color_stop_rgba(-0.25 + offset, *end_color)
        pat.add_color_stop_rgba(0.0 + offset, *start_color)
        
        # Visible area
        pat.add_color_stop_rgba(0.25 + offset, *end_color)
        pat.add_color_stop_rgba(0.5 + offset, *start_color)
        pat.add_color_stop_rgba(0.75 + offset, *end_color)
        pat.add_color_stop_rgba(1.0 + offset, *start_color)
        
        # After visible area
        pat.add_color_stop_rgba(1.25 + offset, *end_color)
        pat.add_color_stop_rgba(1.5 + offset, *start_color)

        cr.set_source(pat)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        
        return False

    def setup_css(self):
        css_provider = Gtk.CssProvider()
        css = """
            button {
                background-image: none;
                background-color: rgba(255, 255, 255, 0.1);
                color: white;
                border-radius: 4px;
                border: none;
                box-shadow: none;
                text-shadow: none;
                -gtk-icon-shadow: none;
            }
            button:hover {
                background-image: none;
                background-color: rgba(255, 255, 255, 0.15);
                box-shadow: none;
            }
            button:active {
                background-image: none;
                background-color: rgba(255, 255, 255, 0.2);
            }
        """
        css_provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def on_destroy(self, *args):
        print("Destroying window...")
        if not self.lg_ready:
            current_pid = os.getpid()
            subprocess.run(['kill', str(current_pid)])
        Gtk.main_quit()

    def update_label(self, new_text):
        GLib.idle_add(self.label.set_markup, 
                     f'<span foreground="gray" size="small">{new_text}</span>')