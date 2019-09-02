# pylabber-deploy

```bash
pyenv virtualenv 3.6.9 pylabber_deploy
pyenv activate pylabber_deploy

pip install -r requirements.txt

fab -e -H pylabber-test1 deploy
```
