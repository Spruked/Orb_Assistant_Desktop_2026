# Memory

A.I.M.S. (`memory/aims`) is the Vault Logic System's single memory authority. The template's
placeholder matrix store and domain files were removed so that no second copy of memory exists.

- Configuration: `memory/aims_binding.yaml`
- Access: `memory/provider.py` (`get_memory()`), one process-wide instance, one store path
- Tiers: short-term cache (volatile, decaying) and long-term ledger (append-only, hash and Glyph chained),
  plus the Vault (A Priori / A Posteriori atoms) and the SKG
- Maintenance ("consolidation"): `memory/consolidation.py` runs the A.I.M.S. maintenance cycle
- Persistent data lives outside the repository (`ORB_AIMS_STORE_PATH`)
