# deploy/
`modal_app.py`: a Modal web endpoint that serves `api/` and `web/dist` at one public URL, one container kept warm. MariaDB runs elsewhere (decide: small cloud server or a Modal container with a Volume).
