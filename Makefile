PROJECT_NAME=wa_bot
IMAGE_NAME=$(PROJECT_NAME):latest
CONTAINER_NAME=$(PROJECT_NAME)_container

.PHONY: build run stop logs

build:
	docker build -t $(IMAGE_NAME) .

run:
	docker run -d --name $(CONTAINER_NAME) -e WA_URL="http://host.docker.internal:8003/" $(IMAGE_NAME)

stop:
	docker stop $(CONTAINER_NAME) || true
	docker rm $(CONTAINER_NAME) || true

rebuild:
	make stop
	make build
	make run

logs:
	docker logs -f $(CONTAINER_NAME)
