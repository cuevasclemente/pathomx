from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import signal
import sys
import re

import matplotlib

from matplotlib.cbook import is_string_like
from matplotlib.backend_bases import FigureManagerBase
from matplotlib.backend_bases import FigureCanvasBase
from matplotlib.backend_bases import NavigationToolbar2

from matplotlib.backend_bases import cursors
from matplotlib.backend_bases import TimerBase
from matplotlib.backend_bases import ShowBase

from matplotlib._pylab_helpers import Gcf
from matplotlib.figure import Figure

from matplotlib.widgets import SubplotTool
try:
    import matplotlib.backends.qt5_editor.figureoptions as figureoptions
except ImportError:
    figureoptions = None

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

from PyQt5 import QtWidgets

_getSaveFileName = QFileDialog.getSaveFileName


def fn_name():
    return sys._getframe(1).f_code.co_name

DEBUG = False

cursord = {
    cursors.MOVE: Qt.SizeAllCursor,
    cursors.HAND: Qt.PointingHandCursor,
    cursors.POINTER: Qt.ArrowCursor,
    cursors.SELECT_REGION: Qt.CrossCursor
}


def draw_if_interactive():
    """
    Is called after every pylab drawing command
    """
    if matplotlib.is_interactive():
        figManager = Gcf.get_active()
        if figManager is not None:
            figManager.canvas.draw_idle()


def _create_qApp():
    """
    Only one qApp can exist at a time, so check before creating one.
    """
    if QApplication.startingUp():
        if DEBUG:
            print("Starting up QApplication")
        global qApp
        app = QApplication.instance()
        if app is None:

            # check for DISPLAY env variable on X11 build of Qt
            if hasattr(QtWidgets, "QX11Info"):
                display = os.environ.get('DISPLAY')
                if display is None or not re.search(':\d', display):
                    raise RuntimeError('Invalid DISPLAY variable')

            qApp = QApplication([str(" ")])
            qApp.lastWindowClosed.connect(qApp.quit)
        else:
            qApp = app


class Show(ShowBase):
    def mainloop(self):
        # allow KeyboardInterrupt exceptions to close the plot window.
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        print('mainloop')
        qApp.exec_()
show = Show()


def new_figure_manager(num, *args, **kwargs):
    """
    Create a new figure manager instance
    """
    thisFig = Figure(*args, **kwargs)
    return new_figure_manager_given_figure(num, thisFig)


def new_figure_manager_given_figure(num, figure):
    """
    Create a new figure manager instance for the given figure.
    """
    canvas = FigureCanvasQT(figure)
    manager = FigureManagerQT(canvas, num)
    return manager


class TimerQT(TimerBase):
    """
    Subclass of :class:`backend_bases.TimerBase` that uses Qt5 timer events.

    Attributes:
    * interval: The time between timer events in milliseconds. Default
        is 1000 ms.
    * single_shot: Boolean flag indicating whether this timer should
        operate as single shot (run once and then stop). Defaults to False.
    * callbacks: Stores list of (func, args) tuples that will be called
        upon timer events. This list can be manipulated directly, or the
        functions add_callback and remove_callback can be used.
    """

    def __init__(self, *args, **kwargs):
        super(TimerQT, self).__init__(*args, **kwargs)

        # Create a new timer and connect the timeout() signal to the
        # _on_timer method.
        self._timer = QTimer()
        self._timer.timeout.connect(self._on_timer)
        self._timer_set_interval()

    def __del__(self):
        # Probably not necessary in practice, but is good behavior to
        # disconnect
        try:
            TimerBase.__del__(self)
            self._timer.timeout.disconnect(self._on_timer)
        except RuntimeError:
            # Timer C++ object already deleted
            pass

    def _timer_set_single_shot(self):
        self._timer.setSingleShot(self._single)

    def _timer_set_interval(self):
        self._timer.setInterval(self._interval)

    def _timer_start(self):
        self._timer.start()

    def _timer_stop(self):
        self._timer.stop()


