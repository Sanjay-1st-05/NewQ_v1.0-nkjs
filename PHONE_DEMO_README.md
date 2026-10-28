# Phone Demo Quick Start

1. Extract the project.
2. **Start the backend on your PC**: double-click `run_backend.bat` (or run
   `python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000` from an
   activated venv). The `--host 0.0.0.0` flag is required so phones on the
   same Wi-Fi can connect.
3. **Allow the connection through Windows Firewall** (first time only, admin
   PowerShell):

   ```powershell
   New-NetFirewallRule -DisplayName 'NewQ Backend (TCP 8000)' -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Any
   ```

4. Verify the PC's Wi-Fi IP matches `API_BASE_URL` in `mobile/src/api.js`
   (check with `ipconfig`; hotspot IPs change — e.g. it has been
   `http://10.117.184.17:8000`, later `http://10.221.164.17:8000`).
   If it changed, update `API_BASE_URL` and reload the app.
5. Open PowerShell in `NewQ\mobile`.
6. Run `npm install`.
7. Run `npx expo start`.
8. Install Expo Go on the Android phone.
9. Scan the QR code.
10. The app opens with sample RBI news. Tap **Analyze News → Start Quiz**.
