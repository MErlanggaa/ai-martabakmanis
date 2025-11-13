// PM2 Ecosystem File untuk Node.js PM2 (bisa juga pakai pm2 untuk Python)
module.exports = {
  apps: [{
    name: 'umkm-ai-api',
    script: '.venv/bin/uvicorn',
    args: 'server:app --host 0.0.0.0 --port 8000',
    cwd: '/var/www/umkm-ai',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
    env: {
      GOOGLE_API_KEY: 'YOUR_API_KEY_HERE',
      GOOGLE_GENAI_API_KEY: 'YOUR_API_KEY_HERE',
      GEMINI_MODEL: 'gemini-2.5-flash'
    },
    error_file: './logs/err.log',
    out_file: './logs/out.log',
    log_date_format: 'YYYY-MM-DD HH:mm:ss Z'
  }]
};


