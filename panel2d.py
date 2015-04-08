from __future__ import division

import numpy as np

from traits.api import (HasTraits, List, Instance, Any, Enum, Tuple, Float,
    Property, Bool, on_trait_change)
from traitsui.api import (View, Item, HGroup, VGroup, Group, NullEditor,
    InstanceEditor, CSVListEditor)

from enable.component_editor import ComponentEditor
from chaco.api import Plot, ArrayPlotData
from chaco.api import bone as bone_cmap
from chaco.api import RdBu as rdbu_cmap
from chaco.api import reverse as reverse_cmap
from chaco.tools.api import SelectTool

import nibabel as nib

from geometry import truncate, apply_affine, get_vox2rasxfm

class Click2DPanelTool(SelectTool):
    
    panel2d = Any #Instance(TwoDimensionalPanel)
    panel_id = Enum('xy','xz','yz')

    def __init__(self, panel2d, panel_id):
        self.panel2d = panel2d
        self.panel_id = panel_id

    def normal_left_down(self, event):
        x,y,z = self.panel2d.cursor            

        #if the panel is not in the image (e.g. a click on the axis), ignore it
        #TODO

        #remember event.x and event.y are in space of pixels

        if self.panel_id == 'xy':
            mx, my = self.panel2d.xy_plane.map_data((event.x, event.y))
            if x == mx and y == my:
                return
            self.panel2d.move_cursor(mx, my, z)

        elif self.panel_id == 'xz':
            mx, mz = self.panel2d.xz_plane.map_data((event.x, event.y))
            if x == mx and z == mz:
                return
            self.panel2d.move_cursor(mx, y, mz)

        elif self.panel_id == 'yz':
            my, mz = self.panel2d.yz_plane.map_data((event.x, event.y))
            if y == my and z == mz:
                return
            self.panel2d.move_cursor(x, my, mz)

        else:
            raise NotImplementedError('FailFish')

    def normal_mouse_move(self, event):
        x,y,z = self.panel2d.cursor    

        if self.panel_id == 'xy':
            mx, my = self.panel2d.xy_plane.map_data((event.x, event.y))
            self.panel2d.move_mouse(mx, my, z) 

        elif self.panel_id == 'xz':
            mx, mz = self.panel2d.xy_plane.map_data((event.x, event.y))
            self.panel2d.move_mouse(mx, y, mz)

        elif self.panel_id == 'yz':
            my, mz = self.panel2d.yz_plane.map_data((event.x, event.y))
            self.panel2d.move_mouse(x, my, mz)

        else:
            raise NotImplementedError('DansGame')

class InfoPanel(HasTraits):
    cursor = Property(Tuple)
    cursor_ras = Property(Tuple)
    cursor_tkr = Property(Tuple)
    cursor_intensity = Float

    mouse = Tuple((0.,0.,0.))
    mouse_ras = Tuple((0.,0.,0.))
    mouse_tkr = Tuple((0.,0.,0.))
    mouse_intensity = Float

    cursor_csvlist = List(Float)
    cursor_ras_csvlist = List(Float)
    cursor_tkr_csvlist = List(Float)

    traits_view = View(
        VGroup(
            Item(name='cursor_csvlist', style='text',
                editor=CSVListEditor(enter_set=True, auto_set=False)),
            Item(name='cursor_ras_csvlist', style='text',
                editor=CSVListEditor(enter_set=True, auto_set=False)),
            Item(name='cursor_tkr_csvlist', style='text',
                editor=CSVListEditor(enter_set=True, auto_set=False)),
            Item(name='cursor_intensity', style='readonly'),
            Item(name='mouse', style='readonly'),
            Item(name='mouse_ras', style='readonly'),
            Item(name='mouse_tkr', style='readonly'),
            Item(name='mouse_intensity', style='readonly'),
        ),
        title='ilumbumbargu',
    )

    def _get_cursor(self):
        return tuple(self.cursor_csvlist)
    def _set_cursor(self, newval):
        self.cursor_csvlist = list(newval)
    def _get_cursor_ras(self):
        return tuple(self.cursor_ras_csvlist)
    def _set_cursor_ras(self, newval):
        self.cursor_ras_csvlist = list(newval)
    def _get_cursor_tkr(self):
        return tuple(self.cursor_tkr_csvlist)
    def _set_cursor_tkr(self, newval):
        self.cursor_tkr_csvlist = list(newval)

