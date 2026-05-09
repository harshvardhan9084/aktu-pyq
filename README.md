# AKTU PYQ Intelligence System
> Zero cost, step-by-step setup guide.

## Stack overview
```
frontend/   Next.js 14  →  Vercel (free)
backend/    FastAPI      →  Render (free)
database    Supabase     →  free tier
```

---

## STEP 1 — GitHub (5 min)
1. https://github.com → Sign up → New repository → name: `aktu-pyq` → **Private** → Create
2. Install Git: https://git-scm.com/downloads
3. In terminal:
```bash
cd path/to/aktu-pyq
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_USERNAME/aktu-pyq.git
git push -u origin main
```

---

## STEP 2 — Supabase database (10 min)
1. https://supabase.com → Sign up with GitHub → New project → name: `aktu-pyq`
2. Region: **Singapore** (closest to India)
3. Wait ~2 min → go to **SQL Editor** → paste contents of `backend/schema.sql` → **Run**
4. Go to **Settings → API** → copy:
   - `Project URL` → `SUPABASE_URL`
   - `anon public` key → `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `service_role` key → `SUPABASE_SERVICE_KEY` *(keep secret!)*
5. Go to **Storage** → New bucket → name: `pdf-uploads` → **Private**

---

## STEP 3 — Backend on Render (15 min)
1. https://render.com → Sign up with GitHub → New → Web Service
2. Connect `aktu-pyq` repo → configure:
   - Root Directory: `backend`
   - Runtime: Python 3
   - Build Command: `apt-get install -y tesseract-ocr poppler-utils && pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
3. Add environment variables:
   ```
   SUPABASE_URL          = (your Supabase URL)
   SUPABASE_SERVICE_KEY  = (service role key)
   ALLOWED_ORIGINS       = https://your-app.vercel.app
   ADMIN_API_TOKEN       = (invent a long random string, e.g. Ak7xM2pL9nQ4)
   ```
4. Deploy → wait ~5 min → copy your URL: `https://aktu-pyq-backend.onrender.com`

> ⚠️ Free Render services sleep after 15 min. First request after sleep = ~30s delay. Fine for MVP.

---

## STEP 4 — Frontend on Vercel (10 min)
1. https://vercel.com → Sign up with GitHub → Add New Project → import `aktu-pyq`
2. Root Directory: `frontend`  |  Framework: Next.js
3. Add environment variables:
   ```
   NEXT_PUBLIC_SUPABASE_URL      = (Supabase URL)
   NEXT_PUBLIC_SUPABASE_ANON_KEY = (anon key)
   NEXT_PUBLIC_BACKEND_URL       = (your Render URL)
   ADMIN_PASSWORD_HASH           = (see Step 5)
   ```
4. Deploy → live in ~2 min at `https://aktu-pyq.vercel.app`

---

## STEP 5 — Set admin password
Your admin panel: `https://your-app.vercel.app/admin/x7k2`

1. Go to https://codebeautify.org/sha256-hash-generator
2. Type your password → Hash → copy the result
3. In Vercel → Settings → Environment Variables → set `ADMIN_PASSWORD_HASH` = that hash
4. Redeploy (Vercel auto-redeploys on env var change)

---

## STEP 6 — Connect to WordPress
In WordPress, add HTML block to any page:
```html
<iframe src="https://your-app.vercel.app"
  width="100%" height="800px"
  frameborder="0" style="border-radius:8px;">
</iframe>
```
Or just link to your Vercel URL.

---

## Testing
1. Visit Vercel URL → search page loads
2. Try search → empty results (no data yet — correct)
3. Visit `/admin/x7k2` → enter password
4. Go to Upload tab → upload one AKTU PDF → fill subject + year → Upload & Process
5. Wait 30–60 sec → Overview tab shows question count
6. Search for that subject → questions appear ✓

---

## File map
```
aktu-pyq/
├── frontend/
│   ├── app/
│   │   ├── page.tsx                    ← Student homepage
│   │   ├── contribute/page.tsx         ← Upload + donate
│   │   ├── layout.tsx
│   │   ├── globals.css
│   │   └── admin/x7k2/
│   │       ├── page.tsx                ← Admin login (hidden URL)
│   │       └── dashboard/page.tsx      ← Full admin panel
│   ├── app/api/admin/
│   │   ├── auth/route.ts               ← Login endpoint
│   │   ├── verify/route.ts             ← Session check
│   │   └── logout/route.ts
│   ├── components/
│   │   ├── Navbar.tsx
│   │   ├── NaturalSearch.tsx           ← Free-text search
│   │   ├── DynamicForm.tsx             ← Step-by-step filter
│   │   └── ResultsList.tsx             ← Results with frequency
│   ├── lib/supabase.ts
│   ├── tailwind.config.js
│   ├── next.config.js
│   ├── tsconfig.json
│   └── .env.example                   ← Copy to .env.local
│
└── backend/
    ├── main.py                         ← FastAPI entry point
    ├── schema.sql                      ← Run once in Supabase
    ├── requirements.txt
    ├── render.yaml                     ← Render config
    ├── .env.example                   ← Copy to .env
    ├── services/
    │   ├── embedding.py               ← Sentence Transformers
    │   ├── vector_db.py               ← ChromaDB
    │   ├── pdf_processor.py           ← OCR + extraction
    │   └── clustering.py             ← DBSCAN clustering
    └── routers/
        ├── search.py                  ← Search endpoints
        ├── upload.py                  ← Student submission
        └── admin.py                  ← Admin operations
```

---

## All costs: ₹0
| Service   | Tier  | Limits |
|-----------|-------|--------|
| Vercel    | Free  | Unlimited deploys, 100 GB/mo bandwidth |
| Render    | Free  | 750 hrs/mo, sleeps after 15 min inactivity |
| Supabase  | Free  | 500 MB DB, 1 GB storage, 50k rows |
| ChromaDB  | Free  | Runs inside Render, no separate service |
| Tesseract | Free  | Open-source OCR |
| ST Model  | Free  | all-MiniLM-L6-v2, ~90 MB, downloads once |
