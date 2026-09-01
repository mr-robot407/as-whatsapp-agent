.PHONY: build deploy test test-unit validate clean logs-inbound local-verify local-message

STACK_NAME := as-whatsapp-agent
REGION     := ap-south-1
CONFIG_ENV := default

build:
	sam build --use-container

build-fast:
	sam build

deploy: build
	sam deploy \
		--stack-name $(STACK_NAME) \
		--region $(REGION) \
		--capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
		--resolve-s3 \
		--config-env $(CONFIG_ENV)

deploy-guided: build
	sam deploy --guided

validate:
	sam validate --region $(REGION)

test: test-unit

test-unit:
	python3 -m pytest tests/unit/ -v

logs-inbound:
	sam logs --name InboundFunction --stack-name $(STACK_NAME) --region $(REGION) --tail

local-verify:
	sam local invoke InboundFunction --event tests/events/webhook_verify.json

local-message:
	sam local invoke InboundFunction --event tests/events/webhook_message_text.json

clean:
	rm -rf .aws-sam/
