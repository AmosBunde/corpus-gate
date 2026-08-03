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
VARIANT ?= echo
PORT ?= 8000
RUN ?= latest
UI_PORT ?= 3000

define not_yet
	@echo "make $(1) lands in milestone $(2); nothing ran." >&2; exit 2
endef

.PHONY: venv install lint format test \
        eval-set ingest eval-base rag eval agent finetune gate smoke \
        judge agreement fetch-corpus serve ui

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
	$(PYTHON) -m corpusgate.evals.schema --complete

eval:
	$(PYTHON) -m corpusgate.evals.runner --variant $(VARIANT)
	$(PYTHON) -m corpusgate.evals.judge score --run latest $(if $(JUDGE_BACKEND),--backend $(JUDGE_BACKEND),)

smoke:
	$(call not_yet,smoke,M1)

eval-base:
	$(call not_yet,eval-base,M2)

gate:
	$(call not_yet,gate,M2)

judge:
	$(PYTHON) -m corpusgate.evals.judge score --run $(RUN) $(if $(JUDGE_BACKEND),--backend $(JUDGE_BACKEND),)

agreement:
	$(PYTHON) -m corpusgate.evals.judge agreement --run $(RUN)

# ---- Ingestion and variants (milestones M2 to M4) -----------------------

fetch-corpus:
	$(PYTHON) -m corpusgate.ingest.fetch --manifest corpus/manifest.json --dest corpus/raw

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
	MODEL_BACKEND=$(MODEL_BACKEND) $(UVICORN) corpusgate.serve.app:app --host 0.0.0.0 --port $(PORT)

ui:
	cd ui && npm install && npm run dev -- --host --port $(UI_PORT)
