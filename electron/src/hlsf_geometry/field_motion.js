class FieldMotion {
  constructor() {
    this.velocity = { x: 0, y: 0 };
  }

  update({ currentPosition, targetZone, intentProfile, screenBounds, maxAcceleration = 0.065 }) {
    const current = currentPosition || { x: 0, y: 0 };
    const target = targetZone || current;
    const profile = intentProfile || { maxSpeed: 0.64, accel: 0.04, damping: 0.983, steerMul: 0.74 };

    const dx = target.x - current.x;
    const dy = target.y - current.y;
    const distance = Math.hypot(dx, dy) || 1;
    const desiredVelocity = {
      x: (dx / distance) * profile.maxSpeed,
      y: (dy / distance) * profile.maxSpeed,
    };

    const dvx = desiredVelocity.x - this.velocity.x;
    const dvy = desiredVelocity.y - this.velocity.y;
    const dvm = Math.hypot(dvx, dvy);
    const accelerationLimit = Math.max(0.01, Math.min(maxAcceleration, profile.accel || maxAcceleration));
    const scale = dvm > accelerationLimit ? accelerationLimit / dvm : 1;

    this.velocity = {
      x: (this.velocity.x + dvx * scale) * profile.damping,
      y: (this.velocity.y + dvy * scale) * profile.damping,
    };

    const raw = {
      x: current.x + this.velocity.x,
      y: current.y + this.velocity.y,
    };

    const bounded = {
      x: Math.min(screenBounds.right, Math.max(screenBounds.left, raw.x)),
      y: Math.min(screenBounds.bottom, Math.max(screenBounds.top, raw.y)),
    };

    return {
      position: bounded,
      velocity: this.velocity,
      fieldState: {
        intensity: Math.min(1, Math.hypot(this.velocity.x, this.velocity.y)),
        turbulence: Math.max(0, 1 - profile.damping),
      },
    };
  }
}

module.exports = FieldMotion;
