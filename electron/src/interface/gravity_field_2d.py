import math
from PySide6.QtCore import QPointF, QRectF
import numpy as np


class EpistemicGravityField2D:
    """
    Lightweight 2D projection of the 3D Epistemic Gravity Field for UI dynamics.
    Maintains a local potential field to smooth out network latency and provide
    immediate 'gravity' feelings for the Orb's movement.
    """

    def __init__(self, width=32, height=32):
        self.width = width
        self.height = height
        self.grid = np.zeros((width, height), dtype=np.float32)
        self.center = (width // 2, height // 2)
        # Smoothing factor for updates
        self.alpha = 0.2
        self.smoothed_pressure = 0.0

    def update_from_pulse(self, gravity_stats):
        """Update the 2D field based on aggregate statistics from the backend."""
        # Use entropy or renewal pressure to modulate the field intensity
        raw_pressure = gravity_stats.get("renewal_pressure", 0.0)

        # EMA Smoothing (Alpha 0.2 roughly corresponds to ~300ms at 10Hz updates)
        self.smoothed_pressure = (self.smoothed_pressure * (1.0 - self.alpha)) + (
            raw_pressure * self.alpha
        )
        pressure = self.smoothed_pressure

        # Simple simulation: Higher pressure = more turbulence/noise in the field
        # We decay the current field
        self.grid *= 0.95

        # Inject noise based on pressure (simulating the 'hot' outer shell)
        noise = np.random.normal(0, pressure * 0.1, self.grid.shape)
        self.grid += noise

        # Clip
        self.grid = np.clip(self.grid, 0.0, 1.0)

        return pressure

    def get_local_force(self, norm_x, norm_y):
        """
        Get the 2D force vector at a normalized position (0.0 to 1.0).
        Returns (fx, fy) derived from the field gradient.
        """
        gx = int(norm_x * (self.width - 1))
        gy = int(norm_y * (self.height - 1))

        # Clamp
        gx = max(0, min(gx, self.width - 1))
        gy = max(0, min(gy, self.height - 1))

        # Calculate local gradient (simple finite difference)
        val = self.grid[gx, gy]

        # Look around
        # High entropy areas typically repel in this architecture (instability)
        # So we create a force pointing AWAY from high values

        fx, fy = 0.0, 0.0

        # X gradient
        left = self.grid[gx - 1, gy] if gx > 0 else 0
        right = self.grid[gx + 1, gy] if gx < self.width - 1 else 0
        fx = -(right - left)  # Negative gradient (flow downhill)

        # Y gradient
        top = self.grid[gx, gy - 1] if gy > 0 else 0
        bottom = self.grid[gx, gy + 1] if gy < self.height - 1 else 0
        fy = -(bottom - top)

        return fx * 5.0, fy * 5.0  # Scale force
