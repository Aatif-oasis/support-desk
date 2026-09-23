# Support Desk — Bilkul Nayi Shuruaat (Hinglish)

Ye guide maan kar chalti hai ki system par purana kuch nahi rakhna. Har
step kram se chalayein.

Ek baat pehle jaan lein, kyunki aapke system par ye baar-baar takraayegi:
**Windows ki Application Control policy `pip.exe` aur `uvicorn.exe` jaise
chhote launcher programs ko block karti hai.** Python khud allowed hai.
Isliye is guide mein har jagah `py -3 -m pip` aur `py -3 -m uvicorn`
likha hai — `.exe` chalane ki koshish hi nahi hoti.

---

## Step 1 — Purana sab hatayein

```powershell
Get-NetTCPConnection -LocalPort 8000, 3000 -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
Stop-Process -Name python, node -Force -ErrorAction SilentlyContinue
```

Purane project folders dekh lein:

```powershell
Get-ChildItem D:\ -Directory | Where-Object { $_.Name -match "oasis|chat_support|clean|temp|unzipped" } | Select-Object Name
```

List theek lage to hata dein:

```powershell
Get-ChildItem D:\ -Directory | Where-Object { $_.Name -match "oasis|chat_support|clean|temp|unzipped" } | Remove-Item -Recurse -Force
```

**Rukiye:** agar `D:\oasis_chatbot` mein aapka git repo hai aur usmein
kaam GitHub par push nahi hua, to pehle push kar lein. Delete ke baad wo
commits wapas nahi aate.

Purane database bhi hata dein:

```powershell
$env:PGPASSWORD = "<postgres ka password>"
$psql = "C:\Program Files\PostgreSQL\18\bin\psql.exe"

& $psql -U postgres -h localhost -c "DROP DATABASE IF EXISTS oasis_test;"
& $psql -U postgres -h localhost -c "DROP DATABASE IF EXISTS oasis_chatbot;"
& $psql -U postgres -h localhost -c "DROP DATABASE IF EXISTS chat_support;"
```

---

## Step 2 — Naya database

```powershell
& $psql -U postgres -h localhost -c "CREATE USER support_desk WITH PASSWORD 'SupportPass123';"
& $psql -U postgres -h localhost -c "CREATE DATABASE support_desk OWNER support_desk;"
$env:PGPASSWORD = ""
```

Alag user isliye, taaki is project ki pahunch kisi purane database tak ho
hi na sake — connection string galti se purani reh jaye to permission
denied milega, chup-chaap purana data nahi khulega.

---

## Step 3 — Sahi Python dhoondhein

Aapke system par ek se zyada Python hain, aur unme se sirf kuch ke paas
project ke packages honge. Pehle dekh lein kaun-kaun hai:

```powershell
py -0
```

Phir project ke packages install karein (ek hi baar):

```powershell
cd D:\support_desk\backend
py -3 -m pip install -r requirements.txt
```

Ye bhi block ho jaye to:

```powershell
py -3 -m pip install --user -r requirements.txt
```

Jaanch lein ki lag gaye:

```powershell
py -3 -c "import sqlalchemy, fastapi, uvicorn; print('packages ready')"
```

`packages ready` aana chahiye.

Note: virtualenv (`venv`) jaan-boojh kar nahi bana rahe. Us par ye policy
`pip.exe` aur `uvicorn.exe` dono block kar deti hai, aur har command
atakti hai. Ek machine, ek project — seedha Python theek hai.

---

## Step 4 — Project rakhein

```powershell
Expand-Archive -Force "$env:USERPROFILE\Downloads\support-desk.zip" "D:\temp_sd"
Move-Item "D:\temp_sd\support_desk" "D:\support_desk"
Remove-Item "D:\temp_sd" -Recurse -Force

Test-Path D:\support_desk\backend\app\main.py
```

Aakhri line `True` aani chahiye.

---

## Step 5 — Config

```powershell
Copy-Item D:\support_desk\backend\.env.example D:\support_desk\backend\.env
py -3 -c "import secrets; print(secrets.token_urlsafe(48))"
notepad D:\support_desk\backend\.env
```

Do line badalni hain:

```
DATABASE_URL=postgresql+asyncpg://support_desk:SupportPass123@localhost:5432/support_desk
JWT_SECRET_KEY=<upar wali random string>
```

