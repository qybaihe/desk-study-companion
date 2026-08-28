PYTHON ?= python3

.PHONY: help test compile config deploy audit server dashboard assets transparent-assets tidb-schema tidb-sync

help:
	@printf '%s\n' \
	  'make test       - run firmware and voice-service tests' \
	  'make compile    - compile-check every maintained Python file' \
	  'make config     - generate the ignored board Wi-Fi/token config' \
	  'make deploy     - upload the canonical firmware to the ESP32-S3' \
	  'make audit      - read and compare all Python files on the board' \
	  'make server     - run the Mac LAN voice service' \
	  'make dashboard  - serve the parent dashboard on port 4173' \
	  'make transparent-assets - build the verified transparent sheep archive' \
	  'make tidb-schema - create the TiDB behaviour/code tables' \
	  'make tidb-sync  - snapshot tracked code and asset metadata to TiDB'

test:
	@set -e; for test in firmware/tests/test_*.py; do \
		PYTHONPATH=firmware $(PYTHON) "$$test"; \
	done
	@set -e; for test in services/voice_ai/test_*.py; do \
		PYTHONPATH=services/voice_ai $(PYTHON) "$$test"; \
	done

compile:
	@$(PYTHON) -m py_compile firmware/*.py tooling/*.py tooling/asset_builders/*.py services/voice_ai/*.py

config:
	@PYTHONPATH=. $(PYTHON) services/voice_ai/build_device_voice_config.py

deploy:
	@PYTHONPATH=.:tooling $(PYTHON) -u tooling/deploy.py

audit:
	@PYTHONPATH=.:tooling $(PYTHON) -u tooling/audit_board.py

server:
	@PYTHONPATH=services/voice_ai $(PYTHON) -u services/voice_ai/local_fast_voice_server.py

dashboard:
	@$(PYTHON) -m http.server 4173 --directory apps/parent_dashboard

assets:
	@$(PYTHON) tooling/asset_builders/build_pet_v2_animation.py
	@$(PYTHON) tooling/asset_builders/build_low_light_animation.py
	@$(PYTHON) tooling/asset_builders/build_rest_break_animation.py

transparent-assets:
	@$(PYTHON) tooling/build_transparent_pet_archive.py

tidb-schema:
	@PYTHONPATH=services/voice_ai $(PYTHON) -c "from mimo_voice_qa import DEFAULT_ENV,load_dotenv;load_dotenv(DEFAULT_ENV);from tidb_store import ensure_schema;ensure_schema();print('TiDB schema: OK')"

tidb-sync:
	@PYTHONPATH=services/voice_ai $(PYTHON) tooling/sync_project_to_tidb.py
