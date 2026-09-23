# Apne Server Par Host Karna (Hinglish)

Ye guide un logon ke liye hai jinke paas **apna VPS** hai (Hetzner,
DigitalOcean, Contabo, AWS EC2 — koi bhi jisme SSH aur root mile).

Shared hosting (cPanel, Hostinger, GoDaddy) par ye project nahi chalega —
wahan Redis nahi milta aur WebSocket band hote hain, jo is product ki jaan
hain.

---

## Server par kya chahiye

| Cheez | Kitna |
|---|---|
| RAM | 2 GB kaam chala lega, **4 GB behtar** |
| CPU | 2 vCPU |
| Disk | 20 GB |
| OS | Ubuntu 22.04 ya 24.04 |
| Docker | install karna hoga (neeche command hai) |
| Domain | ek domain, do subdomain (`api.` aur `app.`) |

Postgres, Redis, Python, Node — **kuch alag se install nahi karna.** Sab
Docker ke andar aa jayega.

---

## Step 1 — Docker install karein

SSH se server par jaakar:

```bash
curl -fsSL https://get.docker.com | sh
docker --version
docker compose version
```

Dono version dikh jayein to aage badhein.

---

## Step 2 — DNS set karein

Apne domain ke DNS panel mein do A record banayein, dono server ke IP par:

```
api.yourdomain.com   ->  <server ka IP>
app.yourdomain.com   ->  <server ka IP>
```

Phailne mein 5-30 minute lag sakte hain.

---

## Step 3 — Code server par laayein

```bash
cd /opt
git clone https://github.com/Aatif-oasis/oasis-chatbot.git
cd oasis-chatbot
```

Private repo hai to GitHub token maangega. Ya zip upload kar dein:
```bash
# apne laptop se
scp oasis_chatbot.zip root@<server-ip>:/opt/
# server par
cd /opt && unzip oasis_chatbot.zip && cd oasis_chatbot
```

---

## Step 4 — Config banayein

```bash
cp deploy/.env.example deploy/.env
nano deploy/.env
```

Paanch cheezein bharni hain:

```
POSTGRES_PASSWORD=<koi lamba password, @ : / # ke bina>
JWT_SECRET_KEY=<random string>
SIGNUP_SETUP_KEY=<random string>
ALLOWED_ORIGINS=["https://app.yourdomain.com"]
PUBLIC_API_URL=https://api.yourdomain.com
```

Random string banane ke liye:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

`Ctrl+O`, `Enter`, `Ctrl+X` se save karein.

---

## Step 5 — SSL certificate lein

```bash
apt install -y certbot
certbot certonly --standalone -d api.yourdomain.com -d app.yourdomain.com

mkdir -p deploy/certs
cp /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem deploy/certs/
cp /etc/letsencrypt/live/api.yourdomain.com/privkey.pem deploy/certs/
```

SSL zaroori hai — **HTTPS ke bina WebSocket nahi chalte**, aur real-time
chat khatam ho jayegi.

---

## Step 6 — nginx config

```bash
cp deploy/nginx.conf.example deploy/nginx.conf
nano deploy/nginx.conf
```

`api.yourdomain.example` aur `app.yourdomain.example` ki jagah apne asli
domain daal dein (chaar jagah hain).

---

## Step 7 — Chalayein

```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

Pehli baar 5-10 minute lagenge (images build honge). Phir:

```bash
docker compose -f deploy/docker-compose.prod.yml ps
```

Sab `running` dikhne chahiye.

---

## Step 8 — System roles daalein (sirf pehli baar)

```bash
docker compose -f deploy/docker-compose.prod.yml exec backend python -m app.seed
```

Migrations apne aap chal jaati hain, par ye **manually** chalana hai. Bina
iske organization register nahi hoga.

---

## Step 9 — Pehla admin banayein

```bash
docker compose -f deploy/docker-compose.prod.yml exec backend python -m app.create_org
```

Ye poochhega organization ka naam, admin ka naam, email, password
(typing chhupi rahegi). Aakhir mein widget ka slug bata dega.

Ye tareeka API se behtar hai — password kahin log mein nahi jaata.

---

## Step 10 — Chala kar dekhein

```
Dashboard : https://app.yourdomain.com/login
API health: https://api.yourdomain.com/api/health
Widget    : https://app.yourdomain.com/demo.html
```

Teen cheezein test karein:

1. **Login** — jo admin abhi banaya
2. **Chat** — widget se message bhejein, dashboard mein aaya?
3. **Real-time** — dashboard ko chhue bina widget se message bhejein.
   Bina refresh ke aa gaya = sab theek.

---

## Client ki website par widget lagana

Us website ke `</body>` se pehle:

```html
<script
  src="https://app.yourdomain.com/oasis-chatbot-widget.js"
  data-org-slug="client-ka-slug"
  data-api-base="https://api.yourdomain.com"
  data-title="Welcome!"
  data-subtitle="How can we help?"
  data-agent-name="Support Team"
  data-topics="Order status,Returns,Warranty">
</script>
```

**Zaroori:** us website ka domain `ALLOWED_ORIGINS` mein jodna padega,
warna browser API call block kar dega:

```
ALLOWED_ORIGINS=["https://app.yourdomain.com","https://client-ki-website.com"]
```

Badalne ke baad:
```bash
docker compose -f deploy/docker-compose.prod.yml up -d backend
```

---

## Rozana ke command

```bash
cd /opt/oasis-chatbot

# Logs dekhein
docker compose -f deploy/docker-compose.prod.yml logs -f backend

# Restart
docker compose -f deploy/docker-compose.prod.yml restart backend

# Naya code aane par
git pull
docker compose -f deploy/docker-compose.prod.yml up -d --build

# Database ka backup
docker compose -f deploy/docker-compose.prod.yml exec postgres \
  pg_dump -U oasis_chatbot oasis_chatbot > backup-$(date +%F).sql
```

Backup ka command **cron mein daal dein**. Server kabhi bhi ja sakta hai,
aur chat history dobara nahi banti.

---

## SSL renew (har 60-80 din)

```bash
certbot renew
cp /etc/letsencrypt/live/api.yourdomain.com/*.pem /opt/oasis-chatbot/deploy/certs/
docker compose -f deploy/docker-compose.prod.yml restart nginx
```

Ise bhi cron mein daal dein, warna ek din chat achanak band ho jayegi aur
wajah samajh nahi aayegi.

---

## Kuch atke to

**Backend start nahi ho raha**
```bash
docker compose -f deploy/docker-compose.prod.yml logs backend
```
Aam wajah: `.env` mein koi value nahi bhari.

**Login par CORS error** — `ALLOWED_ORIGINS` mein dashboard ka poora URL
hona chahiye, aakhir mein slash ke bina.

**Chat real-time nahi hai** — nginx ka WebSocket wala block sahi lagega
hai ya nahi dekhein, aur HTTPS chal raha hai ya nahi.

**Dashboard purana API URL dhoondh raha hai** — `PUBLIC_API_URL` build ke
waqt bundle mein bake hota hai. Badla hai to rebuild karein:
```bash
docker compose -f deploy/docker-compose.prod.yml up -d --build dashboard
```
