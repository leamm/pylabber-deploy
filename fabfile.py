import os

from fabric import Connection, task

PYLABBER_REPO = 'https://github.com/ZviBaratz/pylabber.git'
VUELABBER_REPO = 'https://github.com/ZviBaratz/vuelabber.git'
VUELABBER_DIST_REPO = 'git@github.com:leamm/vuelabber-dist.git'
PYTHON_VERSION = '3.6.9'

PYENV_NAME = 'pylabber'
PYENV_BASHRC = f"""export PATH="~/.pyenv/bin:$PATH"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"
"""

PG_USER = 'pylabber'
PG_DATABASE = 'pylabber'
PG_PASSWORD = 'CbdjoK9A3xH4'

SUPERVISOR_CONFIG_TPL = 'supervisor.conf.tpl'
NGINX_CONFIG_TPL = 'nginx.conf.tpl'
PYLABBER_LOGGING_CONF = 'logging_conf.py'
VUELABBER_DIST_PATH_LOCAL = 'vuelabber-dist'

GUNICORN_BIND = '127.0.0.1:8000'
PYLABBER_PORT = 80
VUELABBER_PORT = 80

SUPERUSER_LOGIN = 'admin'
SUPERUSER_PASS = 'q1w2e3zaxscd'

MODE_DEV = 'dev'
MODE_PROD = 'prod'


def _is_local(c):
    return not isinstance(c, Connection) or c.host.startswith('127.') or c.host == 'localhost'


def _env_vars(mode):
    return {
        'DEBUG': mode != MODE_PROD,
        'DB_NAME': PG_DATABASE,
        'DB_USER': PG_USER,
        'DB_PASSWORD': PG_PASSWORD,
    }


def _pylabber_workdir(c, mode):
    # TODO: determine working directory by passed mode and 'is_local' flag
    is_local = _is_local(c)
    if is_local:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pylabber')
    else:
        return f'/home/{c.user}/pylabber'


def _pylabber_dotenv_file(c, mode):
    return os.path.join(_pylabber_workdir(c, mode), '.env')


def _pyenv_exec(c):
    return f'/home/{c.user}/.pyenv/bin/pyenv'


def _pip_exec(c):
    return f'/home/{c.user}/.pyenv/versions/{PYENV_NAME}/bin/pip'


def _python_exec(c):
    return f'/home/{c.user}/.pyenv/versions/{PYENV_NAME}/bin/python'


def _gunicorn_exec(c):
    return f'/home/{c.user}/.pyenv/versions/{PYENV_NAME}/bin/gunicorn'


def _vuelabber_workdir(c, mode):
    # TODO: determine working directory by passed mode and 'is_local' flag
    is_local = _is_local(c)
    if is_local:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vuelabber')
    else:
        return f'/home/{c.user}/vuelabber'


def _get_domain(c, mode):
    if mode == MODE_PROD:
        return c.original_host
    elif mode == MODE_DEV:
        host = '127.0.0.1' if _is_local(c) else c.host
        return f'{host}.xip.io'
    else:
        raise Exception(f'Unknown mode {mode}')


def _vuelabber_domain(c, mode):
    return _get_domain(c, mode)


def _pylabber_admin_domain(c, mode):
    return 'admin.{}'.format(_get_domain(c, mode))


def _pylabber_admin_url(c, mode, api=False):
    return 'http://{host}{port}{api_path}'.format(
        host=_pylabber_admin_domain(c, mode),
        port='' if str(PYLABBER_PORT) == '80' else f':{PYLABBER_PORT}',
        api_path='/api' if api else ''
    )


def _vuelabber_url(c, mode):
    return 'http://{host}{port}'.format(
        host=_vuelabber_domain(c, mode),
        port='' if str(VUELABBER_PORT) == '80' else f':{VUELABBER_PORT}',
    )


@task
def prepare_os(c):
    c.sudo('locale-gen')
    c.sudo('DEBIAN_FRONTEND=noninteractive sudo apt-get -y update && sudo apt-get -y upgrade')
    c.sudo('apt-get install -y git build-essential libreadline-dev zlib1g-dev libssl-dev libbz2-dev libsqlite3-dev'
           ' libffi-dev postgresql-10 libpq-dev')


@task
def prepare_postgres(c):
    c.sudo(f'psql -c "CREATE USER {PG_USER} WITH PASSWORD \'{PG_PASSWORD}\';"'
           f' -c "CREATE DATABASE {PG_DATABASE};"'
           f' -c "GRANT ALL ON DATABASE {PG_DATABASE} TO {PG_USER}"', user='postgres')


@task
def install_pyenv(c):
    if c.run(f'test -d ~/.pyenv', warn=True).failed:
        c.run('curl https://pyenv.run | bash')

    c.run(f'grep pyenv -q ~/.bashrc || echo \'{PYENV_BASHRC}\' >> ~/.bashrc')