class FigureCanvasQT(QWidget, FigureCanvasBase):
    keyvald = {
        Qt.Key_Control: 'control',
        Qt.Key_Shift: 'shift',
        Qt.Key_Alt: 'alt',
        Qt.Key_Meta: 'super',
        Qt.Key_Return: 'enter',
        Qt.Key_Left: 'left',
        Qt.Key_Up: 'up',
        Qt.Key_Right: 'right',
        Qt.Key_Down: 'down',
        Qt.Key_Escape: 'escape',
        Qt.Key_F1: 'f1',
        Qt.Key_F2: 'f2',
        Qt.Key_F3: 'f3',
        Qt.Key_F4: 'f4',
        Qt.Key_F5: 'f5',
        Qt.Key_F6: 'f6',
        Qt.Key_F7: 'f7',
        Qt.Key_F8: 'f8',
        Qt.Key_F9: 'f9',
        Qt.Key_F10: 'f10',
        Qt.Key_F11: 'f11',
        Qt.Key_F12: 'f12',
        Qt.Key_Home: 'home',
        Qt.Key_End: 'end',
        Qt.Key_PageUp: 'pageup',
        Qt.Key_PageDown: 'pagedown',
    }

    # define the modifier keys which are to be collected on keyboard events.
    # format is: [(modifier_flag, modifier_name, equivalent_key)
    _modifier_keys = [
        (Qt.MetaModifier, 'super', Qt.Key_Meta),
        (Qt.AltModifier, 'alt', Qt.Key_Alt),
        (Qt.ControlModifier, 'ctrl', Qt.Key_Control)
    ]

    _ctrl_modifier = Qt.ControlModifier

    if sys.platform == 'darwin':
        # in OSX, the control and super (aka cmd/apple) keys are switched, so
        # switch them back.
        keyvald.update({Qt.Key_Control: 'super',  # cmd/apple key
                        Qt.Key_Meta: 'control',
                        })

        _modifier_keys = [(Qt.ControlModifier, 'super',
                           Qt.Key_Control),
                          (Qt.AltModifier, 'alt',
                           Qt.Key_Alt),
                          (Qt.MetaModifier, 'ctrl',
                           Qt.Key_Meta),
                          ]

        _ctrl_modifier = Qt.MetaModifier

    # map Qt button codes to MouseEvent's ones:
    buttond = {Qt.LeftButton: 1,
               Qt.MidButton: 2,
               Qt.RightButton: 3,
               }

    def __init__(self, figure):
        if DEBUG:
            print('FigureCanvasQt: ', figure)
        _create_qApp()

        super(FigureCanvasQT, self).__init__(figure=figure)
        self.figure = figure
        self.setMouseTracking(True)
        self._idle = True
        w, h = self.get_width_height()
        self.resize(w, h)

    def __timerEvent(self, event):
        # hide until we can test and fix
        self.mpl_idle_event(event)

    def enterEvent(self, event):
        FigureCanvasBase.enter_notify_event(self, event)

    def leaveEvent(self, event):
        QApplication.restoreOverrideCursor()
        FigureCanvasBase.leave_notify_event(self, event)

    def mousePressEvent(self, event):
        x = event.pos().x()
        # flipy so y=0 is bottom of canvas
        y = self.figure.bbox.height - event.pos().y()
        button = self.buttond.get(event.button())
        if button is not None:
            FigureCanvasBase.button_press_event(self, x, y, button)
        if DEBUG:
            print('button pressed:', event.button())

    def mouseDoubleClickEvent(self, event):
        x = event.pos().x()
        # flipy so y=0 is bottom of canvas
        y = self.figure.bbox.height - event.pos().y()
        button = self.buttond.get(event.button())
        if button is not None:
            FigureCanvasBase.button_press_event(self, x, y,
                                                button, dblclick=True)
        if DEBUG:
            print('button doubleclicked:', event.button())

    def mouseMoveEvent(self, event):
        x = event.x()
        # flipy so y=0 is bottom of canvas
        y = self.figure.bbox.height - event.y()
        FigureCanvasBase.motion_notify_event(self, x, y)
        #if DEBUG: print('mouse move')

    def mouseReleaseEvent(self, event):
        x = event.x()
        # flipy so y=0 is bottom of canvas
        y = self.figure.bbox.height - event.y()
        button = self.buttond.get(event.button())
        if button is not None:
            FigureCanvasBase.button_release_event(self, x, y, button)
        if DEBUG:
            print('button released')

    def wheelEvent(self, event):
        x = event.x()
        # flipy so y=0 is bottom of canvas
        y = self.figure.bbox.height - event.y()
        # from QWheelEvent::delta doc
        if event.pixelDelta().x() == 0 and event.pixelDelta().y() == 0:
            steps = event.angleDelta().y() / 120
        else:
            steps = event.pixelDelta().y()

        if steps != 0:
            FigureCanvasBase.scroll_event(self, x, y, steps)
            if DEBUG:
                print('scroll event: delta = %i, '
                      'steps = %i ' % (event.delta(), steps))

    def keyPressEvent(self, event):
        key = self._get_key(event)
        if key is None:
            return
        FigureCanvasBase.key_press_event(self, key)
        if DEBUG:
            print('key press', key)

    def keyReleaseEvent(self, event):
        key = self._get_key(event)
        if key is None:
            return
        FigureCanvasBase.key_release_event(self, key)
        if DEBUG:
            print('key release', key)

    def resizeEvent(self, event):
        w = event.size().width()
        h = event.size().height()
        if DEBUG:
            print('resize (%d x %d)' % (w, h))
            print("FigureCanvasQt.resizeEvent(%d, %d)" % (w, h))
        dpival = self.figure.dpi
        winch = w / dpival
        hinch = h / dpival
        self.figure.set_size_inches(winch, hinch)
        FigureCanvasBase.resize_event(self)
        self.draw()
        self.update()
        QWidget.resizeEvent(self, event)

    def sizeHint(self):
        w, h = self.get_width_height()
        return QSize(w, h)

    def minumumSizeHint(self):
        return QSize(10, 10)

    def _get_key(self, event):
        if event.isAutoRepeat():
            return None

        if event.key() < 256:
            key = str(event.text())
            # if the control key is being pressed, we don't get the correct
            # characters, so interpret them directly from the event.key().
            # Unfortunately, this means that we cannot handle key's case
            # since event.key() is not case sensitive, whereas event.text() is,
            # Finally, since it is not possible to get the CapsLock state
            # we cannot accurately compute the case of a pressed key when
            # ctrl+shift+p is pressed.
            if int(event.modifiers()) & self._ctrl_modifier:
                # we always get an uppercase character
                key = chr(event.key())
                # if shift is not being pressed, lowercase it (as mentioned,
                # this does not take into account the CapsLock state)
                if not int(event.modifiers()) & Qt.ShiftModifier:
                    key = key.lower()

        else:
            key = self.keyvald.get(event.key())

        if key is not None:
            # prepend the ctrl, alt, super keys if appropriate (sorted
            # in that order)
            for modifier, prefix, Qt_key in self._modifier_keys:
                if (event.key() != Qt_key and
                        int(event.modifiers()) & modifier == modifier):
                    key = '{0}+{1}'.format(prefix, key)

        return key

    def new_timer(self, *args, **kwargs):
        """
        Creates a new backend-specific subclass of
        :class:`backend_bases.Timer`.  This is useful for getting
        periodic events through the backend's native event
        loop. Implemented only for backends with GUIs.

        optional arguments:

        *interval*
            Timer interval in milliseconds

        *callbacks*
            Sequence of (func, args, kwargs) where func(*args, **kwargs)
            will be executed by the timer every *interval*.

    """
        return TimerQT(*args, **kwargs)

    def flush_events(self):
        qApp.processEvents()

    def start_event_loop(self, timeout):
        FigureCanvasBase.start_event_loop_default(self, timeout)

    start_event_loop.__doc__ = FigureCanvasBase.start_event_loop_default.__doc__

    def stop_event_loop(self):
        FigureCanvasBase.stop_event_loop_default(self)

    stop_event_loop.__doc__ = FigureCanvasBase.stop_event_loop_default.__doc__

    def draw_idle(self):
        'update drawing area only if idle'
        d = self._idle
        self._idle = False

        def idle_draw(*args):
            self.draw()
            self._idle = True
        if d:
            QTimer.singleShot(0, idle_draw)


