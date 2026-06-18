# Orb Assistant Desktop

This is a sovereign ORB instance provisioned from the WSL forge copy.

Identity
- `instance_id`: `desktop`
- `app_id`: `com.orbassistant.desktop`
- `shared_mesh_root`: `/mnt/r/R_Drive_Substrate/orb_mesh`

Runtime
- Launch with `./launch_desktop_orb.sh`
- On Windows, launch with `launch_desktop_orb.ps1` if Node and Python are installed there
- Local user data lives in `/mnt/r/Orb_Assistant_Desktop/.orb-assistant-desktop`
- Local CALI system data lives under `/mnt/r/Orb_Assistant_Desktop/system/CALI_System`

Notes
- This instance is designed to coexist with the WSL ORB.
- It shares through the mesh, but it does not depend on the WSL ORB to boot.
