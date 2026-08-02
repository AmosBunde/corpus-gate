# CorpusGate make targets. The contract for this file is README section 8.
#
# Targets whose stage has not landed yet exit nonzero with the milestone
# that delivers them, so a chained invocation fails loudly instead of
# pretending success.

PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip
RUFF ?= .venv/bin/ruff
PYTEST ?= .venv/bin/pytest
UVICORN ?= .venv/bin/uvicorn
MODEL_BACKEND ?= local
VARIANT ?= current

define not_yet
	@echo "make $(1) lands in milestone $(2); nothing ran." >&2; exit 2
endef

.PHONY: venv install lint format test \
        eval-set ingest eval-base rag eval agent finetune gate smoke \
        fetch-corpus serve ui

venv:
	python3 -m venv .venv

install:
	$(PIP) install -e ".[dev,serve]"

lint:
	$(RUFF) check .

format:
	$(RUFF) format .
	$(RUFF) check --fix .

test:
	$(PYTEST)

# ---- Eval gate (milestone M1) -------------------------------------------

eval-set:
	$(call not_yet,eval-set,M1)

eval:
	$(call not_yet,eval,M1)

smoke:
	$(call not_yet,smoke,M1)

eval-base:
	$(call not_yet,eval-base,M2)

gate:
	$(call not_yet,gate,M2)

# ---- Ingestion and variants (milestones M2 to M4) -----------------------

fetch-corpus:
	$(call not_yet,fetch-corpus,M2)

ingest:
	$(call not_yet,ingest,M2)

rag:
	$(call not_yet,rag,M2)

agent:
	$(call not_yet,agent,M3)

finetune:
	$(call not_yet,finetune,M4)

# ---- Serving (stubbed in M0 by issue #8, completed in M5) ---------------

serve:
	MODEL_BACKEND=$(MODEL_BACKEND) $(UVICORN) corpusgate.serve.app:app --host 0.0.0.0 --port 8000

ui:
	cd ui && npm install && npm run dev -- --host --port 3000