class MainWindow(QMainWindow):
    closing = pyqtSignal()

    def closeEvent(self, event):
        self.closing.emit()
        QMainWindow.closeEvent(self, event)


class FigureManagerQT(FigureManagerBase):
    """
    Public attributes

    canvas      : The FigureCanvas instance
    num         : The Figure number
    toolbar     : The qt.QToolBar
    window      : The qt.QMainWindow
    """

    def __init__(self, canvas, num):
        if DEBUG:
            print('FigureManagerQT.%s' % fn_name())
        super(FigureManagerQT, self).__init__(canvas=canvas, num=num)
        self.canvas = canvas
        self.window = MainWindow()
        self.window.closing.connect(canvas.close_event)
        self.window.closing.connect(self._widgetclosed)

        self.window.setWindowTitle("Figure %d" % num)
        image = os.path.join(matplotlib.rcParams['datapath'],
                             'images', 'matplotlib.png')
        self.window.setWindowIcon(QIcon(image))

        # Give the keyboard focus to the figure instead of the
        # manager; StrongFocus accepts both tab and click to focus and
        # will enable the canvas to process event w/o clicking.
        # ClickFocus only takes the focus is the window has been
        # clicked
        # on. http://qt-project.org/doc/qt-4.8/qt.html#FocusPolicy-enum or
        # http://doc.qt.digia.com/qt/qt.html#FocusPolicy-enum
        self.canvas.setFocusPolicy(Qt.StrongFocus)
        self.canvas.setFocus()

        self.window._destroying = False

        self.toolbar = self._get_toolbar(self.canvas, self.window)
        if self.toolbar is not None:
            self.window.addToolBar(self.toolbar)
            self.toolbar.message.connect(self._show_message)
            tbs_height = self.toolbar.sizeHint().height()
        else:
            tbs_height = 0

        # resize the main window so it will display the canvas with the
        # requested size:
        cs = canvas.sizeHint()
        sbs = self.window.statusBar().sizeHint()
        self._status_and_tool_height = tbs_height + sbs.height()
        height = cs.height() + self._status_and_tool_height
        self.window.resize(cs.width(), height)

        self.window.setCentralWidget(self.canvas)

        if matplotlib.is_interactive():
            self.window.show()

        def notify_axes_change(fig):
            # This will be called whenever the current axes is changed
            if self.toolbar is not None:
                self.toolbar.update()
        self.canvas.figure.add_axobserver(notify_axes_change)

    @pyqtSlot()
    def _show_message(self, s):
        # Fixes a PySide segfault.
        self.window.statusBar().showMessage(s)

    def full_screen_toggle(self):
        if self.window.isFullScreen():
            self.window.showNormal()
        else:
            self.window.showFullScreen()

    def _widgetclosed(self):
        if self.window._destroying:
            return
        self.window._destroying = True
        try:
            Gcf.destroy(self.num)
        except AttributeError:
            pass
            # It seems that when the python session is killed,
            # Gcf can get destroyed before the Gcf.destroy
            # line is run, leading to a useless AttributeError.

    def _get_toolbar(self, canvas, parent):
        # must be inited after the window, drawingArea and figure
        # attrs are set
        if matplotlib.rcParams['toolbar'] == 'toolbar2':
            toolbar = NavigationToolbar2QT(canvas, parent, False)
        else:
            toolbar = None
        return toolbar

    def resize(self, width, height):
        'set the canvas size in pixels'
        self.window.resize(width, height + self._status_and_tool_height)

    def show(self):
        self.window.show()

    def destroy(self, *args):
        if self.window._destroying:
            return
        self.window._destroying = True
        self.window.destroyed.connect(self._widgetclosed)

        if self.toolbar:
            self.toolbar.destroy()
        if DEBUG:
            print("destroy figure manager")
        self.window.close()

    def get_window_title(self):
        return str(self.window.windowTitle())

    def set_window_title(self, title):
        self.window.setWindowTitle(title)


