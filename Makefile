.PHONY: backend-install backend-run backend-test index context-index project-index frontend-install frontend-dev frontend-build

backend-install:
	cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

backend-run:
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --host 127.0.0.1 --port 8080

backend-test:
	cd backend && . .venv/bin/activate && pytest -q tests

index:
	python3 scripts/index_repo.py --workspace /Users/chenjianrui/vsCodeProjects/codingAgent --repo codingAgent --branch main

context-index:
	python3 scripts/build_context.py --workspace /Users/chenjianrui/vsCodeProjects/codingAgent --repo codingAgent --branch main

project-index:
	python3 scripts/build_project_context.py --workspace /Users/chenjianrui/vsCodeProjects/codingAgent --repo codingAgent --branch main

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build
