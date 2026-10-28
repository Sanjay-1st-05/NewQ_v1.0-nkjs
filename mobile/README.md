# NewQ Mobile Afternoon Demo

## Run on Android phone
Install **Expo Go** on the phone. On the PC:

```powershell
cd mobile
npm install
npx expo start
```

Scan the QR code in Expo Go. If LAN discovery fails:

```powershell
npx expo start --tunnel
```

The mobile app defaults to `DEMO_MODE=true`, so today's demo works without a server connection. It demonstrates the News → Analysis → Questions → Quiz → Score flow.

### Production stack
- Frontend: React Native
- Backend: Node.js + Express.js
- AI/ML: Python
- Database: Firebase

When the backend is ready, set `DEMO_MODE=false` in `src/api.js` and set `API_BASE_URL` to the PC's LAN IP.