class NavigationToolbar2QT(QToolBar, NavigationToolbar2):
    message = pyqtSignal(str)

    toolitems = (
        ('Home', 'Reset original view', 'home.png', 'home'),
        ('Back', 'Back to  previous view', 'back.png', 'back'),
        ('Forward', 'Forward to next view', 'forward.png', 'forward'),
        ('Pan', 'Pan axes with left mouse, zoom with right', 'move.png', 'pan'),
        ('Zoom', 'Zoom to rectangle', 'zoom_to_rect.png', 'zoom'),
        (None, None, None, None),
        ('Subplots', 'Configure subplots', 'subplots.png', 'configure_subplots'),
        ('Save', 'Save the figure', 'filesave.png', 'save_figure'),
        )

    def __init__(self, canvas, parent, coordinates=True):
        """ coordinates: should we show the coordinates on the right? """
        self.canvas = canvas
        self.coordinates = coordinates
        self._actions = {}
        """A mapping of toolitem method names to their QActions"""
        super(NavigationToolbar2QT, self).__init__(canvas=canvas, parent=parent)

    def _icon(self, name):
        return QIcon(os.path.join(self.basedir, name))

    def _init_toolbar(self):
        self.basedir = os.path.join(matplotlib.rcParams['datapath'], 'images')

        for text, tooltip_text, image_file, callback in self.toolitems:
            if text is None:
                self.addSeparator()
            else:
                a = self.addAction(self._icon(image_file + '.png'),
                                   text, getattr(self, callback))
                self._actions[callback] = a
                if callback in ['zoom', 'pan']:
                    a.setCheckable(True)
                if tooltip_text is not None:
                    a.setToolTip(tooltip_text)

        if figureoptions is not None:
            a = self.addAction(self._icon("qt5_editor_options.png"),
                               'Customize', self.edit_parameters)
            a.setToolTip('Edit curves line and axes parameters')

        self.buttons = {}

        # Add the x,y location widget at the right side of the toolbar
        # The stretch factor is 1 which means any resizing of the toolbar
        # will resize this label instead of the buttons.
        if self.coordinates:
            self.locLabel = QLabel("", self)
            self.locLabel.setAlignment(
                Qt.AlignRight | Qt.AlignTop)
            self.locLabel.setSizePolicy(
                QSizePolicy(QSizePolicy.Expanding,
                                      QSizePolicy.Ignored))
            labelAction = self.addWidget(self.locLabel)
            labelAction.setVisible(True)

        # reference holder for subplots_adjust window
        self.adj_window = None

    if figureoptions is not None:
        def edit_parameters(self):
            allaxes = self.canvas.figure.get_axes()
            if len(allaxes) == 1:
                axes = allaxes[0]
            else:
                titles = []
                for axes in allaxes:
                    title = axes.get_title()
                    ylabel = axes.get_ylabel()
                    if title:
                        fmt = "%(title)s"
                        if ylabel:
                            fmt += ": %(ylabel)s"
                        fmt += " (%(axes_repr)s)"
                    elif ylabel:
                        fmt = "%(axes_repr)s (%(ylabel)s)"
                    else:
                        fmt = "%(axes_repr)s"
                    titles.append(fmt % dict(title=title,
                                             ylabel=ylabel,
                                             axes_repr=repr(axes)))
                item, ok = QInputDialog.getItem(self, 'Customize',
                                                          'Select axes:',
                                                          titles,
                                                          0, False)
                if ok:
                    axes = allaxes[titles.index(str(item))]
                else:
                    return

            figureoptions.figure_edit(axes, self)

    def _update_buttons_checked(self):
        #sync button checkstates to match active mode
        self._actions['pan'].setChecked(self._active == 'PAN')
        self._actions['zoom'].setChecked(self._active == 'ZOOM')

    def pan(self, *args):
        super(NavigationToolbar2QT, self).pan(*args)
        self._update_buttons_checked()

    def zoom(self, *args):
        super(NavigationToolbar2QT, self).zoom(*args)
        self._update_buttons_checked()

    def dynamic_update(self):
        self.canvas.draw()

    def set_message(self, s):
        self.message.emit(s)
        if self.coordinates:
            self.locLabel.setText(s.replace(', ', '\n'))

    def set_cursor(self, cursor):
        if DEBUG:
            print('Set cursor', cursor)
        self.canvas.setCursor(cursord[cursor])

    def draw_rubberband(self, event, x0, y0, x1, y1):
        height = self.canvas.figure.bbox.height
        y1 = height - y1
        y0 = height - y0

        w = abs(x1 - x0)
        h = abs(y1 - y0)

        rect = [int(val)for val in (min(x0, x1), min(y0, y1), w, h)]
        self.canvas.drawRectangle(rect)

    def configure_subplots(self):
        self.adj_window = QMainWindow()
        win = self.adj_window

        win.setWindowTitle("Subplot Configuration Tool")
        image = os.path.join(matplotlib.rcParams['datapath'],
                             'images', 'matplotlib.png')
        win.setWindowIcon(QIcon(image))

        tool = SubplotToolQt(self.canvas.figure, win)
        win.setCentralWidget(tool)
        win.setSizePolicy(QSizePolicy.Preferred,
                          QSizePolicy.Preferred)

        win.show()

    def _get_canvas(self, fig):
        return FigureCanvasQT(fig)

    def save_figure(self, *args):
        filetypes = self.canvas.get_supported_filetypes_grouped()
        sorted_filetypes = list(filetypes.items())
        sorted_filetypes.sort()
        default_filetype = self.canvas.get_default_filetype()

        startpath = matplotlib.rcParams.get('savefig.directory', '')
        startpath = os.path.expanduser(startpath)
        start = os.path.join(startpath, self.canvas.get_default_filename())
        filters = []
        selectedFilter = None
        for name, exts in sorted_filetypes:
            exts_list = " ".join(['*.%s' % ext for ext in exts])
            filter = '%s (%s)' % (name, exts_list)
            if default_filetype in exts:
                selectedFilter = filter
            filters.append(filter)
        filters = ';;'.join(filters)
        fname = _getSaveFileName(self, "Choose a filename to save to",
                                 start, filters, selectedFilter)
        if fname:
            if startpath == '':
                # explicitly missing key or empty str signals to use cwd
                matplotlib.rcParams['savefig.directory'] = startpath
            else:
                # save dir for next time
                matplotlib.rcParams['savefig.directory'] = os.path.dirname(
                    str(fname))
            try:
                self.canvas.print_figure(str(fname))
            except Exception as e:
                QMessageBox.critical(
                    self, "Error saving file", str(e),
                    QMessageBox.Ok, QMessageBox.NoButton)


