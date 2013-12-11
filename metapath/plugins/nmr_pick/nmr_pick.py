# -*- coding: utf-8 -*-
from __future__ import unicode_literals

# Import PyQt5 classes
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWebKit import *
from PyQt5.QtNetwork import *
from PyQt5.QtWidgets import *
from PyQt5.QtPrintSupport import *

import os, copy

from plugins import ProcessingPlugin

import numpy as np
import nmrglue as ng

import ui, db, utils, threads
from data import DataSet, DataDefinition



class NMRPeakPickingView( ui.DataView ):
    def __init__(self, plugin, parent, auto_consume_data=True, **kwargs):
        super(NMRPeakPickingView, self).__init__(plugin, parent, **kwargs)
        
        self.addDataToolBar()
        self.addFigureToolBar()
        
        self.data.add_input('input') # Add input slot        
        self.data.add_output('output')
        self.table.setModel(self.data.o['output'].as_table)
        
        
        # Setup data consumer options
        self.data.consumer_defs.append( 
            DataDefinition('input', {
            'labels_n':     ('>1', None),
            'entities_t':   (None, None), 
            'scales_t': (None, ['float']),
            })
        )
        
        
        self.config.set_defaults({
            'peak_threshold': 0.05,
            'peak_separation': 0.5,
            'peak_algorithm': 'Threshold',
        })
        
        th = self.addToolBar('Peak Picking')
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setDecimals(5)
        self.threshold_spin.setRange(0,1)
        self.threshold_spin.setSuffix('rel')
        self.threshold_spin.setSingleStep(0.005)
        tl = QLabel('Threshold')
        th.addWidget(tl)
        th.addWidget(self.threshold_spin)
        self.config.add_handler('peak_threshold', self.threshold_spin)

        self.separation_spin = QDoubleSpinBox()
        self.separation_spin.setDecimals(1)
        self.separation_spin.setRange(0,5)
        self.separation_spin.setSingleStep(0.5)
        tl = QLabel('Separation')
        tl.setIndent(5)
        th.addWidget(tl)
        th.addWidget(self.separation_spin)
        self.config.add_handler('peak_separation', self.separation_spin)

        self.algorithms = {
            'Connected':'connected',
            'Threshold':'thres',
            'Threshold (fast)':'thres-fast',
            'Downward':'downward',
        }

        self.algorithm_cb = QComboBox()
        self.algorithm_cb.addItems( [k for k,v in self.algorithms.items() ] )
        tl = QLabel('Algorithm')
        tl.setIndent(5)
        th.addWidget(tl)
        th.addWidget(self.algorithm_cb)  
        self.config.add_handler('algorithm', self.algorithm_cb)
              

        self.data.source_updated.connect( self.autogenerate ) # Auto-regenerate if the source data is modified        
        if auto_consume_data:
            self.data.consume_any_of( self.m.datasets[::-1] ) # Try consume any dataset; work backwards
        self.config.updated.connect( self.autogenerate ) # Regenerate if the configuration is changed

    
    def generate(self):
        self.worker = threads.Worker(self.picking, dsi=self.data.get('input'))
        self.start_worker_thread(self.worker)
        
    def generated(self, dso):
        self.data.put('output',dso)
        self.render({})


    def picking(self, dsi): #, config, algorithms):
        # Generate bin values for range start_scale to end_scale
        # Calculate the number of bins at binsize across range
        dso = DataSet( size=dsi.shape )
        dso.import_data(dsi)
        
        #ng.analysis.peakpick.pick(data, thres, msep=None, direction='both', algorithm='thres', est_params=True, lineshapes=None)
        
        threshold =  self.config.get('peak_threshold')
        algorithm = self.algorithms[ self.config.get('algorithm')]
        msep = ( self.config.get('peak_separation'),)
        
        # Take input dataset and flatten in first dimension (average spectra)
        data_avg = np.mean( dsi.data, axis=0)

        # pick peaks and return locations; 
        #nmrglue.analysis.peakpick.pick(data, pthres, nthres=None, msep=None, algorithm='connected', est_params=True, lineshapes=None, edge=None, diag=False, c_struc=None, c_ndil=0, cluster=True, table=True, axis_names=['A', 'Z', 'Y', 'X'])[source]¶
        locations, scales, amps = ng.analysis.peakpick.pick(data_avg, threshold, msep=msep, algorithm=algorithm, est_params = True, cluster=False, table=False)

        #n_cluster = max( cluster_ids )
        n_locations = len( locations )
        
        new_shape = list( dsi.shape )
        new_shape[1] = n_locations # correct number; tho will be zero indexed
        
        # Convert to numpy arrays so we can do clever things
        locations = np.array( [l[0] for l in locations ]) #wtf

        # Adjust the scales (so aren't lost in crop)
        dso.scales[1] = [ float(x) for x in np.array(dso.scales[1])[ locations ] ] # FIXME: The scale check on the plot is duff; doesn't recognise float64,etc.
        dso.labels[1] = [ str(x) for x in dso.scales[1] ] # FIXME: Label plotting on the scale plot
 
        dso.crop( new_shape )
    
        #cluster_ids = np.array( cluster_ids )

        # Iterate over the clusters (1 to n)
        for n, l in enumerate(locations):
            #l = locations[ cluster_ids == n ]
            peak_data = dsi.data[:, l]
            #peak_data = np.amax( peak_data, axis=1 ) # max across cols
            dso.data[:,n-1] = peak_data
            
            #print dsi.data[ :, l ] 
            
        # Extract the location numbers (positions in original spectra)
        # Get max value in each row for those regions
        # Append that to n position in new dataset
        
        # -- optionally use the line widths and take max within each of these for each spectra (peak shiftiness)
        # Filter the original data with those locations and output\

        return {'dso':dso}

 
class NMRPeakPicking(ProcessingPlugin):

    def __init__(self, **kwargs):
        super(NMRPeakPicking, self).__init__(**kwargs)
        self.register_app_launcher( self.app_launcher )

    def app_launcher(self, **kwargs):
        return NMRPeakPickingView( self, self.m, **kwargs )