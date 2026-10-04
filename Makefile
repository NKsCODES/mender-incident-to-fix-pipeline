.PHONY: install test eval eval-cursor demo serve dashboard check
export MENDER_PRICE_IN ?= 3
export MENDER_PRICE_OUT ?= 15

install:
	pip install -e "backend[dev]"
	cd dashboard && npm install

dashboard:
	cd dashboard && npm run build

test:
	cd backend && python -m pytest -q

eval:            ## harness regression suite, no API key needed
	cd backend && python -m mender eval --runner replay

eval-cursor:     ## real model numbers, needs CURSOR_API_KEY and the Cursor CLI
	cd backend && python -m mender eval --runner cursor

demo:            ## fill the dashboard with one run per fixture incident
	cd backend && python -m mender demo

serve:
	cd backend && python -m mender serve

check: test eval dashboard
