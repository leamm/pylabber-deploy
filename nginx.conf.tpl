server {
    listen 80;
    server_name {NGINX_SERVER_NAME};
    access_log  /var/log/nginx/pylabber-django.access.log;
    error_log /var/log/nginx/pylabber-django.error.log;

    location / {
        proxy_pass http://{GUNICORN_BIND};
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /static {
        alias {WORK_DIR}/staticfiles;
    }
}