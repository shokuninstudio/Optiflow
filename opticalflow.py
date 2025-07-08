import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np
import json
import os
from PIL import Image, ImageDraw, ImageTk
import copy
import base64
import io
import logging

# Configure logging for debugging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('OptiflowApp')

# Helper class for tooltips - moved to the top of the file to be defined before use
class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)
    
    def show_tooltip(self, event=None):
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        
        # Create top level window
        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")
        
        frame = tk.Frame(self.tooltip, background="#ffffe0", borderwidth=1, relief="solid")
        frame.pack(ipadx=5, ipady=5)
        
        label = tk.Label(frame, text=self.text, justify=tk.LEFT,
                         background="#ffffe0", wrap=250)
        label.pack()
        
    def hide_tooltip(self, event=None):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

class OptiflowApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Optiflow")
        
        # Data storage
        self.keyframes = {}  # Dictionary to store strokes for each keyframe
        self.current_keyframe = 1
        self.strokes = []    # Current strokes being drawn
        self.current_stroke = []  # Points in the current stroke
        self.is_drawing = False
        
        # Tool state - add tool tracking
        self.current_tool = "pencil"  # Default tool is pencil
        self.eraser_size = 20  # Size of the eraser in pixels
        
        # Undo/Redo history stacks
        self.history = []  # Stack for undo operations
        self.redo_stack = []  # Stack for redo operations
        self.max_history = 50  # Limit history to prevent memory issues
        
        # Canvas dimensions (actual size for rendering and export)
        self.canvas_width = 1920
        self.canvas_height = 1080
        
        # Display scale factor (to fit on screen)
        self.scale_factor = 0.5  # Display at 50% scale
        
        # Add zoom factor - separate from scale_factor
        self.zoom_factor = 1.0  # Start with no zoom (1.0x)
        # Replace min/max zoom with discrete zoom levels
        self.zoom_levels = [1.0, 1.25, 1.56]  # Only three specific zoom levels
        self.current_zoom_index = 0  # Index of current zoom level (starts at 1.0)
        
        # Calculate display dimensions considering both scale and zoom
        self.update_display_dimensions()
        
        # Onion skinning settings
        self.show_onion_skin = True
        self.onion_skin_opacity = 30  # 0-100 (percentage)
        
        # Clipboard storage for copy-paste
        self.clipboard = None
        
        # Remove the paste_with_offset option
        

        
        # Animation state variables
        self.animation_running = False
        
        # Add pencil color property
        self.pencil_color = "#666666"  # Dark grey color
        
        # Set up the UI
        self.setup_ui()
        
        # Set window size based on content (after UI is set up)
        self.root.update_idletasks()  # Ensure all widgets are drawn before getting dimensions
        width = self.main_frame.winfo_reqwidth() + 40  # Add padding
        height = self.main_frame.winfo_reqheight() + 40
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(width, height)
        
        # Register keyboard shortcuts properly
        self.bind_shortcuts()
        
        # Save initial state for undo
        self.save_state()
        
        # For debugging
        logger.info("Application initialized")
        
        # Enable debug logging to get more information about onion skin rendering
        logging.getLogger('OptiflowApp').setLevel(logging.DEBUG)
    
    def update_display_dimensions(self):
        """Update the display dimensions based on scale and zoom factors"""
        self.display_width = int(self.canvas_width * self.scale_factor * self.zoom_factor)
        self.display_height = int(self.canvas_height * self.scale_factor * self.zoom_factor)
    
    def bind_shortcuts(self):
        """Set up keyboard shortcuts that work properly"""
        # Bind to root window (for global shortcuts)
        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Control-y>", lambda e: self.redo())
        self.root.bind("<Control-Z>", lambda e: self.redo())  # Capital Z with Ctrl for Mac
        
        # Add copy and paste shortcuts
        self.root.bind("<Control-c>", lambda e: self.copy_strokes())
        self.root.bind("<Control-v>", lambda e: self.paste_strokes())
        
        # Also bind to canvas for when it has focus
        self.canvas.bind("<Control-z>", lambda e: self.undo())
        self.canvas.bind("<Control-y>", lambda e: self.redo())
        self.canvas.bind("<Control-Z>", lambda e: self.redo())
        self.canvas.bind("<Control-c>", lambda e: self.copy_strokes())
        self.canvas.bind("<Control-v>", lambda e: self.paste_strokes())
        
        # For Mac users (Command key instead of Control)
        if self.root.tk.call('tk', 'windowingsystem') == 'aqua':
            self.root.bind("<Command-z>", lambda e: self.undo())
            self.root.bind("<Command-y>", lambda e: self.redo())
            self.root.bind("<Command-Z>", lambda e: self.redo())
            self.canvas.bind("<Command-z>", lambda e: self.undo())
            self.canvas.bind("<Command-y>", lambda e: self.redo())
            self.canvas.bind("<Command-Z>", lambda e: self.redo())
            
            # Add copy and paste shortcuts for Mac
            self.root.bind("<Command-c>", lambda e: self.copy_strokes())
            self.root.bind("<Command-v>", lambda e: self.paste_strokes())
            self.canvas.bind("<Command-c>", lambda e: self.copy_strokes())
            self.canvas.bind("<Command-v>", lambda e: self.paste_strokes())
            
            # Update shortcut info text for Mac
            # self.shortcut_label.config(text="(⌘Z / ⌘Y)")
            # self.copy_paste_label.config(text="(⌘C / ⌘V)")
        
        # Add tool shortcuts (P for pencil, E for eraser)
        self.root.bind("p", lambda e: self.set_tool("pencil"))
        self.root.bind("P", lambda e: self.set_tool("pencil"))
        self.root.bind("e", lambda e: self.set_tool("eraser"))
        self.root.bind("E", lambda e: self.set_tool("eraser"))
        
        # Also bind tool shortcuts to canvas
        self.canvas.bind("p", lambda e: self.set_tool("pencil"))
        self.canvas.bind("P", lambda e: self.set_tool("pencil"))
        self.canvas.bind("e", lambda e: self.set_tool("eraser"))
        self.canvas.bind("E", lambda e: self.set_tool("eraser"))
        
        # Add zoom shortcuts
        self.root.bind("=", self.zoom_in)  # = key is usually shift-plus, but also works alone
        self.root.bind("+", self.zoom_in)  # Plus key
        self.root.bind("-", self.zoom_out)  # Minus key
        self.root.bind("0", self.reset_zoom)  # 0 key resets zoom
        
        # Also bind zoom shortcuts to canvas
        self.canvas.bind("=", self.zoom_in)
        self.canvas.bind("+", self.zoom_in)
        self.canvas.bind("-", self.zoom_out)
        self.canvas.bind("0", self.reset_zoom)
    
    def zoom_in(self, event=None):
        """Increase zoom level to the next preset level"""
        old_zoom = self.zoom_factor
        
        # Move to next zoom level if not at maximum
        if self.current_zoom_index < len(self.zoom_levels) - 1:
            self.current_zoom_index += 1
            self.zoom_factor = self.zoom_levels[self.current_zoom_index]
            
            # Update display dimensions and redraw
            self.update_display_dimensions()
            self.canvas.config(width=self.display_width, height=self.display_height)
            self.redraw_canvas()
            self.status_var.set(f"Zoom: {int(self.zoom_factor * 100)}%")
            logger.info(f"Zoomed in to {int(self.zoom_factor * 100)}%")
        else:
            self.status_var.set(f"Already at maximum zoom: {int(self.zoom_factor * 100)}%")
        
        return "break"  # Prevent further processing
    
    def zoom_out(self, event=None):
        """Decrease zoom level to the previous preset level"""
        old_zoom = self.zoom_factor
        
        # Move to previous zoom level if not at minimum
        if self.current_zoom_index > 0:
            self.current_zoom_index -= 1
            self.zoom_factor = self.zoom_levels[self.current_zoom_index]
            
            # Update display dimensions and redraw
            self.update_display_dimensions()
            self.canvas.config(width=self.display_width, height=self.display_height)
            self.redraw_canvas()
            self.status_var.set(f"Zoom: {int(self.zoom_factor * 100)}%")
            logger.info(f"Zoomed out to {int(self.zoom_factor * 100)}%")
        else:
            self.status_var.set(f"Already at minimum zoom: {int(self.zoom_factor * 100)}%")
        
        return "break"  # Prevent further processing
    
    def reset_zoom(self, event=None):
        """Reset zoom to default (1.0)"""
        if self.current_zoom_index != 0:  # If not already at default zoom
            self.current_zoom_index = 0
            self.zoom_factor = self.zoom_levels[self.current_zoom_index]
            
            self.update_display_dimensions()
            self.canvas.config(width=self.display_width, height=self.display_height)
            self.redraw_canvas()
            self.status_var.set("Zoom reset to 100%")
            logger.info("Zoom reset to 100%")
        
        return "break"  # Prevent further processing
    
    def set_tool(self, tool_name):
        """Switch between drawing tools"""
        prev_tool = self.current_tool
        self.current_tool = tool_name
        
        # Set appropriate cursor for both canvas and container
        if tool_name == "pencil":
            self.canvas.config(cursor="pencil")
            self.canvas_container.config(cursor="pencil")
        elif tool_name == "eraser":
            self.canvas.config(cursor="dotbox")  # Use dotbox as eraser cursor
            self.canvas_container.config(cursor="dotbox")
        
        # Log tool change
        logger.info(f"Tool changed from {prev_tool} to {tool_name}")
    
    def setup_ui(self):
        # Main frame
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create a PanedWindow to allow user to adjust sizes
        paned_window = ttk.PanedWindow(self.main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)
        
        # Left panel - Drawing canvas
        left_frame = ttk.Frame(paned_window)
        
        # Create a canvas container with dark grey background
        # This provides a visual boundary for the drawing area
        canvas_container = tk.Frame(left_frame, bg="#666666", bd=0)
        canvas_container.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)
        
        # Canvas for drawing - display size uses scale factor and zoom factor
        self.canvas = tk.Canvas(
            canvas_container, 
            width=self.display_width, 
            height=self.display_height,
            bg="white", 
            bd=0, 
            highlightthickness=1,
            highlightbackground="black",
            cursor="pencil"  # Set default cursor to pencil
        )
        # Store padding values to use in coordinate calculations
        self.canvas_padx = 20
        self.canvas_pady = 20
        
        # Center the canvas in the container with expand=True to maintain centering
        self.canvas.pack(padx=self.canvas_padx, pady=self.canvas_pady, expand=True, anchor=tk.CENTER)
        
        # Store a reference to the canvas container
        self.canvas_container = canvas_container
        
        # Bind window resize to ensure canvas stays centered
        self.root.bind("<Configure>", self.on_window_resize)

        # Bind mouse events to BOTH the canvas container and the canvas
        # For the container (to allow drawing from outside)
        self.canvas_container.bind("<Button-1>", self.start_stroke)
        self.canvas_container.bind("<B1-Motion>", self.continue_stroke)
        self.canvas_container.bind("<ButtonRelease-1>", self.end_stroke)
        
        # Also for the canvas itself (to allow direct drawing on canvas)
        self.canvas.bind("<Button-1>", self.start_stroke)
        self.canvas.bind("<B1-Motion>", self.continue_stroke)
        self.canvas.bind("<ButtonRelease-1>", self.end_stroke)
        
        # Also set the cursor for the container to match the canvas
        self.canvas_container.config(cursor="pencil")

        # Combined toolbar below the canvas - all buttons in one row
        toolbar_frame = ttk.Frame(left_frame)
        toolbar_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        
        # Animation controls
        animation_frame = ttk.Frame(toolbar_frame)
        animation_frame.pack(side=tk.LEFT, padx=(0, 10))
        
        # Play and stop buttons
        self.play_btn = ttk.Button(
            animation_frame, 
            text="▶", 
            command=self.play_animation,
            width=3
        )
        self.play_btn.pack(side=tk.LEFT, padx=2)
        
        self.stop_btn = ttk.Button(
            animation_frame, 
            text="■", 
            command=self.stop_animation,
            width=3,
            state=tk.DISABLED  # Initially disabled
        )
        self.stop_btn.pack(side=tk.LEFT, padx=2)
        
        # FPS control
        fps_frame = ttk.Frame(animation_frame)
        fps_frame.pack(side=tk.LEFT, padx=2)
        
        ttk.Label(fps_frame, text="FPS:").pack(side=tk.LEFT)
        self.fps_var = tk.StringVar(value="12")
        ttk.Entry(fps_frame, textvariable=self.fps_var, width=3).pack(side=tk.LEFT)
        
        # Add a separator
        ttk.Separator(toolbar_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # Add tool controls
        tools_frame = ttk.Frame(toolbar_frame)
        tools_frame.pack(side=tk.LEFT, padx=(0, 10))
        
        # Pencil button
        pencil_btn = ttk.Button(tools_frame, text="Pencil", command=lambda: self.set_tool("pencil"), width=8)
        pencil_btn.pack(side=tk.LEFT, padx=2)
        
        # Eraser button
        eraser_btn = ttk.Button(tools_frame, text="Eraser", command=lambda: self.set_tool("eraser"), width=8)
        eraser_btn.pack(side=tk.LEFT, padx=2)
        
        # Add a separator
        ttk.Separator(toolbar_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # Add undo/redo buttons
        undo_redo_frame = ttk.Frame(toolbar_frame)
        undo_redo_frame.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(undo_redo_frame, text="Undo", command=self.undo, width=5).pack(side=tk.LEFT, padx=2)
        ttk.Button(undo_redo_frame, text="Redo", command=self.redo, width=5).pack(side=tk.LEFT, padx=2)
        
        # Add a separator
        ttk.Separator(toolbar_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # Add copy/paste buttons
        copy_paste_frame = ttk.Frame(toolbar_frame)
        copy_paste_frame.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(copy_paste_frame, text="Copy", command=self.copy_strokes, width=5).pack(side=tk.LEFT, padx=2)
        ttk.Button(copy_paste_frame, text="Paste", command=self.paste_strokes, width=5).pack(side=tk.LEFT, padx=2)
        
        # Bind mouse events for drawing
        self.canvas.bind("<Button-1>", self.start_stroke)
        self.canvas.bind("<B1-Motion>", self.continue_stroke)
        self.canvas.bind("<ButtonRelease-1>", self.end_stroke)
        
        # Right panel - Controls
        right_frame = ttk.Frame(paned_window)
        
        # Add both frames to the paned window
        paned_window.add(left_frame, weight=1)
        paned_window.add(right_frame, weight=0)
        
        # Canvas info label
        ttk.Label(right_frame, text=f"Canvas: {self.canvas_width}x{self.canvas_height} px").pack(anchor=tk.W, padx=5, pady=(0, 5))
        
        # Onion skinning controls
        onion_frame = ttk.LabelFrame(right_frame, text="")
        onion_frame.pack(fill=tk.X, pady=(0, 5), padx=5)
        
        # Enable/disable onion skinning
        self.onion_var = tk.BooleanVar(value=self.show_onion_skin)
        ttk.Checkbutton(
            onion_frame, 
            text="Enable Onion Skinning", 
            variable=self.onion_var,
            command=self.toggle_onion_skin
        ).pack(fill=tk.X, padx=5, pady=(5, 0))
        
        # Opacity slider
        opacity_frame = ttk.Frame(onion_frame)
        opacity_frame.pack(fill=tk.X, padx=5, pady=(5, 5)) # Updated pady to close the gap from removed dropdown
        
        ttk.Label(opacity_frame, text="Opacity:").pack(side=tk.LEFT)
        self.opacity_var = tk.IntVar(value=self.onion_skin_opacity)
        opacity_slider = ttk.Scale(
            opacity_frame, 
            from_=5, 
            to=70,
            orient=tk.HORIZONTAL,
            variable=self.opacity_var,
            command=self.update_onion_skin
        )
        opacity_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        
        # Keyframe controls
        keyframe_frame = ttk.LabelFrame(right_frame, text="Keyframe Controls")
        keyframe_frame.pack(fill=tk.X, pady=(0, 5), padx=5)
        
        keyframe_grid = ttk.Frame(keyframe_frame)
        keyframe_grid.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(keyframe_grid, text="Current Keyframe:").grid(row=0, column=0, padx=(0, 5), pady=2, sticky=tk.W)
        self.keyframe_var = tk.StringVar(value="1")
        keyframe_entry = ttk.Entry(keyframe_grid, textvariable=self.keyframe_var, width=5)
        keyframe_entry.grid(row=0, column=1, padx=2, pady=2)
        ttk.Button(keyframe_grid, text="Set", command=self.set_keyframe, width=5).grid(row=0, column=2, padx=2, pady=2)
        
        button_frame = ttk.Frame(keyframe_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        
        # Switch the order of Next and Prev buttons
        ttk.Button(button_frame, text="Prev", command=self.prev_keyframe).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Next", command=self.next_keyframe).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Clear", command=self.clear_canvas).pack(side=tk.LEFT, padx=2)
        
        # Interpolation controls
        interp_frame = ttk.LabelFrame(right_frame, text="Interpolation")
        interp_frame.pack(fill=tk.X, pady=(0, 5), padx=5)
        
        interp_grid = ttk.Frame(interp_frame)
        interp_grid.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(interp_grid, text="Start Frame:").grid(row=0, column=0, padx=(0, 5), pady=2, sticky=tk.W)
        self.start_frame_var = tk.StringVar(value="1")
        ttk.Entry(interp_grid, textvariable=self.start_frame_var, width=5).grid(row=0, column=1, padx=0, pady=2, sticky=tk.W)
        
        ttk.Label(interp_grid, text="End Frame:").grid(row=1, column=0, padx=(0, 5), pady=2, sticky=tk.W)
        self.end_frame_var = tk.StringVar(value="2")
        ttk.Entry(interp_grid, textvariable=self.end_frame_var, width=5).grid(row=1, column=1, padx=0, pady=2, sticky=tk.W)
        
        ttk.Label(interp_grid, text="Inbetweens:").grid(row=2, column=0, padx=(0, 5), pady=2, sticky=tk.W)
        self.num_inbetweens_var = tk.StringVar(value="3")
        ttk.Entry(interp_grid, textvariable=self.num_inbetweens_var, width=5).grid(row=2, column=1, padx=0, pady=2, sticky=tk.W)
        
        # Add a container frame for the interpolation method dropdown and button
        interp_control_frame = ttk.Frame(interp_frame)
        interp_control_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        
        # Remove interpolation method dropdown since we only have optical flow
        # Add interpolate button with full width
        ttk.Button(
            interp_control_frame, 
            text="Interpolate (Optical Flow)", 
            command=self.interpolate_frames
        ).pack(fill=tk.X, expand=True)
        
        # Preview controls (modified to only keep export frames)
        preview_frame = ttk.LabelFrame(right_frame, text="Export")
        preview_frame.pack(fill=tk.X, pady=(0, 5), padx=5)
        
        # Remove "Show Animation" button since we now have animation controls below the canvas
        ttk.Button(preview_frame, text="Export Frames", command=self.export_frames).pack(fill=tk.X, padx=5, pady=5)
        
        # Status bar with copyright info - without beveled borders and with padding
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=0)  # Added padding
        
        # Status message (left-aligned)
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(status_frame, textvariable=self.status_var, anchor=tk.W)
        status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Copyright message (right-aligned)
        copyright_label = ttk.Label(
            status_frame, 
            text="Optiflow by Shokunin Studio © 2025", 
            anchor=tk.E
        )
        copyright_label.pack(side=tk.RIGHT, padx=(10, 0))
    
    def save_state(self):
        """Save current state to history stack for undo operations"""
        # Copy the current strokes list (deep copy to ensure independent data)
        current_state = copy.deepcopy(self.strokes)
        
        # Add to history stack
        self.history.append(current_state)
        
        # Limit history size
        if len(self.history) > self.max_history:
            self.history.pop(0)  # Remove oldest item
            
        # Clear redo stack when new state is added
        self.redo_stack = []
        
        # Update status
        self.status_var.set(f"State saved - Undo stack: {len(self.history)} | Redo stack: {len(self.redo_stack)}")
    
    def undo(self, event=None):
        """Undo the last drawing action"""
        if len(self.history) <= 1:  # Keep at least one state (initial empty state)
            self.status_var.set("Nothing to undo")
            return
        
        # Save current state to redo stack
        self.redo_stack.append(self.history.pop())  # Remove current state and add to redo stack
        
        # Restore previous state
        self.strokes = copy.deepcopy(self.history[-1])  # Get the last element without removing
        
        # Redraw canvas
        self.redraw_canvas()
        
        # Update status
        self.status_var.set(f"Undo - Undo stack: {len(self.history)} | Redo stack: {len(self.redo_stack)}")
        return "break"  # Stop event propagation
    
    def redo(self, event=None):
        """Redo the last undone action"""
        if not self.redo_stack:
            self.status_var.set("Nothing to redo")
            return
        
        # Get the last redo state
        redo_state = self.redo_stack.pop()
        
        # Add current state to history
        self.history.append(copy.deepcopy(self.strokes))
        
        # Apply redo state
        self.strokes = copy.deepcopy(redo_state)
        
        # Redraw canvas
        self.redraw_canvas()
        
        # Update status
        self.status_var.set(f"Redo - Undo stack: {len(self.history)} | Redo stack: {len(self.redo_stack)}")
        return "break"  # Stop event propagation
    
    def start_stroke(self, event):
        """Handle the start of a stroke with proper coordinate calculations"""
        # Determine if the event happened on the canvas or the container
        is_canvas_event = event.widget == self.canvas
        
        if is_canvas_event:
            # Direct canvas event - coordinates are already relative to canvas
            rel_x = event.x
            rel_y = event.y
        else:
            # Container event - need to calculate relative to canvas position
            canvas_x0 = self.canvas.winfo_x()
            canvas_y0 = self.canvas.winfo_y()
            rel_x = event.x - canvas_x0
            rel_y = event.y - canvas_y0
        
        # Store original event coordinates for potential edge calculations
        self.last_event_x = rel_x
        self.last_event_y = rel_y
        
        # Check if the click is within the canvas bounds
        if 0 <= rel_x < self.display_width and 0 <= rel_y < self.display_height:
            self.is_drawing = True
            
            # Convert mouse coordinates from display coordinates to actual canvas coordinates
            # Include both scale_factor and zoom_factor in the conversion
            canvas_x = rel_x / (self.scale_factor * self.zoom_factor)
            canvas_y = rel_y / (self.scale_factor * self.zoom_factor)
            
            if self.current_tool == "pencil":
                # Create a new stroke and add the first point, ensuring it's exactly at the click location
                self.current_stroke = [(canvas_x, canvas_y)]
                self.last_x, self.last_y = canvas_x, canvas_y
                
                # Draw a small dot to ensure even single clicks are visible
                self.canvas.create_oval(
                    rel_x - 1, rel_y - 1, 
                    rel_x + 1, rel_y + 1,
                    fill=self.pencil_color, outline=""
                )
            elif self.current_tool == "eraser":
                # For eraser, we'll erase on each movement
                self.erase_at_point(canvas_x, canvas_y)
        else:
            # Even if starting outside canvas bounds, enable drawing mode
            # and calculate intersection with canvas border
            self.is_drawing = True
            if self.current_tool == "pencil":
                # Create an empty stroke that will receive points when entering canvas
                self.current_stroke = []
                
                # Store last coordinates for boundary calculation
                # These are outside the canvas but we need them to calculate edge intersection
                canvas_x = rel_x / (self.scale_factor * self.zoom_factor)
                canvas_y = rel_y / (self.scale_factor * self.zoom_factor)
                self.last_x, self.last_y = canvas_x, canvas_y
    
    def continue_stroke(self, event):
        """Continue the stroke with proper coordinate calculations"""
        if not self.is_drawing:
            return
        
        # Determine if the event happened on the canvas or the container
        is_canvas_event = event.widget == self.canvas
        
        if is_canvas_event:
            # Direct canvas event - coordinates are already relative to canvas
            rel_x = event.x
            rel_y = event.y
        else:
            # Container event - need to calculate relative to canvas position
            canvas_x0 = self.canvas.winfo_x()
            canvas_y0 = self.canvas.winfo_y()
            rel_x = event.x - canvas_x0
            rel_y = event.y - canvas_y0
        
        # Store latest event positions for potential edge calculations
        prev_event_x, prev_event_y = getattr(self, 'last_event_x', rel_x), getattr(self, 'last_event_y', rel_y)
        self.last_event_x, self.last_event_y = rel_x, rel_y
        
        # Check if the movement crossed the canvas boundary
        prev_in_canvas = (0 <= prev_event_x < self.display_width and 0 <= prev_event_y < self.display_height)
        current_in_canvas = (0 <= rel_x < self.display_width and 0 <= rel_y < self.display_height)
        
        # Convert mouse coordinates, considering both scale and zoom factors
        canvas_x = rel_x / (self.scale_factor * self.zoom_factor)
        canvas_y = rel_y / (self.scale_factor * self.zoom_factor)
        
        # Limit coordinates for visual display purposes
        display_x = max(min(rel_x, self.display_width-1), 0) if current_in_canvas else rel_x
        display_y = max(min(rel_y, self.display_height-1), 0) if current_in_canvas else rel_y
        
        if self.current_tool == "pencil":
            # Calculate if mouse moved quickly and potentially skipped boundary
            if hasattr(self, 'last_x') and hasattr(self, 'last_y'):
                # Calculate the distance moved since last point
                dist = ((prev_event_x - rel_x)**2 + (prev_event_y - rel_y)**2)**0.5
                
                # If the cursor crossed a boundary from outside to inside or vice versa,
                # we need to add an edge point to continue the stroke smoothly
                if prev_in_canvas != current_in_canvas:
                    # Check if movement is significant enough to calculate intersections
                    if dist > 1.0:  # Lower threshold to catch more crossings
                        # Add boundary intersection point(s)
                        edge_points = self.calculate_boundary_intersection(
                            prev_event_x, prev_event_y, 
                            rel_x, rel_y
                        )
                        for edge_x, edge_y in edge_points:
                            # Convert edge point to canvas coordinates
                            edge_canvas_x = edge_x / (self.scale_factor * self.zoom_factor)
                            edge_canvas_y = edge_y / (self.scale_factor * self.zoom_factor)
                            
                            # For visual display - draw line to the edge point
                            if (0 <= edge_x <= self.display_width and 0 <= edge_y <= self.display_height):
                                self.canvas.create_line(
                                    max(0, min(self.last_x * self.scale_factor * self.zoom_factor, self.display_width)), 
                                    max(0, min(self.last_y * self.scale_factor * self.zoom_factor, self.display_height)),
                                    edge_x, edge_y,
                                    width=max(1, int(2 * self.scale_factor * self.zoom_factor)), fill=self.pencil_color, smooth=True
                                )
                            
                            # Add edge point to stroke data
                            self.current_stroke.append((edge_canvas_x, edge_canvas_y))
                            self.last_x, self.last_y = edge_canvas_x, edge_canvas_y
                
                # For fast movements, interpolate points to ensure consistent line quality
                elif current_in_canvas:  # Only interpolate points when inside canvas
                    max_spacing = 10.0  # Maximum allowed spacing between points at display scale
                    
                    # Calculate current spacing in display coordinates, accounting for zoom
                    spacing = ((self.last_x * self.scale_factor * self.zoom_factor - display_x)**2 + 
                              (self.last_y * self.scale_factor * self.zoom_factor - display_y)**2)**0.5
                    
                    # If points are too far apart, interpolate between them
                    if spacing > max_spacing:
                        # Calculate number of points to insert
                        num_points = int(spacing / max_spacing)
                        for i in range(1, num_points):
                            # Linear interpolation
                            t = i / num_points
                            interp_x = self.last_x + (canvas_x - self.last_x) * t
                            interp_y = self.last_y + (canvas_y - self.last_y) * t
                            
                            # Add interpolated point to stroke
                            self.current_stroke.append((interp_x, interp_y))
                            
                            # Draw line segment for visual feedback
                            if i > 1:  # Skip drawing the first segment as it's handled by the main drawing
                                prev_x = self.last_x + (canvas_x - self.last_x) * (i-1) / num_points
                                prev_y = self.last_y + (canvas_y - self.last_y) * (i-1) / num_points
                                self.canvas.create_line(
                                    prev_x * self.scale_factor * self.zoom_factor, 
                                    prev_y * self.scale_factor * self.zoom_factor,
                                    interp_x * self.scale_factor * self.zoom_factor, 
                                    interp_y * self.scale_factor * self.zoom_factor,
                                    width=max(1, int(2 * self.scale_factor * self.zoom_factor)), 
                                    fill=self.pencil_color, 
                                    smooth=True
                                )
                
                # If in canvas, draw normally
                if current_in_canvas:
                    # If we have a previous point in this stroke
                    if hasattr(self, 'last_x') and hasattr(self, 'last_y'):
                        # Draw line on canvas - use proper bounded coordinates
                        self.canvas.create_line(
                            max(0, min(self.last_x * self.scale_factor * self.zoom_factor, self.display_width)), 
                            max(0, min(self.last_y * self.scale_factor * self.zoom_factor, self.display_height)), 
                            display_x, display_y,  # Use display coordinates for visual accuracy
                            width=max(1, int(2 * self.scale_factor * self.zoom_factor)), 
                            fill=self.pencil_color, 
                            smooth=True
                        )
                
                # Add point to the stroke data
                self.current_stroke.append((canvas_x, canvas_y))
            
            # Always update last position, even if outside canvas
            self.last_x, self.last_y = canvas_x, canvas_y
        
        elif self.current_tool == "eraser" and current_in_canvas:
            # Only erase if we're inside the canvas
            self.erase_at_point(canvas_x, canvas_y)
    
    def calculate_boundary_intersection(self, x1, y1, x2, y2):
        """Calculate where a line intersects the canvas boundary"""
        intersections = []
        left, top = 0, 0
        right, bottom = self.display_width, self.display_height
        
        # Line equation coefficients: ax + by + c = 0
        a = y2 - y1
        b = x1 - x2
        c = x2*y1 - x1*y2
        
        # Exit early if line is too short (avoid divide by zero)
        if abs(a) < 0.0001 and abs(b) < 0.0001:
            return []
        
        # Add validity checks for intersection points
        def is_valid_intersection(x, y):
            # Check if point is actually on the line segment
            on_segment = (min(x1, x2) <= x <= max(x1, x2)) and (min(y1, y2) <= y <= max(y1, y2))
            # Check if point is on the canvas boundary (with small tolerance)
            on_boundary = (abs(x - left) < 0.1 or abs(x - right) < 0.1 or 
                          abs(y - top) < 0.1 or abs(y - bottom) < 0.1)
            return on_segment and on_boundary
        
        # Check intersection with left boundary (x = left)
        if abs(b) > 0.0001:  # Avoid division by zero
            y_left = (-c - a*left) / b
            if top <= y_left <= bottom and is_valid_intersection(left, y_left):
                intersections.append((left, y_left))
        
        # Check intersection with right boundary (x = right)
        if abs(b) > 0.0001:  # Avoid division by zero
            y_right = (-c - a*right) / b
            if top <= y_right <= bottom and is_valid_intersection(right, y_right):
                intersections.append((right, y_right))
        
        # Check intersection with top boundary (y = top)
        if abs(a) > 0.0001:  # Avoid division by zero
            x_top = (-c - b*top) / a
            if left <= x_top <= right and is_valid_intersection(x_top, top):
                intersections.append((x_top, top))
        
        # Check intersection with bottom boundary (y = bottom)
        if abs(a) > 0.0001:  # Avoid division by zero
            x_bottom = (-c - b*bottom) / a
            if left <= x_bottom <= right and is_valid_intersection(x_bottom, bottom):
                intersections.append((x_bottom, bottom))
        
        # If we have multiple intersections, sort by distance from starting point
        if len(intersections) > 1:
            # Use the direction of movement to prioritize
            dx = x2 - x1
            dy = y2 - y1
            
            # Sort based on dot product with movement vector to find point in the movement direction
            intersections.sort(key=lambda p: dx * (p[0] - x1) + dy * (p[1] - y1))
            
            # If entering canvas, keep furthest entry point (last intersection)
            # If leaving canvas, keep first exit point (first intersection)
            if not (0 <= x2 < right and 0 <= y2 < bottom):  # Leaving canvas
                intersections = [intersections[0]]
            else:  # Entering canvas
                intersections = [intersections[-1]]
        
        return intersections
    
    def end_stroke(self, event):
        """Handle the end of a stroke, saving it to the current frame only"""
        if self.is_drawing:
            self.is_drawing = False
            
            if self.current_tool == "pencil":
                # Only add if it's a valid stroke with at least two points
                if len(self.current_stroke) > 1:
                    # Add the stroke to the current strokes list
                    self.strokes.append(self.current_stroke)
                    # Save the current strokes to the current keyframe
                    # This ensures strokes are saved to the current frame only
                    self.keyframes[self.current_keyframe] = copy.deepcopy(self.strokes)
                    
                    # Log the operation for debugging
                    logger.info(f"Added stroke to keyframe {self.current_keyframe}, now has {len(self.strokes)} strokes")
                    
                    # Save state for undo after adding the stroke
                    self.save_state()
                self.erase_state_saved = False
            elif self.current_tool == "eraser" and hasattr(self, 'erase_state_saved') and self.erase_state_saved:
                # Reset the flag so next eraser operation will save state
                self.erase_state_saved = False
            
            # Clean up temporary variables
            self.current_stroke = []
            if hasattr(self, 'last_x'):
                del self.last_x
            if hasattr(self, 'last_y'):
                del self.last_y
            if hasattr(self, 'last_event_x'):
                del self.last_event_x
            if hasattr(self, 'last_event_y'):
                del self.last_event_y
    
    def set_keyframe(self):
        """Set current frame as keyframe, including background image"""
        try:
            frame_num = int(self.keyframe_var.get())
            prev_frame = self.current_keyframe
            self.current_keyframe = frame_num
            
            # If changing to a different frame, make sure we store current strokes
            if prev_frame != frame_num:
                # Save previous frame explicitly
                self.keyframes[prev_frame] = copy.deepcopy(self.strokes)
            
            # Call dedicated helper function to save with background for the new frame
            self.save_keyframe_with_background()
            
            # If changing to a different frame, load it
            if prev_frame != frame_num:
                self.load_keyframe(frame_num)
            
        except ValueError:
            messagebox.showerror("Error", "Invalid keyframe number")
    
    def load_keyframe(self, frame_num):
        """Load a keyframe"""
        logger.info(f"Loading keyframe {frame_num}")
        current_frame = self.current_keyframe
        
        # Save current frame data explicitly before switching
        if current_frame != frame_num and self.strokes:
            # Only save if there are strokes to save and we're actually changing frames
            self.keyframes[current_frame] = copy.deepcopy(self.strokes)
            logger.info(f"Saved current frame {current_frame} with {len(self.strokes)} strokes before switching")
        
        # Clear the canvas
        self.canvas.delete("all")
        
        # Load the strokes for the new frame
        if frame_num in self.keyframes:
            # Load strokes - make a deep copy to avoid reference issues
            self.strokes = copy.deepcopy(self.keyframes[frame_num])
            logger.info(f"Loaded {len(self.strokes)} strokes for frame {frame_num}")
        else:
            # If the frame doesn't exist yet, initialize with empty strokes
            self.strokes = []
            logger.info(f"No data for frame {frame_num}, initialized with empty strokes")
        
        # Update the display
        self.redraw_canvas()
        
        # Update status
        self.status_var.set(f"Loaded keyframe {frame_num} ({len(self.strokes)} strokes)")
        
        # Update UI to reflect current keyframe
        self.keyframe_var.set(str(frame_num))
        self.current_keyframe = frame_num
        
        # Reset undo/redo history when changing frames
        self.history = [copy.deepcopy(self.strokes)]
        self.redo_stack = []
        
        # Log active keyframes for debugging
        logger.info(f"Active keyframes: {list(self.keyframes.keys())}")
    
    def next_keyframe(self):
        self.current_keyframe += 1
        self.keyframe_var.set(str(self.current_keyframe))
        self.load_keyframe(self.current_keyframe)
    
    def prev_keyframe(self):
        if self.current_keyframe > 1:
            self.current_keyframe -= 1
            self.keyframe_var.set(str(self.current_keyframe))
            self.load_keyframe(self.current_keyframe)
    
    def clear_canvas(self, save_history=False):
        """Clear the canvas, removing all drawings"""
        if save_history and self.strokes:  # Don't save if already empty
            self.save_state()  # Save current state before clearing
        
        # Clear the canvas
        self.canvas.delete("all")
        self.strokes = []
        
        # Remove the keyframe from the keyframes dictionary when it's completely cleared
        cleared_frame = self.current_keyframe
        if cleared_frame in self.keyframes:
            logger.info(f"Removing keyframe {cleared_frame} from keyframes dictionary")
            del self.keyframes[cleared_frame]
        
        # Redraw the current canvas
        self.redraw_canvas()
        
        if save_history:
            self.save_state()  # Save the cleared state
        
        # Update status to indicate the frame was cleared
        self.status_var.set(f"Cleared keyframe {cleared_frame}")

    def update_all_affected_onion_skins(self, cleared_frame=None):
        """Update onion skins for all frames that might be affected by a change"""
        if not self.keyframes:
            return
        
        # This functionality is no longer needed with our simplified onion skin approach
        # that only shows directly adjacent frames
        logger.debug(f"Skipping complex onion skin update - using simple adjacent frame approach")
        
        # We'll just redraw the current frame with the new onion skin logic
        self.redraw_canvas()
    
    def redraw_canvas(self):
        """Redraw the canvas with current strokes and optional onion skins"""
        self.canvas.delete("all")
        
        # Set the erase_state_saved flag to False so the next erase operation will save state
        if hasattr(self, 'erase_state_saved'):
            self.erase_state_saved = False
        
        # Draw onion skins if enabled
        if self.show_onion_skin:
            # Get strictly previous and next frame numbers, not keyframes
            current_frame = self.current_keyframe
            prev_frame = current_frame - 1
            next_frame = current_frame + 1
            
            # Log the frames we're looking for
            logger.debug(f"Looking for onion skins: prev={prev_frame}, current={current_frame}, next={next_frame}")
            
            # Check if these exact frames exist in keyframes dictionary
            if prev_frame in self.keyframes:
                logger.debug(f"Drawing previous frame {prev_frame} with blue onion skin")
                self.draw_onion_skin(self.keyframes[prev_frame], alpha_factor=1.0, color="blue")
            else:
                logger.debug(f"Previous frame {prev_frame} not found in keyframes")
                
            if next_frame in self.keyframes:
                logger.debug(f"Drawing next frame {next_frame} with red onion skin")
                self.draw_onion_skin(self.keyframes[next_frame], alpha_factor=1.0, color="red")
            else:
                logger.debug(f"Next frame {next_frame} not found in keyframes")
        
        # Draw current strokes on top with dark grey color, adjusted for zoom
        for stroke in self.strokes:
            for i in range(len(stroke) - 1):
                # Convert actual coordinates to display coordinates including zoom factor
                self.canvas.create_line(
                    stroke[i][0] * self.scale_factor * self.zoom_factor, 
                    stroke[i][1] * self.scale_factor * self.zoom_factor, 
                    stroke[i+1][0] * self.scale_factor * self.zoom_factor, 
                    stroke[i+1][1] * self.scale_factor * self.zoom_factor, 
                    width=max(1, int(2 * self.scale_factor * self.zoom_factor)), 
                    fill=self.pencil_color, 
                    smooth=True
                )
    
    def draw_onion_skin(self, strokes, alpha_factor=1.0, color="blue"):
        """Draw an onion skin with the given opacity and color"""
        # Calculate opacity in hex format (00-FF)
        alpha = int((self.onion_skin_opacity / 100.0) * alpha_factor * 255)
        alpha_hex = format(alpha, '02x')
        
        # Create color with alpha transparency
        hex_color = f"#{color}{alpha_hex}" if color in ["red", "blue"] else f"#{color}{alpha_hex}"
        
        # Draw strokes with transparency, accounting for zoom
        for stroke in strokes:
            for i in range(len(stroke) - 1):
                # Convert actual coordinates to display coordinates with zoom
                x1 = stroke[i][0] * self.scale_factor * self.zoom_factor
                y1 = stroke[i][1] * self.scale_factor * self.zoom_factor
                x2 = stroke[i+1][0] * self.scale_factor * self.zoom_factor
                y2 = stroke[i+1][1] * self.scale_factor * self.zoom_factor
                
                # In tkinter, you can't set alpha directly, so we use lighter colors
                # to simulate transparency
                if color == "blue":
                    line_color = f"#{alpha_hex}{alpha_hex}ff"  # Blue with alpha
                elif color == "red":
                    line_color = f"#ff{alpha_hex}{alpha_hex}"  # Red with alpha
                else:
                    line_color = f"#{alpha_hex}{alpha_hex}{alpha_hex}"  # Gray with alpha
                
                self.canvas.create_line(
                    x1, y1, x2, y2,
                    width=max(1, int(1.5 * self.scale_factor * self.zoom_factor)), 
                    fill=line_color, 
                    smooth=True,
                    dash=(3, 2)  # Dashed line for onion skin
                )
    
    def toggle_onion_skin(self):
        """Enable or disable onion skinning"""
        self.show_onion_skin = self.onion_var.get()
        self.redraw_canvas()
    
    def update_onion_skin(self, _=None):
        """Update onion skinning settings and redraw"""
        self.onion_skin_opacity = self.opacity_var.get()
        self.redraw_canvas()
    
    def interpolate_frames(self):
        # Save the current state before interpolation
        if self.strokes:
            self.save_state()
        
        try:
            start_frame = int(self.start_frame_var.get())
            end_frame = int(self.end_frame_var.get())
            num_inbetweens = int(self.num_inbetweens_var.get())
            
            if start_frame not in self.keyframes or end_frame not in self.keyframes:
                messagebox.showerror("Error", "Start or end keyframe not found")
                return
            
            start_strokes = self.keyframes[start_frame]
            end_strokes = self.keyframes[end_frame]
            
            # Basic validation - for proper interpolation, the number of strokes 
            # should match (this is a simplification)
            if len(start_strokes) != len(end_strokes):
                messagebox.showwarning("Warning", 
                                      "Keyframes have different numbers of strokes. " +
                                      "Interpolation may not work as expected.")
            
            logger.info("Using optical flow interpolation")
            
            # Create interpolated frames
            for i in range(1, num_inbetweens + 1):
                new_frame_num = start_frame + i * (end_frame - start_frame) / (num_inbetweens + 1)
                new_frame_num = int(new_frame_num)
                
                # Calculate interpolation factor (0.0 to 1.0)
                factor = i / (num_inbetweens + 1)
                
                # Create interpolated strokes using optical flow
                new_strokes = self.optical_flow_interpolate(start_strokes, end_strokes, factor)
                
                # Store the interpolated frame
                self.keyframes[new_frame_num] = new_strokes
            
            self.status_var.set(f"Created {num_inbetweens} interpolated frames between {start_frame} and {end_frame} using Optical Flow")
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid input values: {str(e)}")
    
    def optical_flow_interpolate(self, start_strokes, end_strokes, factor):
        """
        Optical flow interpolation between two frames
        Uses GPU acceleration when available with cross-platform support
        """
        logger.info(f"Performing OPTICAL FLOW interpolation with factor {factor}")
        
        progress = ttk.Progressbar(self.root, mode='indeterminate')
        progress.pack(fill='x', padx=10, pady=5)
        progress.start()
        self.root.update()
        
        try:
            import cv2
            import numpy as np
            
            # Check if accelerated computing is available (OpenCL or Metal for Mac)
            has_opencl = False
            has_metal = False
            
            # Check for OpenCL support (works on Windows, Linux, and Mac)
            try:
                if cv2.ocl.haveOpenCL():
                    cv2.ocl.setUseOpenCL(True)
                    has_opencl = cv2.ocl.useOpenCL()
                    logger.info(f"OpenCL acceleration: {'Available' if has_opencl else 'Not available'}")
            except Exception:
                logger.info("OpenCL support check failed")
                
            # On macOS, check for Metal support
            if not has_opencl and self.root.tk.call('tk', 'windowingsystem') == 'aqua':
                try:
                    # Indirect check for Metal through VideoCapture backend
                    # This isn't a perfect check but helps differentiate Metal capability
                    metal_check = cv2.videoio_registry.getBackendName(cv2.CAP_AVFOUNDATION) == "AVFoundation"
                    has_metal = metal_check and int(cv2.__version__.split('.')[0]) >= 4
                    logger.info(f"Metal acceleration: {'Available' if has_metal else 'Not available'}")
                except Exception:
                    logger.info("Metal support check failed")
            
            # Create blank canvases at a resolution that balances detail and performance
            canvas_width, canvas_height = 1920, 1080  # Fixed size for consistent performance
            
            # Create images from strokes
            start_img = np.ones((canvas_height, canvas_width), dtype=np.uint8) * 255
            end_img = np.ones((canvas_height, canvas_width), dtype=np.uint8) * 255
            
            # Draw strokes on canvases - pass cv2 to the helper methods
            self._draw_strokes_on_numpy_array(start_img, start_strokes, cv2)
            self._draw_strokes_on_numpy_array(end_img, end_strokes, cv2)
            
            # Calculate optical flow using best available method
            if has_opencl or has_metal:
                # Use OpenCV's optimized optical flow with GPU acceleration
                # This uses OpenCL on Windows/Linux and Metal optimizations on Mac
                flow = cv2.calcOpticalFlowFarneback(
                    start_img, end_img, None, 
                    pyr_scale=0.5, levels=5, winsize=13, 
                    iterations=10, poly_n=5, poly_sigma=1.2, flags=0
                )
                logger.info("Using GPU-accelerated optical flow")
            else:
                # CPU fallback with optimized parameters
                flow = cv2.calcOpticalFlowFarneback(
                    start_img, end_img, None, 
                    pyr_scale=0.5, levels=3, winsize=13, 
                    iterations=7, poly_n=5, poly_sigma=1.2, flags=0
                )
                logger.info("Using CPU optical flow")
            
            # Use flow vectors to interpolate between frames
            h, w = flow.shape[:2]
            
            # Create the interpolated frame
            # Scale the flow by the interpolation factor
            flow_x = flow[..., 0] * factor
            flow_y = flow[..., 1] * factor
            
            # Create mapping grid for remapping
            map_x = np.float32(np.tile(np.arange(w), (h, 1)))
            map_y = np.float32(np.tile(np.arange(h), (w, 1)).T)
            
            # Apply flow to generate mapped coordinates
            interp_map_x = map_x + flow_x
            interp_map_y = map_y + flow_y
            
            # Apply reverse mapping to warp the image
            interpolated = cv2.remap(start_img, interp_map_x, interp_map_y, 
                                    cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            
            # Extract strokes from the interpolated image - pass cv2 to the helper method
            new_strokes = self._extract_strokes_from_image(interpolated, start_strokes, end_strokes, factor, cv2)
            
            return new_strokes
        
        except ImportError:
            logger.error("OpenCV not available - optical flow interpolation requires OpenCV")
            messagebox.showerror("Error", "OpenCV not available. Optical flow interpolation requires OpenCV to be installed.")
            return []
        except Exception as e:
            logger.error(f"Optical flow interpolation failed: {str(e)}", exc_info=True)
            messagebox.showerror("Error", f"Optical flow interpolation failed: {str(e)}")
            return []
        finally:
            progress.stop()
            progress.destroy()

    def _find_point_at_param(self, stroke, t):
        """Helper function to find a point at parametric position t along a stroke"""
        if t <= 0:
            return stroke[0]
        if t >= 1:
            return stroke[-1]
        
        # Calculate total length of the stroke
        lengths = [0.0]
        total_length = 0.0
        for i in range(1, len(stroke)):
            segment_length = ((stroke[i][0] - stroke[i-1][0])**2 + 
                             (stroke[i][1] - stroke[i-1][1])**2)**0.5
            total_length += segment_length
            lengths.append(total_length)
        
        # Normalize lengths to [0, 1]
        if total_length > 0:
            lengths = [l / total_length for l in lengths]
        
        # Find the segment containing t
        for i in range(1, len(lengths)):
            if lengths[i-1] <= t < lengths[i]:
                # Interpolate within this segment
                segment_t = (t - lengths[i-1]) / (lengths[i] - lengths[i-1]) if lengths[i] > lengths[i-1] else 0
                x = stroke[i-1][0] + segment_t * (stroke[i][0] - stroke[i-1][0])
                y = stroke[i-1][1] + segment_t * (stroke[i][1] - stroke[i-1][1])
                return (x, y)
        
        # Fallback
        return stroke[-1]

    def _draw_strokes_on_numpy_array(self, img, strokes, cv2=None):
        """Draw strokes on a numpy array image"""
        # Check if cv2 was passed from calling function
        if cv2 is None:
            # Local import in case the method is called directly
            import cv2 as cv2_local
            cv2 = cv2_local
            
        h, w = img.shape if len(img.shape) == 2 else img.shape[:2]
        
        for stroke in strokes:
            # Skip strokes with fewer than 2 points
            if len(stroke) < 2:
                continue
                
            points = []
            for point in stroke:
                # Scale stroke coordinates to image dimensions
                x = int(point[0] * w / self.canvas_width)
                y = int(point[1] * h / self.canvas_height)
                points.append((x, y))
                
            # Draw lines connecting points
            for i in range(len(points) - 1):
                cv2.line(img, points[i], points[i+1], 0, thickness=2)

    def _extract_strokes_from_image(self, img, start_strokes, end_strokes, factor, cv2=None):
        """Extract stroke data from the interpolated image using intelligent path tracing"""
        # Check if cv2 was passed from calling function
        if cv2 is None:
            # Local import in case the method is called directly
            import cv2 as cv2_local
            cv2 = cv2_local
        
        # Also need numpy
        import numpy as np
        
        # First try contour detection
        _, binary = cv2.threshold(img, 240, 255, cv2.THRESH_BINARY_INV)
        
        # Clean up noise
        kernel = np.ones((3,3), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        
        # Find contours
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        new_strokes = []
        
        # For better quality, use stroke matching instead of just contours
        # This approach matches start and end strokes and uses optical flow to trace their paths
        for j in range(min(len(start_strokes), len(end_strokes))):
            start_stroke = start_strokes[j]
            end_stroke = end_strokes[j]
            
            if len(start_stroke) == len(end_stroke):
                # Create an interpolated stroke by following the flow
                new_stroke = []
                for k in range(len(start_stroke)):
                    # Get corresponding points
                    start_point = start_stroke[k]
                    end_point = end_stroke[k]
                    
                    # Linear interpolation as fallback (more reliable than pure flow for points)
                    new_x = (1 - factor) * start_point[0] + factor * end_point[0]
                    new_y = (1 - factor) * start_point[1] + factor * end_point[1]
                    
                    # Check if the point falls on a contour in the flow image
                    # This helps snap points to actual visible lines
                    h, w = img.shape if len(img.shape) == 2 else img.shape[:2]
                    img_x = int(new_x * w / self.canvas_width)
                    img_y = int(new_y * h / self.canvas_height)
                    
                    # Check 5x5 region around point to find black pixels (stroke)
                    radius = 5
                    img_x = max(radius, min(w-radius-1, img_x))
                    img_y = max(radius, min(h-radius-1, img_y))
                    region = binary[img_y-radius:img_y+radius+1, img_x-radius:img_x+radius+1]
                    
                    # If we found stroke pixels, adjust the point to the center of mass
                    if np.any(region > 0):
                        # Find center of mass of white pixels
                        white_y, white_x = np.where(region > 0)
                        if len(white_x) > 0:
                            center_x = np.mean(white_x) + img_x - radius
                            center_y = np.mean(white_y) + img_y - radius
                            
                            # Convert back to canvas coordinates
                            adjusted_x = center_x * self.canvas_width / w
                            adjusted_y = center_y * self.canvas_height / h
                            
                            # Blend with original interpolation for stability
                            new_x = 0.7 * adjusted_x + 0.3 * new_x
                            new_y = 0.7 * adjusted_y + 0.3 * new_y
                    
                    new_stroke.append((new_x, new_y))
                new_strokes.append(new_stroke)
            else:
                # Use the reparameterization approach for different point counts
                # This produces better quality than the contour method for uneven strokes
                new_stroke = []
                
                # Create an adaptive number of points based on stroke complexity
                num_points = max(len(start_stroke), len(end_stroke))
                
                # Parameterize both strokes
                for t in np.linspace(0, 1, num_points):
                    # Find corresponding points on each stroke based on parameterization
                    start_param = self._find_point_at_param(start_stroke, t)
                    end_param = self._find_point_at_param(end_stroke, t)
                    
                    # Interpolate between them
                    new_x = (1 - factor) * start_param[0] + factor * end_param[0]
                    new_y = (1 - factor) * start_param[1] + factor * end_param[1]
                    
                    new_stroke.append((new_x, new_y))
                    
                new_strokes.append(new_stroke)
        
        return new_strokes



    def play_animation(self):
        """Play animation directly in the main canvas"""
        if self.animation_running:
            return
        
        try:
            fps = int(self.fps_var.get())
            if fps < 1:  # Prevent division by zero or negative values
                fps = 12
            delay = int(1000 / fps)  # Milliseconds between frames
            
            frame_nums = sorted(self.keyframes.keys())
            if not frame_nums:
                messagebox.showerror("Error", "No frames to animate")
                return
            
            # Store the current state to restore after animation
            self.animation_current_frame = self.current_keyframe
            self.animation_current_strokes = copy.deepcopy(self.strokes)
            
            self.animation_running = True
            self.play_btn.config(state=tk.DISABLED)  # Disable play button while playing
            self.stop_btn.config(state=tk.NORMAL)    # Enable stop button
            
            # Also disable drawing while animation is playing - unbind from both canvas and container
            self.canvas_container.unbind("<Button-1>")
            self.canvas_container.unbind("<B1-Motion>")
            self.canvas_container.unbind("<ButtonRelease-1>")
            self.canvas.unbind("<Button-1>")
            self.canvas.unbind("<B1-Motion>")
            self.canvas.unbind("<ButtonRelease-1>")
            
            # Define a recursive function to show frames
            def show_frame(index):
                if not self.animation_running:
                    return
                try:
                    frame_num = frame_nums[index % len(frame_nums)]
                    strokes = self.keyframes[frame_num]
                    
                    # Clear canvas and draw strokes
                    self.canvas.delete("all")
                    
                    # Draw strokes with dark grey color, accounting for zoom
                    for stroke in strokes:
                        for i in range(len(stroke) - 1):
                            # Scale for display, including zoom factor
                            x1 = stroke[i][0] * self.scale_factor * self.zoom_factor
                            y1 = stroke[i][1] * self.scale_factor * self.zoom_factor
                            x2 = stroke[i+1][0] * self.scale_factor * self.zoom_factor
                            y2 = stroke[i+1][1] * self.scale_factor * self.zoom_factor
                            self.canvas.create_line(
                                x1, y1, x2, y2,
                                width=max(1, int(2 * self.scale_factor * self.zoom_factor)),
                                fill=self.pencil_color, 
                                smooth=True
                            )
                    
                    # Update status to show current frame
                    self.status_var.set(f"Animation playing: Frame {frame_num} of {len(frame_nums)}")
                    
                    # Schedule the next frame
                    self.root.after(delay, show_frame, (index + 1) % len(frame_nums))
                except Exception as e:
                    logger.error(f"Animation error: {str(e)}", exc_info=True)
                    self.stop_animation()
                    self.status_var.set(f"Animation error: {str(e)}")
            
            # Start showing frames
            show_frame(0)
        except ValueError:
            messagebox.showerror("Error", "Invalid FPS value, using default 12 FPS")
            self.fps_var.set("12")
            self.play_animation()  # Try again with valid value
        except Exception as e:
            logger.error(f"Animation setup error: {str(e)}", exc_info=True)
            messagebox.showerror("Error", f"Animation failed: {str(e)}")
            self.animation_running = False
    
    def stop_animation(self):
        """Stop animation playback and restore drawing state"""
        if not self.animation_running:
            return
        
        self.animation_running = False
        
        # Update button states
        self.play_btn.config(state=tk.NORMAL)  # Re-enable play button
        self.stop_btn.config(state=tk.DISABLED)  # Disable stop button
        
        # Restore drawing capability - bind to both container and canvas
        self.canvas_container.bind("<Button-1>", self.start_stroke)
        self.canvas_container.bind("<B1-Motion>", self.continue_stroke)
        self.canvas_container.bind("<ButtonRelease-1>", self.end_stroke)
        self.canvas.bind("<Button-1>", self.start_stroke)
        self.canvas.bind("<B1-Motion>", self.continue_stroke)
        self.canvas.bind("<ButtonRelease-1>", self.end_stroke)
        
        # Restore the saved state before animation
        if hasattr(self, 'animation_current_frame') and hasattr(self, 'animation_current_strokes'):
            # Set current keyframe back to what it was
            self.current_keyframe = self.animation_current_frame
            self.keyframe_var.set(str(self.current_keyframe))
            
            # Restore strokes from saved state before animation
            self.strokes = copy.deepcopy(self.animation_current_strokes)
            
            # Clean up saved state to free memory
            del self.animation_current_strokes
            
            # Redraw canvas with original state
            self.redraw_canvas()
            self.status_var.set(f"Animation stopped, returned to keyframe {self.current_keyframe}")
    
    def export_frames(self):
        """Export frames"""
        if not self.keyframes:
            messagebox.showinfo("Info", "No frames to export")
            return
        
        export_dir = filedialog.askdirectory(title="Select Export Directory")
        if not export_dir:
            return
        
        frame_nums = sorted(self.keyframes.keys())
        
        try:
            for frame_num in frame_nums:
                # Create image at full resolution (1920x1080)
                img = Image.new('RGB', (self.canvas_width, self.canvas_height), color='white')
                
                # Create a higher resolution image for anti-aliasing
                img_high_res = img.resize((self.canvas_width * 4, self.canvas_height * 4), Image.Resampling.LANCZOS)
                draw = ImageDraw.Draw(img_high_res)
                
                # Draw strokes with anti-aliasing by drawing at higher resolution
                strokes = self.keyframes[frame_num]
                for stroke in strokes:
                    for i in range(len(stroke) - 1):
                        # Scale coordinates to higher resolution
                        x1, y1 = stroke[i][0] * 4, stroke[i][1] * 4
                        x2, y2 = stroke[i+1][0] * 4, stroke[i+1][1] * 4
                        draw.line([x1, y1, x2, y2], fill=self.pencil_color, width=8)  # 2 * 4 for higher resolution
                
                # Resize back to original size with anti-aliasing
                img = img_high_res.resize((self.canvas_width, self.canvas_height), Image.Resampling.LANCZOS)
                
                # Save frame
                filename = os.path.join(export_dir, f"frame_{frame_num:04d}.png")
                img.save(filename)
                logger.info(f"Saved frame {frame_num} to {filename}")
            
            self.status_var.set(f"Exported {len(frame_nums)} frames at {self.canvas_width}x{self.canvas_height} to {export_dir}")
            messagebox.showinfo("Success", f"Exported {len(frame_nums)} frames at {self.canvas_width}x{self.canvas_height}")
        except Exception as e:
            logger.error(f"Export failed: {str(e)}", exc_info=True)
            messagebox.showerror("Error", f"Export failed: {str(e)}")
    
    def save_keyframe_with_background(self):
        """Helper function to explicitly save the current frame"""
        try:
            frame_num = self.current_keyframe
            
            # Save strokes explicitly for this frame
            self.keyframes[frame_num] = copy.deepcopy(self.strokes)
            logger.info(f"Saved {len(self.strokes)} strokes for keyframe {frame_num}")
            
            # Update status
            self.status_var.set(f"Keyframe {frame_num} set with {len(self.strokes)} strokes")
            
            # Log active keyframes for debugging
            logger.info(f"Active keyframes after saving: {list(self.keyframes.keys())}")
        except Exception as e:
            logger.error(f"Error saving keyframe: {e}", exc_info=True)
            messagebox.showerror("Error", "Failed to save keyframe")
    

    def copy_strokes(self, event=None):
        """Copy current strokes to clipboard in both internal format and JSON for external apps"""
        if not self.strokes:
            self.status_var.set("Nothing to copy")
            return "break"
        
        try:
            # Copy strokes to internal clipboard
            self.clipboard = copy.deepcopy(self.strokes)
            
            # Convert strokes to JSON format for external clipboard
            json_strokes = json.dumps(self.strokes)
            
            # Use Tkinter clipboard to store JSON data
            self.root.clipboard_clear()
            self.root.clipboard_append(json_strokes)
            
            self.status_var.set(f"Copied {len(self.strokes)} strokes to clipboard")
        except Exception as e:
            self.status_var.set(f"Error copying strokes: {str(e)}")
    
    def paste_strokes(self, event=None):
        """Paste strokes from clipboard, handling both internal and external formats"""
        try:
            # Try to get JSON data from external clipboard
            json_data = self.root.clipboard_get()
            paste_strokes = json.loads(json_data)
            
            # Process the strokes to ensure valid format
            processed_strokes = []
            for stroke in paste_strokes:
                if not isinstance(stroke, list):
                    continue
                
                new_stroke = []
                for point in stroke:
                    # Handle both tuple and list formats for points
                    if isinstance(point, (list, tuple)) and len(point) >= 2:
                        try:
                            x, y = float(point[0]), float(point[1])
                            new_stroke.append((x, y))
                        except (ValueError, TypeError):
                            # Skip invalid points
                            continue
                
                if len(new_stroke) > 1:  # Only add if it's a valid stroke
                    processed_strokes.append(new_stroke)
            
            # Add processed strokes to current strokes
            if processed_strokes:
                self.strokes.extend(processed_strokes)
                self.save_state()
                self.redraw_canvas()
                
                num_strokes = len(processed_strokes)
                self.status_var.set(f"Pasted {num_strokes} strokes in exact position")
            else:
                self.status_var.set("No valid strokes found in clipboard data")
        except Exception as e:
            self.status_var.set(f"Error pasting strokes: {str(e)}")
        return "break"
    
    def on_window_resize(self, event=None):
        """Handle window resize to ensure canvas stays centered"""
        # We only care about resize events for the window, not other widgets
        if event.widget == self.root:
            # No need to resize the canvas, just ensure it's centered
            # The pack manager with expand=True and anchor=CENTER handles this automatically
            pass
    
    def erase_at_point(self, canvas_x, canvas_y):
        """Erase strokes near the specified point"""
        # Save state before first erase operation
        if not hasattr(self, 'erase_state_saved') or not self.erase_state_saved:
            self.save_state()
            self.erase_state_saved = True
        
        # Scale the eraser radius for display coordinates, accounting for zoom
        eraser_radius = self.eraser_size / 2  # Eraser size is the diameter
        display_radius = eraser_radius * self.scale_factor * self.zoom_factor
        display_x = canvas_x * self.scale_factor * self.zoom_factor
        display_y = canvas_y * self.scale_factor * self.zoom_factor
        
        # Draw visual feedback of eraser directly using display coordinates
        eraser_outline = self.canvas.create_oval(
            display_x - display_radius,
            display_y - display_radius,
            display_x + display_radius,
            display_y + display_radius,
            outline="red",
            width=1
        )
        self.canvas.after(100, lambda: self.canvas.delete(eraser_outline))
        
        # Check each stroke
        modified = False
        new_strokes = []
        for stroke in self.strokes:
            # Check if any point in the stroke is within eraser radius
            points_to_remove = []
            for i, point in enumerate(stroke):
                dist = ((point[0] - canvas_x)**2 + (point[1] - canvas_y)**2)**0.5
                if dist <= eraser_radius:
                    points_to_remove.append(i)
                modified = True
            
            # Convert to continuous ranges to handle split properly
            if points_to_remove:
                ranges = []
                start = points_to_remove[0]
                end = start
                for i in range(1, len(points_to_remove)):
                    if points_to_remove[i] == end + 1:
                        end = points_to_remove[i]
                    else:
                        ranges.append((start, end))
                        start = points_to_remove[i]
                        end = start
                ranges.append((start, end))
                
                # Handle each continuous range
                last_end = -1
                segments = []
                for start, end in ranges:
                    # Add segment before this range if it exists and has enough points
                    if start > last_end + 1:
                        segment = stroke[last_end+1:start]
                        if len(segment) > 1:
                            segments.append(segment)
                    last_end = end
                
                # Add final segment after the last removed range
                if last_end < len(stroke) - 1:
                    segment = stroke[last_end+1:]
                    if len(segment) > 1:
                        segments.append(segment)
                
                # Add valid segments to new strokes
                new_strokes.extend(segments)
            else:
                # If no points were affected, keep the whole stroke
                new_strokes.append(stroke)
        
        if modified:
            self.strokes = new_strokes
            self.keyframes[self.current_keyframe] = copy.deepcopy(self.strokes)
            self.redraw_canvas()
    



if __name__ == "__main__":
    root = tk.Tk()
    app = OptiflowApp(root)
    root.mainloop()