`ALLOWED_ORIGINS` aisi honi chahiye — port badalna ho to yahi line
badlegi:

```
ALLOWED_ORIGINS=["http://localhost:3000","null"]
```

Dashboard ka config:

```powershell
"NEXT_PUBLIC_API_BASE=http://localhost:8000" | Set-Content D:\support_desk\dashboard\.env.local
```

---

## Step 6 — Database taiyaar karein

```powershell
cd D:\support_desk\backend
py -3 -m alembic upgrade head
py -3 -m app.seed
```

`app.seed` system roles banata hai. Bina iske organization ban hi nahi
sakti.

---

## Step 7 — Apna admin banayein

```powershell
py -3 -m app.create_org
```

Poochhega: organization ka naam, admin ka naam, email, password (typing
chhupi rahegi). Aakhir mein **widget ka slug** bata dega — likh lein.

`app.seed_demo` mat chalayein: wo `admin@demo.com` / `DemoPass123` banata
hai, jo purane setup ka account tha.

---

## Step 8 — Dashboard ke packages

```powershell
cd D:\support_desk\dashboard
npm install
```

---

## Step 9 — Chalayein

```powershell
cd D:\support_desk
powershell -ExecutionPolicy Bypass -File run.ps1
```

Ye khud hi sahi Python dhoondhta hai, ports khali karta hai, aur dono
server alag window mein chalu kar deta hai.

Haath se chalana ho to:

```powershell
# window 1
cd D:\support_desk\backend
py -3 -m uvicorn app.main:app --reload

# window 2
cd D:\support_desk\dashboard
npm run dev
```

Login: `http://localhost:3000/login` — wahi email aur password jo Step 7
mein banaya.

---

## Step 10 — Widget

```powershell
notepad D:\support_desk\widget\demo.html
```

`data-org-slug="REPLACE-WITH-YOUR-SLUG"` mein Step 7 wala slug daalein.
Phir:

```powershell
cd D:\support_desk\dashboard
node scripts/copy-widget.js
```

Widget: `http://localhost:3000/demo.html`

Browser console (`F12`) mein ek baar ye chala lein, taaki purane install
ka visitor data saaf ho jaye:

```javascript
localStorage.clear(); sessionStorage.clear(); location.reload();
```

---

## IP restriction kaise use karein

Users page par har agent ke aage **Sign-in location** ki column hai.

1. Admin office se login kare
2. Page ke upar apna IP dikhega — wahi copy karein
3. Agent ke aage **Restrict** dabakar wo IP daal dein

Ab wo agent sirf usi IP se login karega. Kahin shift ho jaye to
**Change** se naya IP; kuch din ghar se kaam karna ho to field khali
karke Save — phir wo kahin se bhi login karega.

Galat jagah se koshish par us agent ke neeche amber mein dikhega:
*"Blocked from 198.51.100.77"*.

**Admin par ye rok kabhi nahi lagti** — uske aage "Anywhere
(administrator)" likha aata hai. Warna admin apna IP galat daal kar khud
hamesha ke liye bahar ho jaata, aur usko wapas laane wala koi nahi hota.

Router ka andar wala IP (`192.168.x.x`) mat daalna — wo server tak
pahunchta hi nahi. Isi liye page par aapka asli IP dikhaya jaata hai.

Live server par nginx ke peeche `.env` mein `TRUST_FORWARDED_FOR=true`
karna hoga, warna har agent ka IP nginx ka IP dikhega.

---

## Kuch atke to

**"Application Control policy has blocked this file"** — `.exe` chalane
ki koshish hui. Har jagah `py -3 -m <naam>` use karein.

**"No module named sqlalchemy"** — galat Python chal raha hai. Step 3
dobara karein, aur wahi `py -3` istemaal karein jisne "packages ready"
kaha tha.

**Login par "Failed to fetch"** — backend chal raha hai ya nahi:
```powershell
Invoke-RestMethod "http://localhost:8000/api/health"
```
Chal raha ho to browser ka address `http://localhost:3000` hona chahiye
(`127.0.0.1` ya network IP nahi), warna CORS rok dega.

**Purana server chal raha hai** — `run.ps1` khud hata deta hai, par haath
se dekhna ho:
```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { Get-Process -Id $_.OwningProcess | Select-Object Id, Path, StartTime }
```
`StartTime` purana dikhe to wahi wajah hai.