@task
def create_venv(c):
    pyenv_exec = _pyenv_exec(c)
    c.run(f'{pyenv_exec} update')
    c.run(f'{pyenv_exec} install {PYTHON_VERSION} --skip-existing')
    c.run(f'{pyenv_exec} virtualenvs --bare | grep ^{PYENV_NAME}$ ||'
          f' {pyenv_exec} virtualenv {PYTHON_VERSION} {PYENV_NAME}')


@task
def create_workdirs(c, mode):
    pylabber_work_dir = _pylabber_workdir(c, mode)
    vuelabber_work_dir = _vuelabber_workdir(c, mode)

    c.run(f'mkdir -p {pylabber_work_dir} {vuelabber_work_dir}')

    vuelabber_dotgit_dir = os.path.join(pylabber_work_dir, '.git')
    if c.run(f'test -d {vuelabber_dotgit_dir}', warn=True).failed:
        c.run(f'git clone {PYLABBER_REPO} {pylabber_work_dir}')

    pylabber_dotgit_dir = os.path.join(vuelabber_work_dir, '.git')
    if c.run(f'test -d {pylabber_dotgit_dir}', warn=True).failed:
        c.run(f'git clone {VUELABBER_REPO} {vuelabber_work_dir}')


@task
def install_requirements(c, mode):
    pylabber_work_dir = _pylabber_workdir(c, mode)
    pyenv_pip_exec = _pip_exec(c)
    with c.cd(pylabber_work_dir):
        c.run(f'{pyenv_pip_exec} install --upgrade pip setuptools')
        # TODO: fix setup.py at django_mri package: rid of requirements file reading to set dependencies
        c.run(f'rm -rf /tmp/django_mri_repo &&'
              f' git clone https://github.com/ZviBaratz/django_mri.git /tmp/django_mri_repo &&'
              f' sed -i "/^http.*$/d" /tmp/django_mri_repo/requirements/common.txt &&'
              f' {pyenv_pip_exec} install /tmp/django_mri_repo/ &&'
              f' rm -rf /tmp/django_mri_repo')
        c.run(f'cat requirements/common.txt | grep -v django_mri | xargs {pyenv_pip_exec} install')
        c.run(f'{pyenv_pip_exec} install -r requirements/dev.txt')
        c.run(f'{pyenv_pip_exec} install treebeard')
        c.run(f'{pyenv_pip_exec} install gunicorn')


@task
def create_dotenv(c, mode, force=False):
    dot_env_file = _pylabber_dotenv_file(c, mode)
    if force or c.run(f'test -f {dot_env_file}', warn=True).failed:
        c.run(f'rm -rf {dot_env_file}')
        for name, value in _env_vars(mode).items():
            c.run(f'echo "{name}={value}" >> {dot_env_file}')


@task
def db_migrate(c, mode):
    pylabber_work_dir = _pylabber_workdir(c, mode)
    pyenv_python_exec = _python_exec(c)
    with c.cd(pylabber_work_dir):
        # TODO: add env.read_env(os.path.join(BASE_DIR, '.env')) to settings.py
        c.run(f'export $(cat .env | xargs) &&'
              f' {pyenv_python_exec} ./manage.py makemigrations &&'
              f' {pyenv_python_exec} ./manage.py migrate')


@task
def collect_static(c, mode):
    pylabber_work_dir = _pylabber_workdir(c, mode)
    pyenv_python_exec = _python_exec(c)
    with c.cd(pylabber_work_dir):
        c.run('mkdir -p static dist node_modules')
        c.run(f'{pyenv_python_exec} ./manage.py collectstatic --no-input')


@task
def configure_cors(c, mode):
    vuelabber_url = _vuelabber_url(c, mode)
    vuelabber_url_esc = vuelabber_url.replace('/', r'\/')
    pylabber_work_dir = _pylabber_workdir(c, mode)
    pyenv_python_exec = _python_exec(c)
    with c.cd(pylabber_work_dir):
        c.run(f'''export $(cat .env | xargs) && {pyenv_python_exec} ./manage.py shell -c '''
              f'''"from pylabber import settings; print(settings.CORS_ORIGIN_WHITELIST)" | '''
              f'''grep '{vuelabber_url_esc}' -q || echo "CORS_ORIGIN_WHITELIST = [\'{vuelabber_url}\']"'''
              f''' >>  pylabber/settings.py''')


@task
def configure_logging(c, mode):
    remote_tmp_file = '/tmp/logging_conf.py'
    pylabber_work_dir = _pylabber_workdir(c, mode)
    remote_dst_dir = os.path.join(pylabber_work_dir, 'pylabber')
    c.put(PYLABBER_LOGGING_CONF, remote_tmp_file)
    c.run(f'mv {remote_tmp_file} {remote_dst_dir}')
    with c.cd(pylabber_work_dir):
        c.run(r'grep "from .logging_conf import \*" -q pylabber/settings.py ||'
              r' echo "from .logging_conf import *" >> pylabber/settings.py')


