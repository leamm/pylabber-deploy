import os
from fabric import task

PYLABBER_REPO = 'https://github.com/ZviBaratz/pylabber.git'
VUELABBER_REPO = 'https://github.com/ZviBaratz/vuelabber.git'
USER = 'user'
WORK_DIR = f'/home/{USER}/pylabber'
VUELABBER_WORK_DIR = f'/home/{USER}/vuelabber'
PYTHON_VERSION = '3.6.9'
DOT_ENV_FILE = os.path.join(WORK_DIR, '.env')

PYENV_NAME = 'pylabber'
PYENV_BASHRC = f"""export PATH="/home/{USER}/.pyenv/bin:$PATH"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"
"""
PYENV_EXEC = f'/home/{USER}/.pyenv/bin/pyenv'
PYENV_PIP_EXEC = f'/home/{USER}/.pyenv/versions/{PYENV_NAME}/bin/pip'
PYENV_PYTHON_EXEC = f'/home/{USER}/.pyenv/versions/{PYENV_NAME}/bin/python'
PYENV_GUNICORN_EXEC = f'/home/{USER}/.pyenv/versions/{PYENV_NAME}/bin/gunicorn'

PG_USER = 'pylabber'
PG_DATABASE = 'pylabber'
PG_PASSWORD = 'CbdjoK9A3xH4'

SUPERVISOR_CONFIG_TPL = 'supervisor.conf.tpl'
NGINX_CONFIG_TPL = 'nginx.conf.tpl'
NGINX_SERVER_NAME = 'pylabber-test1'
GUNICORN_BIND = '127.0.0.1:8000'
PYLABBER_PORT = 8080
VUELABBER_PORT = 80

SUPERUSER_LOGIN = 'admin'
SUPERUSER_PASS = 'q1w2e3zaxscd'

ENV_VARS = {
    'DEBUG': False,
    'DB_NAME': PG_DATABASE,
    'DB_USER': PG_USER,
    'DB_PASSWORD': PG_PASSWORD,
}


@task
def prepare_os(c):
    c.sudo('locale-gen')
    c.sudo('DEBIAN_FRONTEND=noninteractive sudo apt-get -y update && sudo apt-get -y upgrade')
    c.sudo('apt-get install -y git build-essential libreadline-dev zlib1g-dev libssl-dev libbz2-dev libsqlite3-dev'
           ' libffi-dev')


@task
def prepare_postgres(c):
    c.sudo('apt-get install -y postgresql-10 libpq-dev')
    c.sudo(f'psql -c "CREATE USER {PG_USER} WITH PASSWORD \'{PG_PASSWORD}\';"'
           f' -c "CREATE DATABASE {PG_DATABASE};"'
           f' -c "GRANT ALL ON DATABASE {PG_DATABASE} TO {PG_USER}"', user='postgres')


@task
def install_pyenv(c):
    if c.run(f'test -d /home/{USER}/.pyenv', warn=True).failed:
        c.run('curl https://pyenv.run | bash')

    c.run(f'grep pyenv -q ~/.bashrc || echo \'{PYENV_BASHRC}\' >> ~/.bashrc')


@task
def create_venv(c):
    c.run(f'{PYENV_EXEC} update')
    c.run(f'{PYENV_EXEC} install {PYTHON_VERSION} --skip-existing')
    c.run(f'{PYENV_EXEC} virtualenvs --bare | grep ^{PYENV_NAME}$ ||'
          f' {PYENV_EXEC} virtualenv {PYTHON_VERSION} {PYENV_NAME}')


@task
def create_workdirs(c):
    c.run(f'mkdir -p {WORK_DIR} {VUELABBER_WORK_DIR}')

    vuelabber_dotgit_dir = os.path.join(WORK_DIR, '.git')
    if c.run(f'test -d {vuelabber_dotgit_dir}', warn=True).failed:
        c.run(f'git clone {PYLABBER_REPO} {WORK_DIR}')

    pylabber_dotgit_dir = os.path.join(VUELABBER_WORK_DIR, '.git')
    if c.run(f'test -d {pylabber_dotgit_dir}', warn=True).failed:
        c.run(f'git clone {VUELABBER_REPO} {VUELABBER_WORK_DIR}')


@task
def install_requirements(c):
    with c.cd(WORK_DIR):
        c.run(f'{PYENV_PIP_EXEC} install --upgrade pip setuptools')
        # TODO: fix setup.py at django_mri package: rid of requirements file reading to set dependencies
        c.run(f'rm -rf /tmp/django_mri_repo &&'
              f' git clone https://github.com/ZviBaratz/django_mri.git /tmp/django_mri_repo &&'
              f' sed -i "/^http.*$/d" /tmp/django_mri_repo/requirements/common.txt &&'
              f' {PYENV_PIP_EXEC} install /tmp/django_mri_repo/ &&'
              f' rm -rf /tmp/django_mri_repo')
        c.run(f'cat requirements/common.txt | grep -v django_mri | xargs {PYENV_PIP_EXEC} install')
        c.run(f'{PYENV_PIP_EXEC} install -r requirements/dev.txt')
        c.run(f'{PYENV_PIP_EXEC} install treebeard')


