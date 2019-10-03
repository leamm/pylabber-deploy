# pylabber-deploy

```bash
pyenv virtualenv 3.6.9 pylabber_deploy
pyenv activate pylabber_deploy

pip install -r requirements.txt

# To run deploy process on the remote host pylabber-test1
fab -e -H pylabber-test1 deploy --mode=prod

# Local dev
fab -e deploy --mode=dev
```
