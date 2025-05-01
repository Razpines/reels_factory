PYTHON ?= python
CONFIG ?= config/config.json

.PHONY: install scrape rewrite generate publish clean

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

scrape:
	$(PYTHON) -m reels_factory.cli scrape --config-path $(CONFIG)

rewrite:
	$(PYTHON) -m reels_factory.cli rewrite --config-path $(CONFIG)

generate:
	$(PYTHON) -m reels_factory.cli generate --config-path $(CONFIG)

publish:
	$(PYTHON) -m reels_factory.cli publish

clean:
	rm -rf __pycache__ .pytest_cache dist build output/*.parquet output/narration output/reels output/logs