class TwoDimensionalPanel(HasTraits):
    images = List

    current_image = Any # np.ndarray XxYxZ
    current_affine = Any
    current_tkr_affine = Any

    xy_plane = Instance(Plot)
    xz_plane = Instance(Plot)
    yz_plane = Instance(Plot)
    
    info_panel = Instance(InfoPanel, ())

    #later we will rename cursor to "coord"

    cursor = Tuple # 3-tuple

    null = Any # None

    _finished_plotting = Bool(False)

    traits_view = View(
        Group(
        HGroup(
            Item(name='xz_plane', editor=ComponentEditor(),
                height=400, width=400, show_label=False, resizable=True),
            Item(name='yz_plane', editor=ComponentEditor(),
                height=400, width=400, show_label=False, resizable=True),
        ),
        HGroup(
            Item(name='xy_plane', editor=ComponentEditor(),
                height=400, width=400, show_label=False, resizable=True),
            Item(name='info_panel', 
                    editor=InstanceEditor(), 
                style='custom',
            #Item(name='null', editor=NullEditor(),
                height=400, width=400, show_label=False, resizable=True),
        ),
        ),
        title='Contact 867-5309 for blobfish sales',
    )

    def map_cursor(self, cursor, affine, invert=False):
        x,y,z = cursor
        aff_to_use = np.linalg.inv(affine) if invert else affine
        mcursor, = apply_affine([cursor], aff_to_use)
        return tuple(map(lambda x: truncate(x, 2), mcursor))

    def cut_data(self, data, mcursor):
        xm,ym,zm = [int(np.round(c)) for c in mcursor]
        #xm, ym, zm = mcursor
        #yz_cut = np.rot90(data[xm,:,:].T)
        #xz_cut = np.rot90(data[:,ym,:].T)
        #xy_cut = np.rot90(data[:,:,zm].T)
        yz_cut = data[xm,:,:].T
        xz_cut = data[:,ym,:].T
        xy_cut = data[:,:,zm].T
        return xy_cut, xz_cut, yz_cut

    def load_img(self, imgf):
        self._finished_plotting = False

        img = nib.load(imgf)

        self.current_affine = aff = img.get_affine()
        self.current_tkr_affine = get_vox2rasxfm(imgf, stem='vox2ras-tkr')

        from nilearn.image.resampling import reorder_img

        #img = reorder_img(uimg, resample='continuous')

        xsz, ysz, zsz = img.shape

        print 'image coordinate transform', img.get_affine()

        imgd = img.get_data()
        print 'image size', imgd.shape

        self.images.append(imgd)
        self.current_image = imgd

        self.cursor = x,y,z = tuple(np.array(imgd.shape) // 2)

        xy_cut, xz_cut, yz_cut = self.cut_data(imgd, self.cursor)

        print xy_cut.shape, xz_cut.shape, yz_cut.shape

        xy_plotdata = ArrayPlotData()
        xy_plotdata.set_data('imagedata', xy_cut)
        xy_plotdata.set_data('cursor_x', np.array((x,)))
        xy_plotdata.set_data('cursor_y', np.array((y,)))

        xz_plotdata = ArrayPlotData()
        xz_plotdata.set_data('imagedata', xz_cut)
        xz_plotdata.set_data('cursor_x', np.array((x,)))
        xz_plotdata.set_data('cursor_z', np.array((z,)))

        yz_plotdata = ArrayPlotData()
        yz_plotdata.set_data('imagedata', yz_cut)
        yz_plotdata.set_data('cursor_y', np.array((y,)))
        yz_plotdata.set_data('cursor_z', np.array((z,)))

        self.xy_plane = Plot(xy_plotdata, bgcolor='black',
            aspect_ratio=xsz/ysz)
        self.xz_plane = Plot(xz_plotdata, bgcolor='black',
            aspect_ratio=xsz/zsz)
        self.yz_plane = Plot(yz_plotdata, bgcolor='black',
            aspect_ratio=ysz/zsz)

        self.xy_plane.img_plot('imagedata',name='',colormap=bone_cmap)
        self.xz_plane.img_plot('imagedata',name='',colormap=bone_cmap)
        self.yz_plane.img_plot('imagedata',name='',colormap=bone_cmap)

        #self.xz_plane.y_mapper.range.high = 512

        self.xy_plane.plot(('cursor_x','cursor_y'), type='scatter', 
            color='red', marker='plus', size=3)
        self.xz_plane.plot(('cursor_x','cursor_z'), type='scatter',
            color='red', marker='plus', size=3)
        self.yz_plane.plot(('cursor_y','cursor_z'), type='scatter',
            color='red', marker='plus', size=3)

        self.xy_plane.tools.append(Click2DPanelTool(self, 'xy'))
        self.xz_plane.tools.append(Click2DPanelTool(self, 'xz'))
        self.yz_plane.tools.append(Click2DPanelTool(self, 'yz'))

        #from PyQt4.QtCore import pyqtRemoveInputHook
        #import pdb
        #pyqtRemoveInputHook()
        #pdb.set_trace()

        self.info_panel.cursor = self.cursor
        self.info_panel.cursor_ras = self.map_cursor(self.cursor, aff)
        self.info_panel.cursor_tkr = self.map_cursor(self.cursor,
            self.current_tkr_affine)
        self.info_panel.cursor_intensity = self.current_image[x,y,z]

        self._finished_plotting = True

    def cursor_outside_image_dimensions(self, cursor, image=None):
        if image is None:
            image = self.current_image

        x, y, z = cursor

        x_sz, y_sz, z_sz = image.shape

        if not 0 <= x < x_sz:
            return True
        if not 0 <= y < y_sz:
            return True
        if not 0 <= z < z_sz:
            return True
        
        return False

    def move_cursor(self, x, y, z, suppress_cursor=False, suppress_ras=False,
            suppress_tkr=False):

        #it doesnt seem necessary for the instance variable cursor to exist
        #at all but this code isn't broken
        cursor = x,y,z

        if self.cursor_outside_image_dimensions(cursor):
            return

        self.cursor = cursor

        xy_cut, xz_cut, yz_cut = self.cut_data(self.current_image, self.cursor)

        print 'clicked on point %.2f %.2f %.2f'%(x,y,z)

        self.xy_plane.data.set_data('imagedata', xy_cut)
        self.xz_plane.data.set_data('imagedata', xz_cut)
        self.yz_plane.data.set_data('imagedata', yz_cut)

        self.xy_plane.data.set_data('cursor_x', np.array((x,)))
        self.xy_plane.data.set_data('cursor_y', np.array((y,)))

        self.xz_plane.data.set_data('cursor_x', np.array((x,)))
        self.xz_plane.data.set_data('cursor_z', np.array((z,)))

        self.yz_plane.data.set_data('cursor_y', np.array((y,)))
        self.yz_plane.data.set_data('cursor_z', np.array((z,)))

        if not suppress_cursor:
            self.info_panel.cursor = tuple(
                map(lambda x:truncate(x, 2), self.cursor))
        if not suppress_ras:
            self.info_panel.cursor_ras = self.map_cursor(self.cursor,
                self.current_affine)
        if not suppress_tkr:
            self.info_panel.cursor_tkr = self.map_cursor(self.cursor,
                self.current_tkr_affine)
        self.info_panel.cursor_intensity = truncate(self.current_image[x,y,z],3)

    def move_mouse(self, x, y, z):
        mouse = (x,y,z)

        if self.cursor_outside_image_dimensions(mouse):
            return

        self.info_panel.mouse = tuple(map(lambda x:truncate(x, 2), mouse))
        self.info_panel.mouse_ras = self.map_cursor(mouse,
            self.current_affine)
        self.info_panel.mouse_tkr = self.map_cursor(mouse, 
            self.current_tkr_affine)
        self.info_panel.mouse_intensity = truncate(self.current_image[x,y,z], 3)

    #because these calls all call map_cursor, which changes the listener
    #variables they end up infinite looping.

    #to solve this we manage _finished_plotting manually
    #so that move_cursor is only called once when any listener is triggered
    @on_trait_change('info_panel:cursor_csvlist')
    def _listen_cursor(self):
        if self._finished_plotting:
            self._finished_plotting = False
            x,y,z = self.info_panel.cursor
            self.move_cursor(x,y,z, suppress_cursor=True)
            self._finished_plotting = True

    @on_trait_change('info_panel:cursor_ras_csvlist')
    def _listen_cursor_ras(self):
        if self._finished_plotting:
            self._finished_plotting = False
            x,y,z = self.map_cursor(self.info_panel.cursor_ras,
                self.current_affine, invert=True)
            self.move_cursor(x,y,z, suppress_ras=True)
            self._finished_plotting = True

    @on_trait_change('info_panel:cursor_tkr_csvlist')
    def _listen_cursor_tkr(self):
        if self._finished_plotting:
            self._finished_plotting = False
            x,y,z = self.map_cursor(self.info_panel.cursor_tkr,
                self.current_tkr_affine, invert=True)
            self.move_cursor(x,y,z, suppress_tkr=True)
            self._finished_plotting = True