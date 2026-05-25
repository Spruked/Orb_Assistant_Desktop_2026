class CompanionIntent {
  constructor(options = {}) {
    this.state = 'calm_idle';
    this.lastIntentChange = Date.now();
    this.playfulnessEnabled = Boolean(options.playfulnessEnabled);
    this.debug = Boolean(options.debug);
  }

  update(inputs = {}) {
    const {
      displayActive = true,
      bridgeHealth = 1,
      bridgeFault = false,
      isSubmitting = false,
      swarmPendingCount = 0,
      isUserActive = false,
      presenceProfile = {},
      cursorDistance = 0,
      returnDistance = 980,
    } = inputs;

    let next = 'calm_idle';
    if (!displayActive || cursorDistance > returnDistance) {
      next = 'returning';
    } else if (bridgeFault || bridgeHealth < 0.3) {
      next = 'concerned_degraded';
    } else if (isSubmitting) {
      next = 'thinking';
    } else if (swarmPendingCount > 0) {
      next = 'searching';
    } else if (isUserActive) {
      next = 'aware';
    } else if (presenceProfile?.is_idle && this.playfulnessEnabled) {
      next = 'playful_idle';
    }

    if (!this.playfulnessEnabled && next === 'playful_idle') {
      next = 'calm_idle';
    }

    return this.setIntent(next);
  }

  setIntent(nextState) {
    if (this.state !== nextState) {
      this.state = nextState;
      this.lastIntentChange = Date.now();
      this.logTelemetry({ intent: nextState, source: 'companion_intent' });
    }

    return {
      intent: this.state,
      motionProfile: this.getMotionProfile(this.state),
    };
  }

  getMotionProfile(state) {
    switch (state) {
      case 'returning':
        return { maxSpeed: 1.0, accel: 0.08, damping: 0.988, steerMul: 1.0 };
      case 'searching':
        return { maxSpeed: 0.92, accel: 0.06, damping: 0.987, steerMul: 0.95 };
      case 'thinking':
      case 'listening':
        return { maxSpeed: 0.7, accel: 0.05, damping: 0.984, steerMul: 0.78 };
      case 'concerned_degraded':
        return { maxSpeed: 0.52, accel: 0.04, damping: 0.98, steerMul: 0.7 };
      case 'aware':
        return { maxSpeed: 0.8, accel: 0.05, damping: 0.985, steerMul: 0.82 };
      case 'calm_idle':
      default:
        return { maxSpeed: 0.64, accel: 0.04, damping: 0.983, steerMul: 0.74 };
    }
  }

  logTelemetry(payload) {
    if (this.debug || globalThis.ORB_DEBUG) {
      console.log('[COMPANION_INTENT]', payload);
    }
  }
}

module.exports = CompanionIntent;
