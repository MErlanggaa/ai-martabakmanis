# Panduan Deployment Server AI (FastAPI)

Panduan ini menjelaskan cara menjalankan server AI secara terus-menerus di server production.

## 🚀 Opsi Deployment

### 1. **Docker (Recommended - Termudah)**

#### Persiapan:
```bash
# Pastikan Docker & Docker Compose terinstall
docker --version
docker-compose --version
```

#### Setup:
1. Buat file `.env`:
```bash
GOOGLE_API_KEY=your_api_key_here
GOOGLE_GENAI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

2. Build & Run:
```bash
docker-compose up -d
```

3. Cek status:
```bash
docker-compose ps
docker-compose logs -f
```

4. Stop:
```bash
docker-compose down
```

**Keuntungan:**
- ✅ Auto-restart jika crash
- ✅ Mudah di-deploy ulang
- ✅ Isolasi environment
- ✅ Bisa dijalankan di VPS, Cloud, atau server manapun

---

### 2. **Systemd (Linux VPS - Ubuntu/Debian)**

#### Setup:
1. Copy service file:
```bash
sudo cp systemd/umkm-ai-api.service /etc/systemd/system/
```

2. Edit file dan isi API key:
```bash
sudo nano /etc/systemd/system/umkm-ai-api.service
```

3. Reload & Start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable umkm-ai-api
sudo systemctl start umkm-ai-api
```

4. Cek status:
```bash
sudo systemctl status umkm-ai-api
sudo journalctl -u umkm-ai-api -f
```

5. Restart:
```bash
sudo systemctl restart umkm-ai-api
```

**Keuntungan:**
- ✅ Native Linux service
- ✅ Auto-start saat boot
- ✅ Terintegrasi dengan system log

---

### 3. **Supervisor (Alternative untuk Process Management)**

#### Install:
```bash
sudo apt-get install supervisor
```

#### Setup:
1. Copy config:
```bash
sudo cp supervisor/umkm-ai-api.conf /etc/supervisor/conf.d/
```

2. Edit dan isi API key:
```bash
sudo nano /etc/supervisor/conf.d/umkm-ai-api.conf
```

3. Reload & Start:
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start umkm-ai-api
```

4. Cek status:
```bash
sudo supervisorctl status
sudo supervisorctl tail -f umkm-ai-api
```

**Keuntungan:**
- ✅ Mudah manage multiple processes
- ✅ Web interface (opsional)
- ✅ Auto-restart

---

### 4. **PM2 (Bisa pakai untuk Python)**

#### Install PM2:
```bash
npm install -g pm2
```

#### Setup:
1. Edit `ecosystem.config.js` dan isi API key
2. Start:
```bash
pm2 start ecosystem.config.js
```

3. Auto-start saat boot:
```bash
pm2 startup
pm2 save
```

4. Cek status:
```bash
pm2 status
pm2 logs umkm-ai-api
```

---

## 🌐 Cloud Platform (No-Server Setup)

### **Railway.app**
1. Install Railway CLI: `npm i -g @railway/cli`
2. Login: `railway login`
3. Deploy: `railway up`
4. Set environment variables di dashboard

### **Render.com**
1. Connect GitHub repository
2. Pilih "Web Service"
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn server:app --host 0.0.0.0 --port $PORT`
5. Set environment variables

### **Fly.io**
1. Install: `curl -L https://fly.io/install.sh | sh`
2. Login: `fly auth login`
3. Deploy: `fly launch`
4. Set secrets: `fly secrets set GOOGLE_API_KEY=xxx`

### **DigitalOcean App Platform**
1. Connect GitHub
2. Pilih Python
3. Set build/run commands
4. Add environment variables

---

## 📋 Checklist Sebelum Deploy

- [ ] API Key Google sudah di-set di environment variables
- [ ] Port 8000 (atau port lain) sudah dibuka di firewall
- [ ] Database FAISS sudah ada atau akan dibuat saat pertama kali upload
- [ ] Dependencies sudah terinstall
- [ ] Test API di local dulu dengan Postman
- [ ] Reverse proxy (Nginx) sudah dikonfigurasi (opsional)

---

## 🔧 Nginx Reverse Proxy (Opsional)

Jika ingin pakai domain custom dan HTTPS:

```nginx
server {
    listen 80;
    server_name api-umkm-ai.example.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 🎯 Rekomendasi

**Untuk pemula:** Gunakan **Docker** - paling mudah dan fleksibel.

**Untuk production VPS:** Gunakan **Systemd** - native, stabil, terintegrasi.

**Untuk cloud:** Gunakan **Railway** atau **Render** - gratis tier, auto-deploy dari GitHub.

---

## 📝 Monitoring

Setelah deploy, test endpoint:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/admin/status
```

Pastikan server selalu running dan auto-restart jika crash.