@task
def configure_supervisor(c, mode):
    c.sudo('apt-get install -y supervisor')
    remote_tpl_file = f'/tmp/{SUPERVISOR_CONFIG_TPL}'
    c.put(SUPERVISOR_CONFIG_TPL, '/tmp/')
    config_params = {
        'WORK_DIR': _pylabber_workdir(c, mode),
        'PYENV_GUNICORN_EXEC': _gunicorn_exec(c),
        'USER': c.user,
        'GUNICORN_BIND': GUNICORN_BIND,
        'ENV_VARS': ','.join(f'{k}={v}' for k, v in _env_vars(mode).items())
    }
    for k, v in config_params.items():
        c.run('sed -i "s/{{{k}}}/{v}/g" {remote_tpl_file}'.format(
            k=k,
            v=v.replace('/', r'\/'),
            remote_tpl_file=remote_tpl_file,
        ))
    c.sudo(f'mv {remote_tpl_file} /etc/supervisor/conf.d/pylabber.conf')
    c.sudo('supervisorctl reload')


@task
def configure_nginx(c, mode):
    c.sudo('apt-get install -y nginx')
    remote_tpl_file = f'/tmp/{NGINX_CONFIG_TPL}'
    c.put(NGINX_CONFIG_TPL, '/tmp/')
    config_params = {
        'WORK_DIR': _pylabber_workdir(c, mode),
        'VUELABBER_WORK_DIR': os.path.join(_vuelabber_workdir(c, mode), 'dist'),
        'VUELABBER_SERVER_NAME': _vuelabber_domain(c, mode),
        'PYLABBER_SERVER_NAME': _pylabber_admin_domain(c, mode),
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
def create_superuser(c, mode):
    pylabber_work_dir = _pylabber_workdir(c, mode)
    pyenv_python_exec = _python_exec(c)
    with c.cd(pylabber_work_dir):
        c.run(f'export $(cat .env | xargs) && {pyenv_python_exec} manage.py shell -c '
              f'"from django.contrib.auth import get_user_model; User = get_user_model();'
              f'User.objects.filter(username=\'{SUPERUSER_LOGIN}\').exists() or '
              f'User.objects.create_superuser(\'{SUPERUSER_LOGIN}\', \'admin@example.com\', \'{SUPERUSER_PASS}\')"')


@task
def npm_build(c, mode):
    c.sudo('apt-get install -y npm')
    # TODO: rid of hardcoded config params at vuelabber(src/api/base_url.js)
    vuelabber_work_dir = _vuelabber_workdir(c, mode)
    base_url_conf_file = os.path.join(vuelabber_work_dir, 'src/api/base_url.js')
    pylabber_api_url_esc = _pylabber_admin_url(c, mode, api=True).replace('/', r'\/')
    c.run(f"""sed -i "s/const PRODUCTION =.*/const PRODUCTION = '{pylabber_api_url_esc}'/g" {base_url_conf_file}""")
    c.run(f"""sed -i "s/const MODE.*$/const MODE = \'production\'/g" {base_url_conf_file}""")
    with c.cd(vuelabber_work_dir):
        c.run('npm install && npm run build')


@task
def vuelabber_fetch_build(c, mode):
    c.local('tar cf /tmp/vuelabber-dist.tar vuelabber-dist')
    c.put('/tmp/vuelabber-dist.tar', '/tmp/vuelabber-dist.tar')
    pylabber_api_url_esc = _pylabber_admin_url(c, mode, api=True).replace('/', r'\/')
    vuelabber_work_dir = _vuelabber_workdir(c, mode)
    with c.cd(vuelabber_work_dir):
        c.run(rf'tar xf /tmp/vuelabber-dist.tar && rm -rf dist && mv vuelabber-dist dist && '
              rf'sed -i "s/https:\/\/pylabber.org\/api/{pylabber_api_url_esc}/g" dist/js/*')


@task
def info(c, mode):
    print('Pylabber work dir', _pylabber_workdir(c, mode))
    print('Vuelabber work dir', _vuelabber_workdir(c, mode))
    print('-' * 10)
    print('Admin URL', _pylabber_admin_url(c, mode))
    print('API URL', _pylabber_admin_url(c, mode, api=True))
    print('Vuelabber URL', _vuelabber_url(c, mode))
    print('-' * 10)
    print(f'Test user: {SUPERUSER_LOGIN} {SUPERUSER_PASS}')


@task
def deploy(c, mode=MODE_PROD):
    is_local = _is_local(c)
    if not is_local:
        prepare_os(c)
    prepare_postgres(c)
    if not is_local:
        install_pyenv(c)
        create_venv(c)
    create_workdirs(c, mode)
    install_requirements(c, mode)
    create_dotenv(c, mode)
    db_migrate(c, mode)
    collect_static(c, mode)
    configure_cors(c, mode)
    if not is_local:
        configure_logging(c, mode)
        configure_supervisor(c, mode)
        configure_nginx(c, mode)
    create_superuser(c, mode)
    if not is_local:
        vuelabber_fetch_build(c, mode)
    info(c, mode)
