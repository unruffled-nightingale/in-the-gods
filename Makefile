NAME   := inthegods
IMAGE  := unrufflednightingale/$(NAME)
TAG    := latest
PORT   := 8080
WEEKS  ?= 8
PYTHON ?= $(firstword $(wildcard .venv/bin/python) python3)

.PHONY: help recollect serve docker-build docker-run docker-stop docker-push kube-secret kube-apply kube-redeploy deploy

help:
	@echo "recollect        crawl venues, rebuild extract and theatre.html ($(WEEKS) weeks)"
	@echo "serve            start the website on http://localhost:$(PORT)"
	@echo "docker-build     build local image '$(NAME)'"
	@echo "docker-run       build and run on http://localhost:$(PORT)"
	@echo "docker-stop      stop the local container"
	@echo "docker-push      build, tag, and push $(IMAGE):$(TAG)"
	@echo "kube-secret      write kube/secret.yaml from .env"
	@echo "kube-redeploy    rollout restart deployment $(NAME)"
	@echo "deploy           push image, apply kube, restart"

recollect:
	$(PYTHON) pipeline/fetch.py \
		--venues data/venues.yaml \
		--weeks $(WEEKS) \
		--out .cache/raw.json
	$(PYTHON) pipeline/build_extract.py \
		--raw .cache/raw.json \
		--out data/extracts/latest.json
	$(PYTHON) pipeline/refine.py \
		--in data/extracts/latest.json \
		--out data/extracts/latest.json
	$(PYTHON) pipeline/embed.py \
		--in data/extracts/latest.json \
		--out data/extracts/latest.embeddings.npz
	$(PYTHON) frontend/make_artifact.py \
		--events data/extracts/latest.json \
		--template frontend/template.html \
		--out frontend/theatre.html

serve:
	$(PYTHON) -m uvicorn server.app:app --host 0.0.0.0 --port $(PORT)

docker-build:
	docker build --platform linux/amd64 -t $(NAME) .

docker-run: docker-build
	docker run --rm -p $(PORT):80 --name $(NAME) -d $(NAME)

docker-stop:
	docker stop $(NAME)

docker-push: docker-build
	docker tag $(NAME) $(IMAGE):$(TAG)
	docker push $(IMAGE):$(TAG)

kube-secret:
	./kube/make_secret.sh

kube-apply: kube-secret
	kubectl apply -f kube/

kube-redeploy:
	kubectl rollout restart deployment $(NAME)

deploy: docker-push kube-apply kube-redeploy