@task
def create_dotenv(c, force=False):
    if force or c.run(f'test -f {DOT_ENV_FILE}', warn=True).failed:
        c.run(f'rm -rf {DOT_ENV_FILE}')
        for name, value in ENV_VARS.items():
            c.run(f'echo "{name}={value}" >> {DOT_ENV_FILE}')


@task
def db_migrate(c):
    with c.cd(WORK_DIR):
        # TODO: add env.read_env(os.path.join(BASE_DIR, '.env')) to settings.py
        c.run(f'export $(cat .env | xargs) &&'
              f' {PYENV_PYTHON_EXEC} ./manage.py makemigrations &&'
              f' {PYENV_PYTHON_EXEC} ./manage.py migrate')


@task
def collect_static(c):
    with c.cd(WORK_DIR):
        c.run('mkdir -p static dist node_modules')
        c.run(f'{PYENV_PYTHON_EXEC} ./manage.py collectstatic --no-input')


@task
def configure_gunicorn(c):
    with c.cd(WORK_DIR):
        c.run(f'{PYENV_PIP_EXEC} install gunicorn')


@task
def configure_supervisor(c):
    c.sudo('apt-get install -y supervisor')
    remote_tpl_file = f'/tmp/{SUPERVISOR_CONFIG_TPL}'
    c.put(SUPERVISOR_CONFIG_TPL, '/tmp/')
    config_params = {
        'WORK_DIR': WORK_DIR,
        'PYENV_GUNICORN_EXEC': PYENV_GUNICORN_EXEC,
        'USER': USER,
        'GUNICORN_BIND': GUNICORN_BIND,
        'ENV_VARS': ','.join(f'{k}={v}' for k, v in ENV_VARS.items())
    }
    for k, v in config_params.items():
        c.run('sed -i "s/{{{k}}}/{v}/g" {remote_tpl_file}'.format(
            k=k,
            v=v.replace('/', r'\/'),
            remote_tpl_file=remote_tpl_file,
        ))
    c.sudo(f'mv {remote_tpl_file} /etc/supervisor/conf.d/pylabber.conf')
    c.sudo('supervisorctl update')


@task
def configure_nginx(c):
    c.sudo('apt-get install -y nginx')
    remote_tpl_file = f'/tmp/{NGINX_CONFIG_TPL}'
    c.put(NGINX_CONFIG_TPL, '/tmp/')
    config_params = {
        'WORK_DIR': WORK_DIR,
        'VUELABBER_WORK_DIR': os.path.join(VUELABBER_WORK_DIR, 'dist'),
        'NGINX_SERVER_NAME': NGINX_SERVER_NAME,
        'PYLABBER_PORT': str(PYLABBER_PORT),
        'VUELABBER_PORT': str(VUELABBER_PORT),
        'GUNICORN_BIND': GUNICORN_BIND,
    }
    for k, v in config_params.items():
        c.run('sed -i "s/{{{k}}}/{v}/g" {remote_tpl_file}'.format(
            k=k,
            v=v.replace('/', r'\/'),
            remote_tpl_file=remote_tpl_file,
        ))
    c.sudo(f'mv {remote_tpl_file} /etc/nginx/sites-available/pylabber')
    c.sudo('sudo ln -sf /etc/nginx/sites-available/pylabber /etc/nginx/sites-enabled/pylabber')
    c.sudo('service nginx reload')


@task
def create_superuser(c):
    with c.cd(WORK_DIR):
        c.run(f'export $(cat .env | xargs) && {PYENV_PYTHON_EXEC} manage.py shell -c '
              f'"from django.contrib.auth import get_user_model; User = get_user_model();'
              f'User.objects.filter(username=\'{SUPERUSER_LOGIN}\').exists() or '
              f'User.objects.create_superuser(\'{SUPERUSER_LOGIN}\', \'admin@example.com\', \'{SUPERUSER_PASS}\')"')


@task
def npm_build(c):
    c.sudo('apt-get install -y npm')
    # TODO: rid of hardcoded config params at vuelabber(src/api/base_url.js)
    base_url_conf_file = os.path.join(VUELABBER_WORK_DIR, 'src/api/base_url.js')
    prod_base_url = f'http://{NGINX_SERVER_NAME}:{PYLABBER_PORT}/api'.replace('/', r'\/')
    c.run(f"""sed -i "s/const PRODUCTION =.*/const PRODUCTION = '{prod_base_url}'/g" {base_url_conf_file}""")
    c.run(f"""sed -i "s/const MODE.*$/const MODE = \'production\'/g" {base_url_conf_file}""")
    with c.cd(VUELABBER_WORK_DIR):
        c.run('npm install && npm run build')


@task
def deploy(c):
    prepare_os(c)
    prepare_postgres(c)
    install_pyenv(c)
    create_venv(c)
    create_workdirs(c)
    install_requirements(c)
    create_dotenv(c)
    db_migrate(c)
    collect_static(c)
    configure_gunicorn(c)
    configure_supervisor(c)
    configure_nginx(c)
    create_superuser(c)
    npm_build(c)

# TODO: vue frontend deploy
# TODO: localdev
