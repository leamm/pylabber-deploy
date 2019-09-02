[program:pylabber-gunicorn-django]
directory={WORK_DIR}
command={PYENV_GUNICORN_EXEC} -w 4 pylabber.wsgi --bind {GUNICORN_BIND}
user={USER}
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/supervisor/pylabber-gunicorn-django.log
environment={ENV_VARS}
