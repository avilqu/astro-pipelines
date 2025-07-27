import numpy as np
from PyQt6.QtWidgets import QSlider
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import Qt


class HistogramController:
    """
    Handles all histogram stretch and brightness adjustment functionality
    for the FITS viewer.
    """
    
    def __init__(self, parent_viewer):
        self.parent = parent_viewer
        self.stretch_mode = 'linear'  # 'linear' or 'log', default to linear
        self.clipping_enabled = False
        self.display_min = None
        self.display_max = None
        self.sigma_clip = 3.0
        self.stretch_locked = True
        self.locked_display_min = None
        self.locked_display_max = None
        self.brightness_adjustment = 0.0  # Track user's brightness adjustment separately
        
        # Create UI elements
        self._create_ui_elements()
    
    def _create_ui_elements(self):
        """Create histogram-related UI elements for the toolbar."""
        # UI elements are now created by the toolbar controller
        # Get references to the UI elements from the toolbar controller
        self.linear_action = self.parent.toolbar_controller.linear_action
        self.log_action = self.parent.toolbar_controller.log_action
        self.brightness_slider = self.parent.toolbar_controller.brightness_slider
        self.clipping_action = self.parent.toolbar_controller.clipping_action
    
    def on_brightness_slider_changed(self, value):
        """Handle brightness slider value changes."""
        # Convert slider value (0-100) to brightness adjustment
        # 50 = neutral, 0 = darkest, 100 = brightest
        if self.display_min is None or self.display_max is None:
            auto_min, auto_max = self._get_auto_display_minmax()
            self.display_min = auto_min
            self.display_max = auto_max
        
        # Calculate the adjustment range based on image statistics
        step = self._get_display_min_step()
        adjustment_range = 10 * step  # Allow for significant brightness adjustment
        
        # Convert slider value to adjustment
        # value 50 = no adjustment, value 0 = darkest, value 100 = brightest
        adjustment = (value - 50) / 50.0 * adjustment_range
        
        # Store the brightness adjustment separately
        self.brightness_adjustment = adjustment
        
        # Apply adjustment to display_min (lower values = brighter image)
        auto_min, auto_max = self._get_auto_display_minmax()
        adjusted_min = auto_min - adjustment
        
        # Update display parameters
        self.display_min = adjusted_min
        self.locked_display_min = self.display_min
        self.locked_display_max = self.display_max
        
        # Update the image display
        self.parent.update_image_display(keep_zoom=True)
        self.update_brightness_slider_tooltip()

    def update_brightness_slider_tooltip(self):
        """Update tooltip to show current brightness level."""
        if self.display_min is not None:
            self.brightness_slider.setToolTip(f"Adjust image brightness (min: {self.display_min:.2f})")
        else:
            self.brightness_slider.setToolTip("Adjust image brightness")

    def _get_auto_display_minmax(self):
        """Compute the default min/max as would be used by create_image_object."""
        if self.stretch_mode == 'log':
            data = self.parent.image_data.astype(float)
            # Avoid divide-by-zero warning by only computing log10 for positive values
            mask = data > 0
            log_data = np.zeros_like(data)
            log_data[mask] = np.log10(data[mask])
            data = log_data
        else:
            data = self.parent.image_data
            
        if self.clipping_enabled:
            finite_vals = data[np.isfinite(data)]
            if finite_vals.size > 0:
                mean = float(np.mean(finite_vals))
                std = float(np.std(finite_vals))
                return mean - self.sigma_clip * std, mean + self.sigma_clip * std
            else:
                return float(np.min(data)), float(np.max(data))
        else:
            finite_vals = data[np.isfinite(data)]
            if finite_vals.size > 0:
                histo = np.histogram(finite_vals, 60, None, True)
                return float(histo[1][0]), float(histo[1][-1])
            else:
                return float(np.min(data)), float(np.max(data))

    def _get_display_min_step(self):
        """Use a step based on the image stddev."""
        if self.stretch_mode == 'log':
            data = self.parent.image_data.astype(float)
            # Avoid divide-by-zero warning by only computing log10 for positive values
            mask = data > 0
            log_data = np.zeros_like(data)
            log_data[mask] = np.log10(data[mask])
            data = log_data
        else:
            data = self.parent.image_data
            
        if data is not None:
            finite_vals = data[np.isfinite(data)]
            if finite_vals.size > 0:
                return float(np.std(finite_vals)) * 0.4  # 4x bigger than before
        return 4.0

    def update_display_minmax_tooltips(self):
        """Update brightness slider tooltip."""
        self.update_brightness_slider_tooltip()

    def set_linear_stretch(self):
        """Set linear histogram stretch mode."""
        self.stretch_mode = 'linear'
        # Recalculate base parameters with new stretch mode
        auto_min, auto_max = self._get_auto_display_minmax()
        # Apply the stored brightness adjustment to preserve user's settings
        adjusted_min = auto_min - self.brightness_adjustment
        self.locked_display_min = adjusted_min
        self.locked_display_max = auto_max
        self.display_min = self.locked_display_min
        self.display_max = self.locked_display_max
        # Update the display with the new stretch mode
        self.parent.update_image_display(keep_zoom=True)
        # Don't call zoom_to_fit() as it changes the viewport position

    def set_log_stretch(self):
        """Set logarithmic histogram stretch mode."""
        self.stretch_mode = 'log'
        # Recalculate base parameters with new stretch mode
        auto_min, auto_max = self._get_auto_display_minmax()
        # Apply the stored brightness adjustment to preserve user's settings
        adjusted_min = auto_min - self.brightness_adjustment
        self.locked_display_min = adjusted_min
        self.locked_display_max = auto_max
        self.display_min = self.locked_display_min
        self.display_max = self.locked_display_max
        # Update the display with the new stretch mode
        self.parent.update_image_display(keep_zoom=True)
        # Don't call zoom_to_fit() as it changes the viewport position

    def toggle_clipping(self):
        """Toggle sigma clipping for display stretch."""
        self.clipping_enabled = not self.clipping_enabled
        self.clipping_action.setChecked(self.clipping_enabled)
        # Recalculate base parameters with new clipping setting
        auto_min, auto_max = self._get_auto_display_minmax()
        # Apply the stored brightness adjustment to preserve user's settings
        adjusted_min = auto_min - self.brightness_adjustment
        self.locked_display_min = adjusted_min
        self.locked_display_max = auto_max
        self.display_min = self.locked_display_min
        self.display_max = self.locked_display_max
        # Update the display with the new clipping setting
        self.parent.update_image_display(keep_zoom=True)

    def toggle_stretch_lock(self):
        """This method is no longer used since stretch is always locked by default."""
        pass

    def update_button_states_for_no_image(self):
        """Disable histogram-related buttons when no image is loaded."""
        # Button state management is now handled by the toolbar controller
        pass

    def update_button_states_for_image_loaded(self):
        """Enable histogram-related buttons when an image is loaded."""
        # Button state management is now handled by the toolbar controller
        pass

    def initialize_for_new_image(self, restore_view=False):
        """Initialize histogram parameters for a newly loaded image."""
        # Since stretch is always locked, initialize locked parameters on first load
        if self.locked_display_min is None or self.locked_display_max is None:
            # First time loading - calculate and store locked parameters
            auto_min, auto_max = self._get_auto_display_minmax()
            self.locked_display_min = auto_min
            self.locked_display_max = auto_max
            self.display_min = self.locked_display_min
            self.display_max = self.locked_display_max
        else:
            # Use existing locked parameters - DO NOT recalculate based on new image
            # Apply the stored brightness adjustment to the new image
            auto_min, auto_max = self._get_auto_display_minmax()
            adjusted_min = auto_min - self.brightness_adjustment
            self.locked_display_min = adjusted_min
            self.locked_display_max = auto_max
            self.display_min = self.locked_display_min
            self.display_max = self.locked_display_max
            # Update the display with the locked parameters
            self.parent.update_image_display(keep_zoom=restore_view)
        
        # Restore brightness slider position and apply adjustment
        if hasattr(self.parent, '_last_brightness'):
            self.brightness_slider.setValue(self.parent._last_brightness)
            # The brightness adjustment is already applied above, just update the slider tooltip
            self.update_brightness_slider_tooltip()
        else:
            self.brightness_slider.setValue(50)

    def save_state_before_switch(self):
        """Save current brightness state before switching images."""
        if self.parent.image_data is not None:
            self.parent._last_brightness = self.brightness_slider.value()
        else:
            self.parent._last_brightness = 50

    def get_display_parameters(self):
        """Get current display parameters for image creation."""
        return {
            'display_min': self.display_min,
            'display_max': self.display_max,
            'clipping': self.clipping_enabled,
            'sigma_clip': self.sigma_clip,
            'stretch_mode': self.stretch_mode
        } 