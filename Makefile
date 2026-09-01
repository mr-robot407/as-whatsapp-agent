.PHONY: build deploy test test-unit validate seed clean

STACK_NAME   := as-email-agent
REGION       := ap-south-1
CONFIG_ENV   := default

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

test-e2e: seed
	@echo "Trigger SES inbound by sending a test email to info@ateliershreenu.com"

seed:
	python3 scripts/seed_test_emails.py

seed-contacts:
	@[ -f contacts.csv ] || (echo "ERROR: contacts.csv not found" && exit 1)
	python3 scripts/import_contacts.py --file contacts.csv

validate-classifier:
	@[ -f labelled_emails.csv ] || (echo "ERROR: labelled_emails.csv not found" && exit 1)
	python3 scripts/validate_classifier.py --file labelled_emails.csv

upload-assets:
	bash scripts/upload_assets.sh

logs-inbound:
	sam logs --name InboundFunction --stack-name $(STACK_NAME) --region $(REGION) --tail

logs-campaigns:
	sam logs --name CampaignsFunction --stack-name $(STACK_NAME) --region $(REGION) --tail

logs-funnel:
	sam logs --name FunnelFunction --stack-name $(STACK_NAME) --region $(REGION) --tail

logs-hooks:
	sam logs --name HooksFunction --stack-name $(STACK_NAME) --region $(REGION) --tail

local-inbound:
	sam local invoke InboundFunction --event tests/events/ses_inbound.json

local-hooks:
	sam local invoke HooksFunction --event tests/events/sns_bounce.json

local-campaigns:
	sam local invoke CampaignsFunction --event tests/events/cron_event.json

clean:
	rm -rf .aws-sam/
