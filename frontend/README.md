# File Vault frontend

`app/page.tsx` is the password and Google sign-in page. `app/dashboard/page.tsx` checks the app JWT with FastAPI before rendering `DashboardClient.tsx`. `lib/api.ts` sends credentialed requests to the backend.

Run `npm install`, `npm run dev`, and `npm test` from this directory. The backend URL defaults to `http://localhost:8000`; override it with `NEXT_PUBLIC_API_BASE_URL` if needed. Keep the frontend and backend on the same hostname so the browser and the Next.js server can send the host-only JWT cookie.
