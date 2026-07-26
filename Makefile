# Optional convenience wrapper. Everything here also works cross-platform via
#   python -m ingomob.cli <stage>
# which is the documented path for Windows users without make.
PY ?= python3
export PYTHONPATH := src

.PHONY: help setup generate validate warehouse analytics forecast dashboard report all \
        serve doctor test lint fmt clean docker-build live

help:
	@$(PY) -m ingomob.cli --help

setup:
	$(PY) -m pip install -r requirements-dev.txt -c constraints.txt
	$(PY) -m pip install -e . -c constraints.txt

generate:   ; $(PY) -m ingomob.cli generate
validate:   ; $(PY) -m ingomob.cli validate
warehouse:  ; $(PY) -m ingomob.cli warehouse
analytics:  ; $(PY) -m ingomob.cli analytics
forecast:   ; $(PY) -m ingomob.cli forecast
dashboard:  ; $(PY) -m ingomob.cli dashboard
report:     ; $(PY) -m ingomob.cli report
all:        ; $(PY) -m ingomob.cli run-all
live:       ; $(PY) -m ingomob.cli --source live run-all
serve:      ; $(PY) -m ingomob.cli serve
doctor:     ; $(PY) -m ingomob.cli doctor

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check src tests

fmt:
	$(PY) -m ruff check --fix src tests

clean:
	$(PY) -c "import shutil,pathlib; [shutil.rmtree(p, ignore_errors=True) for p in \
	  ['data/raw','data/processed','data/warehouse','data/cache','.pytest_cache','.ruff_cache']]"

docker-build:
	docker build -t ingomob:latest .
