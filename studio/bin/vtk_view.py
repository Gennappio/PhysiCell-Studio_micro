"""
vtk_view.py - provides 3D visualization using VTK.

This module handles all VTK-related functionality for PhysiCell Studio,
creating a clean separation between the visualization interface and VTK rendering.
"""

import os
import vtk
from PyQt5 import QtCore
from pyMCDS_cells import pyMCDS_cells
from pathlib import Path
from PyQt5.QtWidgets import QMainWindow, QVBoxLayout, QWidget
from vtk.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

class PhysiCellVTKView:
    """A class to handle VTK visualization for PhysiCell output."""
    
    def __init__(self, output_dir, current_frame=0, cell_colors=None):
        """
        Initialize the VTK viewer.
        
        Args:
            output_dir (str): Directory containing the PhysiCell output files
            current_frame (int): The current frame to visualize
            cell_colors (list): List of RGB colors for cell types
        """
        self.output_dir = output_dir
        self.current_frame = current_frame
        self.cell_colors = cell_colors if cell_colors else []
        
        # VTK objects
        self.vtk_win = None
        self.renderer = None
        self.interactor = None
        self.update_timer = None
        
    def open_window(self):
        """Open a standalone VTK window for 3D visualization."""
        # Create Qt window to hold the VTK widget
        self.qt_window = QMainWindow()
        self.qt_window.setWindowTitle(f"PhysiCell VTK Viewer - Frame {self.current_frame}")
        self.qt_window.resize(800, 600)
        
        # Central widget and layout
        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        
        # Create QVTKRenderWindowInteractor widget
        self.vtk_widget = QVTKRenderWindowInteractor(central_widget)
        layout.addWidget(self.vtk_widget)
        
        # Set central widget
        self.qt_window.setCentralWidget(central_widget)
        
        # Get render window and interactor from widget
        self.vtk_win = self.vtk_widget.GetRenderWindow()
        self.interactor = self.vtk_widget  # Use the widget directly as the interactor
        
        # Create renderer
        self.renderer = vtk.vtkRenderer()
        self.vtk_win.AddRenderer(self.renderer)
        
        # Load and display the current frame data
        self.update_frame_data()
        
        # Add navigation help text
        help_text = vtk.vtkTextActor()
        help_text.SetInput("Left mouse: Rotate | Right mouse: Zoom | Middle mouse: Pan")
        help_text.GetTextProperty().SetFontSize(12)
        help_text.GetTextProperty().SetColor(1, 1, 1)  # White
        help_text.SetPosition(20, 560)
        self.renderer.AddActor2D(help_text)
        
        # Set background color
        self.renderer.SetBackground(0.1, 0.2, 0.3)  # Dark blue
        
        # Add axes
        self.add_orientation_axes()
        
        # Reset camera to show all objects
        self.renderer.ResetCamera()
        
        # Start interactor
        self.interactor.Initialize()
        
        # Set up a timer to check for frame updates
        from PyQt5.QtCore import QTimer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.check_for_frame_update)
        self.update_timer.start(500)  # Check every 500 ms
        
        # Show the Qt window (must be called on the main thread)
        self.qt_window.show()
        
        # Start the event loop
        self.vtk_widget.Start()
        
        # Set interactor style to trackball camera for smoother interaction
        interactor_style = vtk.vtkInteractorStyleTrackballCamera()
        self.interactor.SetInteractorStyle(interactor_style)
        
        # Adjust sphere resolution for performance
        sphere = vtk.vtkSphereSource()
        sphere.SetPhiResolution(8)
        sphere.SetThetaResolution(8)
    
    def update_frame_data(self):
        """Load and display data for the current frame."""
        # Clear previous actors
        self.renderer.RemoveAllViewProps()
        
        # Add frame info text at the top
        self.add_frame_info_text()
        
        try:
            # Try to load cell data from model output for the current frame
            xml_file_root = f"output{self.current_frame:08d}.xml"
            xml_file = os.path.join(self.output_dir, xml_file_root)
            
            if os.path.exists(xml_file):
                self.load_and_display_cells(xml_file_root)
            else:
                # Try loading from SVG file if XML is not available
                self.try_svg_fallback()
        except Exception as e:
            print(f"Error loading cell data: {e}")
            self.create_demo_sphere()
            self.add_error_text(str(e))
        
        # Add orientation axes (always keep these)
        self.add_orientation_axes()
        
        # Re-render
        if self.vtk_win:
            self.vtk_win.Render()
    
    def load_and_display_cells(self, xml_file_root):
        """Load cell data from XML file and display as spheres."""
        # Load cell data using pyMCDS
        mcds = pyMCDS_cells(xml_file_root, self.output_dir, microenv=False, graph=False, verbose=False)
        
        # Get cell positions and types from dataframe
        cell_df = mcds.get_cell_df()
        positions_x = cell_df['position_x'].values
        positions_y = cell_df['position_y'].values
        if 'position_z' in cell_df.columns:
            positions_z = cell_df['position_z'].values
        else:
            positions_z = np.zeros_like(positions_x)
        
        # Calculate cell radii
        cell_vols = cell_df['total_volume'].values
        four_thirds_pi = 4.188790204786391
        cell_radii = np.divide(cell_vols, four_thirds_pi)
        cell_radii = np.power(cell_radii, 0.333333333333333333333333333333333333333)
        
        # Get cell types for coloring
        cell_types = cell_df['cell_type'].values.astype(int)
        
        # Create points for cell centers
        points = vtk.vtkPoints()
        num_cells = len(positions_x)
        
        # Create arrays for colors and sizes
        colors = vtk.vtkUnsignedCharArray()
        colors.SetNumberOfComponents(3)
        colors.SetName("Colors")
        
        sizes = vtk.vtkFloatArray()
        sizes.SetNumberOfComponents(1)
        sizes.SetName("Sizes")
        
        # Add points and data
        for i in range(num_cells):
            points.InsertNextPoint(positions_x[i], positions_y[i], positions_z[i])
            
            # Set color based on cell type
            ct = cell_types[i]
            if ct < len(self.cell_colors):
                color = self.cell_colors[ct]
                r = int(color[0] * 255)
                g = int(color[1] * 255)
                b = int(color[2] * 255)
            else:
                r, g, b = 180, 180, 180  # Default light gray
            
            colors.InsertNextTuple3(r, g, b)
            sizes.InsertNextValue(cell_radii[i])
        
        # Create a polydata object
        polydata = vtk.vtkPolyData()
        polydata.SetPoints(points)
        
        # Add the color and size data to the points
        polydata.GetPointData().SetScalars(colors)
        polydata.GetPointData().AddArray(sizes)
        
        # Create the sphere source for glyphing
        sphere = vtk.vtkSphereSource()
        sphere.SetPhiResolution(8)
        sphere.SetThetaResolution(8)
        sphere.SetRadius(1.0)  # Will be scaled by the glyphing
        
        # Create the glyph
        glyph = vtk.vtkGlyph3D()
        glyph.SetSourceConnection(sphere.GetOutputPort())
        glyph.SetInputData(polydata)
        glyph.SetScaleModeToScaleByScalar()
        glyph.SetScaleFactor(1.0)
        glyph.SetColorModeToColorByScalar()
        glyph.SetInputArrayToProcess(0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS, "Sizes")
        glyph.SetInputArrayToProcess(1, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS, "Colors")
        
        # Create mapper and actor
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(glyph.GetOutputPort())
        
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        self.renderer.AddActor(actor)
        
        # Get the time information
        mins = mcds.get_time()
        hrs = int(mins/60)
        days = int(hrs/24)
        time_str = f"{days}d, {hrs-days*24}h, {int(mins-hrs*60)}m"
        
        # Add info text about XML file
        file_info = vtk.vtkTextActor()
        file_info.SetInput(f"FILE: {xml_file_root}")
        file_info.GetTextProperty().SetFontSize(16)
        file_info.GetTextProperty().SetColor(1, 1, 1)  # White text
        file_info.SetPosition(20, 60)
        self.renderer.AddActor2D(file_info)
        
        # Update the frame info text with cell count and time
        frame_info = vtk.vtkTextActor()
        frame_info.SetInput(f"PhysiCell Frame {self.current_frame} - {num_cells} cells - {time_str}")
        frame_info.GetTextProperty().SetFontSize(16)
        frame_info.GetTextProperty().SetColor(1, 1, 1)  # White text
        frame_info.SetPosition(20, 30)
        self.renderer.AddActor2D(frame_info)
        
        print(f"Loaded {num_cells} cells from frame {self.current_frame}")
    
    def try_svg_fallback(self):
        """Try to load from SVG file if XML is not available."""
        svg_file = f"snapshot{self.current_frame:08d}.svg"
        svg_path = os.path.join(self.output_dir, svg_file)
        
        if os.path.exists(svg_path):
            print(f"Found SVG file: {svg_path}")
            
            # Add text showing SVG file name
            file_info = vtk.vtkTextActor()
            file_info.SetInput(f"FILE: {svg_path}")
            file_info.GetTextProperty().SetFontSize(24)
            file_info.GetTextProperty().SetColor(1, 1, 0)  # Bright yellow
            file_info.SetPosition(100, 100)
            self.renderer.AddActor2D(file_info)
            
            # Add a message about XML vs SVG
            svg_info = vtk.vtkTextActor()
            svg_info.SetInput("SVG files contain limited position data. Full 3D visualization requires XML output.")
            svg_info.GetTextProperty().SetFontSize(16)
            svg_info.GetTextProperty().SetColor(1, 0.5, 0.5)  # Light red
            svg_info.SetPosition(20, 140)
            self.renderer.AddActor2D(svg_info)
            
            # Create a demo sphere 
            self.create_demo_sphere()
        else:
            # No data found
            frame_info = vtk.vtkTextActor()
            frame_info.SetInput(f"No cell data found for frame {self.current_frame}")
            frame_info.GetTextProperty().SetFontSize(24)
            frame_info.GetTextProperty().SetColor(1, 1, 0)  # Bright yellow
            frame_info.SetPosition(100, 100)
            self.renderer.AddActor2D(frame_info)
            
            self.create_demo_sphere()
    
    def create_demo_sphere(self):
        """Create a demo sphere for the VTK window when no data is available."""
        # Create a sphere
        sphere = vtk.vtkSphereSource()
        sphere.SetCenter(0, 0, 0)
        sphere.SetRadius(50)
        sphere.SetPhiResolution(30)
        sphere.SetThetaResolution(30)
        
        # Create mapper
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(sphere.GetOutputPort())
        
        # Create actor
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(1, 0, 0)  # Red
        
        # Add actor to renderer
        self.renderer.AddActor(actor)
    
    def add_orientation_axes(self):
        """Add orientation axes to the renderer."""
        axes = vtk.vtkAxesActor()
        axes.SetTotalLength(20, 20, 20)
        axes.GetXAxisCaptionActor2D().SetCaption("X")
        axes.GetYAxisCaptionActor2D().SetCaption("Y")
        axes.GetZAxisCaptionActor2D().SetCaption("Z")
        
        # Position the axes widget
        axes_widget = vtk.vtkOrientationMarkerWidget()
        axes_widget.SetOrientationMarker(axes)
        axes_widget.SetInteractor(self.interactor)
        axes_widget.SetViewport(0.0, 0.0, 0.2, 0.2)
        axes_widget.EnabledOn()
        axes_widget.InteractiveOff()
    
    def add_frame_info_text(self):
        """Add text showing current frame number."""
        frame_info = vtk.vtkTextActor()
        frame_info.SetInput(f"CURRENT FRAME: {self.current_frame}")
        frame_info.GetTextProperty().SetFontSize(24)
        frame_info.GetTextProperty().SetColor(1, 1, 0)  # Bright yellow
        frame_info.SetPosition(100, 30)
        self.renderer.AddActor2D(frame_info)
    
    def add_error_text(self, error_msg):
        """Add text showing error message."""
        error_text = vtk.vtkTextActor()
        error_text.SetInput(f"Error loading data: {error_msg}")
        error_text.GetTextProperty().SetFontSize(16)
        error_text.GetTextProperty().SetColor(1, 0.5, 0.5)  # Light red
        error_text.SetPosition(20, 100)
        self.renderer.AddActor2D(error_text)
    
    def set_current_frame(self, frame_num):
        """Set the current frame and update visualization."""
        if self.current_frame == frame_num:
            return
            
        self.current_frame = frame_num
        print(f"VTK viewer updating to frame {self.current_frame}")
        
        # Update window title
        if hasattr(self, 'qt_window'):
            self.qt_window.setWindowTitle(f"PhysiCell VTK Viewer - Frame {self.current_frame}")
        elif self.vtk_win:
            self.vtk_win.SetWindowName(f"PhysiCell VTK Viewer - Frame {self.current_frame}")
            
        # Update data display
        self.update_frame_data()
    
    def check_for_frame_update(self):
        """Check if the main application has requested a frame update."""
        # In a real-world implementation, this would check if the parent app
        # has signaled a frame change, but the actual update happens through
        # the set_current_frame method already
        pass
    
    def close(self):
        """Close the VTK window."""
        if self.update_timer:
            self.update_timer.stop()
        
        if self.interactor:
            self.interactor.TerminateApp()
            
        if hasattr(self, 'vtk_widget'):
            self.vtk_widget.close()
            
        if hasattr(self, 'qt_window'):
            self.qt_window.close()
            
        self.vtk_win = None
        self.renderer = None
        self.interactor = None
        

# Import numpy here to avoid circular imports
import numpy as np

# Optional: Implement a static method to share a VTK viewer instance
_vtk_viewer_instance = None

def get_vtk_viewer():
    """Get the current VTK viewer instance."""
    global _vtk_viewer_instance
    return _vtk_viewer_instance

def set_vtk_viewer(viewer):
    """Set the current VTK viewer instance."""
    global _vtk_viewer_instance
    _vtk_viewer_instance = viewer

def open_vtk_view(output_dir, current_frame, cell_colors=None):
    """
    Open a VTK window to visualize the PhysiCell model.
    
    Args:
        output_dir (str): Directory containing the PhysiCell output files
        current_frame (int): The current frame to visualize
        cell_colors (list): List of RGB colors for cell types
    
    Returns:
        PhysiCellVTKView: The VTK viewer object
    """
    viewer = PhysiCellVTKView(output_dir, current_frame, cell_colors)
    # Store the viewer instance so it can be accessed from other modules
    set_vtk_viewer(viewer)
    # Start the VTK window
    viewer.open_window()
    return viewer 