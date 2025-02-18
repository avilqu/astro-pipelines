#!/home/tan/Astro/pipelines/.venv/bin/python

import tkinter as tk
from tkinter import ttk
from tkinter.filedialog import askopenfilename
from PIL import Image, ImageTk
import matplotlib.pyplot as plt
import numpy as np
import scipy as sp
from astropy.io import fits


class GUI():

    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Astro-Pipelines')
        self.root.tk.call('tk', 'scaling', 1.0)
        self.root.rowconfigure(0, minsize=1000, weight=1)
        self.root.columnconfigure(1, minsize=1000, weight=1)

        vbar = AutoScrollbar(self.root, orient='vertical')
        hbar = AutoScrollbar(self.root, orient='horizontal')
        vbar.grid(row=0, column=2, sticky='ns')
        hbar.grid(row=1, column=1, sticky='we')

        self.canvas = tk.Canvas(self.root, highlightthickness=0,
                                xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        self.frame = tk.Frame(self.root, relief=tk.RAISED, bd=2)
        self.btn_open = tk.Button(
            self.frame, text='Open', command=self.open_file)

        self.btn_open.grid(row=0, column=0, sticky='ew', padx=5, pady=5)
        self.frame.grid(row=0, column=0, sticky='ns')
        self.canvas.grid(row=0, column=1, sticky='nsew')

        self.imscale = 1.0
        self.imageid = None
        self.delta = 0.75

        vbar.configure(command=self.scroll_y)
        hbar.configure(command=self.scroll_x)

        self.canvas.bind('<Configure>', self.show_image)
        self.canvas.bind('<ButtonPress-1>', self.move_from)
        self.canvas.bind('<B1-Motion>', self.move_to)
        self.canvas.bind('<Button-5>', self.wheel)
        self.canvas.bind('<Button-4>', self.wheel)

    def scroll_y(self, *args, **kwargs):
        ''' Scroll canvas vertically and redraw the image '''
        self.canvas.yview(*args, **kwargs)
        self.show_image()

    def scroll_x(self, *args, **kwargs):
        ''' Scroll canvas horizontally and redraw the image '''
        self.canvas.xview(*args, **kwargs)
        self.show_image()

    def move_from(self, event):
        ''' Remember previous coordinates for scrolling with the mouse '''
        self.canvas.scan_mark(event.x, event.y)

    def move_to(self, event):
        ''' Drag (move) canvas to the new position '''
        self.canvas.scan_dragto(event.x, event.y, gain=1)
        self.show_image()

    def wheel(self, event):
        ''' Zoom with mouse wheel '''
        scale = 1.0
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)

        bbox = self.canvas.bbox(self.container)
        if bbox[0] < x < bbox[2] and bbox[1] < y < bbox[3]:
            pass
        else:
            return

        if event.num == 5:
            i = min(self.width, self.height)
            if int(i * self.imscale) < 30:
                return
            self.imscale /= self.delta
            scale /= self.delta
        if event.num == 4:
            i = min(self.canvas.winfo_width(), self.canvas.winfo_height())
            if i < self.imscale:
                return
            self.imscale *= self.delta
            scale *= self.delta

        self.canvas.scale('all', x, y, scale, scale)
        self.show_image()

    def create_image_object(self, image_data: np.ndarray):
        print(f'image_data {image_data}')
        print(image_data.dtype)

        histo = sp.histogram(image_data, 60, None, True)
        self.display_min = histo[1][0]
        self.display_max = histo[1][1]
        plt.imsave("tempimgfile.gif", image_data, cmap=plt.cm.gray,
                   vmin=self.display_min, vmax=self.display_max, origin="lower")

        # return Image.fromarray(image_data, mode='I;16')
        return Image.fromarray(image_data.astype('uint8'), mode='L')
        # return Image.fromarray((stretched_data * 255).astype('uint16'), mode='I;16')
        # return Image.fromarray(stretched_data.astype('uint16'), mode='I;16')
        # return Image.fromarray(image_data, mode='I;16')

    def open_file(self):
        filepath = askopenfilename(
            filetypes=[('FITS Files', '*.fits'), ('All Files', '*.*')]
        )

        hdu_list = fits.open(filepath)
        hdu_list.info()
        image_data = hdu_list[0].data

        self.load_image(image_data, filepath)

    def load_image(self, image_data=None, title=None):
        self.image_data = image_data
        self.image = self.create_image_object(image_data)
        self.width, self.height = self.image.size
        self.container = self.canvas.create_rectangle(
            0, 0, self.width, self.height, width=0)
        self.show_image()
        self.root.title(f'Astro-Pipelines - {title}')

    def show_image(self):
        bbox1 = self.canvas.bbox(self.container)
        bbox1 = (bbox1[0] + 1, bbox1[1] + 1, bbox1[2] - 1, bbox1[3] - 1)
        bbox2 = (self.canvas.canvasx(0),
                 self.canvas.canvasy(0),
                 self.canvas.canvasx(self.canvas.winfo_width()),
                 self.canvas.canvasy(self.canvas.winfo_height()))
        bbox = [min(bbox1[0], bbox2[0]), min(bbox1[1], bbox2[1]),
                max(bbox1[2], bbox2[2]), max(bbox1[3], bbox2[3])]

        if bbox[0] == bbox2[0] and bbox[2] == bbox2[2]:
            bbox[0] = bbox1[0]
            bbox[2] = bbox1[2]
        if bbox[1] == bbox2[1] and bbox[3] == bbox2[3]:
            bbox[1] = bbox1[1]
            bbox[3] = bbox1[3]

        self.canvas.configure(scrollregion=bbox)

        x1 = max(bbox2[0] - bbox1[0], 0)
        y1 = max(bbox2[1] - bbox1[1], 0)
        x2 = min(bbox2[2], bbox1[2]) - bbox1[0]
        y2 = min(bbox2[3], bbox1[3]) - bbox1[1]

        if int(x2 - x1) > 0 and int(y2 - y1) > 0:
            x = min(int(x2 / self.imscale), self.width)
            y = min(int(y2 / self.imscale), self.height)
            image = self.image.crop(
                (int(x1 / self.imscale), int(y1 / self.imscale), x, y))
            imagetk = ImageTk.PhotoImage(
                image.resize((int(x2 - x1), int(y2 - y1))))
            imageid = self.canvas.create_image(max(bbox2[0], bbox1[0]), max(bbox2[1], bbox1[1]),
                                               anchor='nw', image=imagetk)
            self.canvas.lower(imageid)
            self.canvas.imagetk = imagetk
        # hold = tk.PhotoImage(file="tempimgfile.gif")
        # self.canvas.create_image(0,0,image=hold,anchor="nw")

    def start_GUI(self):
        self.root.mainloop()


class AutoScrollbar(ttk.Scrollbar):
    ''' A scrollbar that hides itself if it's not needed.
        Works only if you use the grid geometry manager '''

    def set(self, lo, hi):
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            self.grid_remove()
        else:
            self.grid()
            ttk.Scrollbar.set(self, lo, hi)

    def pack(self, **kw):
        raise tk.TclError('Cannot use pack with this widget')

    def place(self, **kw):
        raise tk.TclError('Cannot use place with this widget')


app = GUI()
app.start_GUI()