class SubplotToolQt(QWidget, SubplotTool):
    def __init__(self, targetfig, parent):
        QWidget.__init__(self, parent)

        self.targetfig = targetfig
        self.parent = parent

        self.sliderleft = QSlider(Qt.Horizontal)
        self.sliderbottom = QSlider(Qt.Vertical)
        self.sliderright = QSlider(Qt.Horizontal)
        self.slidertop = QSlider(Qt.Vertical)
        self.sliderwspace = QSlider(Qt.Horizontal)
        self.sliderhspace = QSlider(Qt.Vertical)

        # constraints
        self.sliderleft.valueChanged.connect(self.sliderright.setMinimum)
        self.sliderright.valueChanged.connect(self.sliderleft.setMaximum)
        self.sliderbottom.valueChanged.connect(self.slidertop.setMinimum)
        self.slidertop.valueChanged.connect(self.sliderbottom.setMaximum)

        sliders = (self.sliderleft, self.sliderbottom, self.sliderright,
                   self.slidertop, self.sliderwspace, self.sliderhspace, )
        adjustments = ('left:', 'bottom:', 'right:',
                       'top:', 'wspace:', 'hspace:')

        for slider, adjustment in zip(sliders, adjustments):
            slider.setMinimum(0)
            slider.setMaximum(1000)
            slider.setSingleStep(5)

        layout = QGridLayout()

        leftlabel = QLabel('left')
        layout.addWidget(leftlabel, 2, 0)
        layout.addWidget(self.sliderleft, 2, 1)

        toplabel = QLabel('top')
        layout.addWidget(toplabel, 0, 2)
        layout.addWidget(self.slidertop, 1, 2)
        layout.setAlignment(self.slidertop, Qt.AlignHCenter)

        bottomlabel = QLabel('bottom')  # this might not ever be used
        layout.addWidget(bottomlabel, 4, 2)
        layout.addWidget(self.sliderbottom, 3, 2)
        layout.setAlignment(self.sliderbottom, Qt.AlignHCenter)

        rightlabel = QLabel('right')
        layout.addWidget(rightlabel, 2, 4)
        layout.addWidget(self.sliderright, 2, 3)

        hspacelabel = QLabel('hspace')
        layout.addWidget(hspacelabel, 0, 6)
        layout.setAlignment(hspacelabel, Qt.AlignHCenter)
        layout.addWidget(self.sliderhspace, 1, 6)
        layout.setAlignment(self.sliderhspace, Qt.AlignHCenter)

        wspacelabel = QLabel('wspace')
        layout.addWidget(wspacelabel, 4, 6)
        layout.setAlignment(wspacelabel, Qt.AlignHCenter)
        layout.addWidget(self.sliderwspace, 3, 6)
        layout.setAlignment(self.sliderwspace, Qt.AlignBottom)

        layout.setRowStretch(1, 1)
        layout.setRowStretch(3, 1)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(3, 1)
        layout.setColumnStretch(6, 1)

        self.setLayout(layout)

        self.sliderleft.setSliderPosition(int(targetfig.subplotpars.left * 1000))
        self.sliderbottom.setSliderPosition(
            int(targetfig.subplotpars.bottom * 1000))
        self.sliderright.setSliderPosition(
            int(targetfig.subplotpars.right * 1000))
        self.slidertop.setSliderPosition(int(targetfig.subplotpars.top * 1000))
        self.sliderwspace.setSliderPosition(
            int(targetfig.subplotpars.wspace * 1000))
        self.sliderhspace.setSliderPosition(
            int(targetfig.subplotpars.hspace * 1000))

        self.sliderleft.valueChanged.connect(self.funcleft)
        self.sliderbottom.valueChanged.connect(self.funcbottom)
        self.sliderright.valueChanged.connect(self.funcright)
        self.slidertop.valueChanged.connect(self.functop)
        self.sliderwspace.valueChanged.connect(self.funcwspace)
        self.sliderhspace.valueChanged.connect(self.funchspace)

    def funcleft(self, val):
        if val == self.sliderright.value():
            val -= 1
        self.targetfig.subplots_adjust(left=val / 1000.)
        if self.drawon:
            self.targetfig.canvas.draw()

    def funcright(self, val):
        if val == self.sliderleft.value():
            val += 1
        self.targetfig.subplots_adjust(right=val / 1000.)
        if self.drawon:
            self.targetfig.canvas.draw()

    def funcbottom(self, val):
        if val == self.slidertop.value():
            val -= 1
        self.targetfig.subplots_adjust(bottom=val / 1000.)
        if self.drawon:
            self.targetfig.canvas.draw()

    def functop(self, val):
        if val == self.sliderbottom.value():
            val += 1
        self.targetfig.subplots_adjust(top=val / 1000.)
        if self.drawon:
            self.targetfig.canvas.draw()

    def funcwspace(self, val):
        self.targetfig.subplots_adjust(wspace=val / 1000.)
        if self.drawon:
            self.targetfig.canvas.draw()

    def funchspace(self, val):
        self.targetfig.subplots_adjust(hspace=val / 1000.)
        if self.drawon:
            self.targetfig.canvas.draw()


def error_msg_qt(msg, parent=None):
    if not is_string_like(msg):
        msg = ','.join(map(str, msg))

    QMessageBox.warning(None, "Matplotlib", msg,
                                  QMessageBox.Ok)


def exception_handler(type, value, tb):
    """Handle uncaught exceptions
    It does not catch SystemExit
    """
    msg = ''
    # get the filename attribute if available (for IOError)
    if hasattr(value, 'filename') and value.filename is not None:
        msg = value.filename + ': '
    if hasattr(value, 'strerror') and value.strerror is not None:
        msg += value.strerror
    else:
        msg += str(value)

    if len(msg):
        error_msg_qt(msg)

FigureManager = FigureManagerQT
