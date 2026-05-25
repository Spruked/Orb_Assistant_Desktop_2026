export const OrbService = {
  /**
   * Send a message to the unified ORB core interface.
   * Dynamically routes to local Electron IPC or Remote Web API.
   * @param {string} text - User prompt
   * @param {Function} onPulse - Callback to trigger UI color changes based on the "leading_mind"
   */
  async sendMessage(text, onPulse) {
    if (typeof window !== 'undefined' && window.electronAPI) {
      // ------------------------------------------
      // Desktop Path: Talk to local Python bridge
      // ------------------------------------------
      if (onPulse) onPulse("white", "processing"); // General processing pulse
      
      const response = await window.electronAPI.sendToOrb(text);
      return response;
    } else {
      // ------------------------------------------
      // Web Path: Talk to FastAPI backend
      // ------------------------------------------
      try {
        if (onPulse) onPulse("white", "processing"); 

        const response = await fetch('/api/v1/tribunal', { // Adjust host for production vs proxy
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt: text, context: {} })
        });
        
        if (!response.ok) throw new Error("Network response was not ok");
        
        const data = await response.json();
        
        // Trigger specific color pulse based on whichever philosopher won the shadow trace
        if (onPulse && data.metadata && data.metadata.leading_mind) {
          const mindColors = {
            "spinoza": "#00ffcc",  // Cyan for Monism
            "kant": "#ff00ff",     // Magenta for Critical/Moral
            "hume": "#ffaa00",     // Orange for Skepticism
            "locke": "#00ff00"     // Green for Empiricism
          };
          const color = mindColors[data.metadata.leading_mind] || "white";
          onPulse(color, data.metadata.leading_mind);
        }
        
        return data;
      } catch (error) {
        console.error("OrbService Error:", error);
        return { error: true, message: error.message };
      }
    }
  }
};
