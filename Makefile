# Nodo Ruta · comandos básicos del proyecto
# Ejecute `make help` para ver los comandos disponibles.

.DEFAULT_GOAL := help

# --- Variables (se pueden sobrescribir: make run PUERTO=9000 ID=local-2) ---
# Primer Python 3.10+ que encuentre: en Mac, python3 suele ser el 3.9 del sistema y logfire 6 no se instala ahí.
PYTHON     ?= $(shell for p in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do \
                command -v $$p >/dev/null 2>&1 && { echo $$p; break; }; done)
VENV       ?= .venv
VENV_PY    := $(VENV)/bin/python
PUERTO     ?= 8080
ID         ?= local-1
PETICIONES ?= 10
ESPERADAS  ?= instancia-1,instancia-2
IMAGEN     ?= nodo-ruta
COMPOSE    := docker compose

# Carga las variables de .env (LOGFIRE_TOKEN, ...) solo si el archivo existe.
CARGAR_ENV := if [ -f .env ]; then set -a; . ./.env; set +a; fi;
# Avisa si aún no se instalaron las dependencias.
VERIFICAR_VENV := if [ ! -x $(VENV_PY) ]; then echo "No existe $(VENV). Ejecute primero: make install"; exit 1; fi;

.PHONY: help venv install install-dev datos run iniciar verificar test \
        respaldar simular-error restaurar \
        docker-build docker-run compose-up compose-down compose-verificar clean

help: ## Muestra esta ayuda con los comandos disponibles
	@echo "Nodo Ruta · uso: make <comando> [VARIABLE=valor]"
	@echo ""
	@echo "Comandos disponibles:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "Variables: PYTHON=$(PYTHON) PUERTO=$(PUERTO) ID=$(ID) PETICIONES=$(PETICIONES) IMAGEN=$(IMAGEN)"

# --- Entorno -------------------------------------------------------------------

$(VENV_PY):
	$(PYTHON) -m venv $(VENV)
	$(VENV_PY) -m pip install --upgrade pip

venv: $(VENV_PY) ## Crea el entorno virtual en .venv (requiere Python 3.10+)

install: $(VENV_PY) ## Instala las dependencias del servicio (requirements.txt)
	$(VENV_PY) -m pip install -r requirements.txt

install-dev: $(VENV_PY) ## Instala las dependencias de pruebas (requirements-dev.txt)
	$(VENV_PY) -m pip install -r requirements-dev.txt

# --- Ejecución local -----------------------------------------------------------

iniciar: ## Levanta backend + interfaz web (http://127.0.0.1:3000) con un comando
	$(PYTHON) iniciar.py

datos: ## Prepara la copia de trabajo de los datos (data/pedidos.json)
	@if [ -f data/pedidos.json ]; then echo "data/pedidos.json ya existe; no se modifica."; \
	else $(PYTHON) scripts/datos.py preparar; fi

run: datos ## Levanta una instancia local (PUERTO=8080 ID=local-1)
	@$(VERIFICAR_VENV) $(CARGAR_ENV) $(VENV_PY) scripts/ejecutar_local.py --puerto $(PUERTO) --id $(ID)

verificar: ## Consulta /pedidos y guarda evidencia en evidencias/ (servicio corriendo)
	$(PYTHON) scripts/verificar_servicio.py http://127.0.0.1:$(PUERTO)/pedidos \
		--peticiones $(PETICIONES) --salida evidencias/prueba_$$(date +%Y%m%d_%H%M%S).json

test: ## Ejecuta la prueba e2e de Logfire (requiere tokens en .env)
	@$(VERIFICAR_VENV) $(CARGAR_ENV) $(VENV_PY) -m unittest tests.test_e2e_logfire -v

# --- Respaldo y recuperación ---------------------------------------------------

respaldar: ## Crea un respaldo de data/pedidos.json en respaldos/
	$(PYTHON) scripts/datos.py respaldar

simular-error: ## Corrompe la copia de trabajo para simular una falla (/health -> 503)
	$(PYTHON) scripts/datos.py simular-error

restaurar: ## Restaura un respaldo (RESPALDO=respaldos/<archivo>.json)
	@if [ -z "$(RESPALDO)" ]; then echo "Indique RESPALDO=respaldos/<archivo>.json"; exit 1; fi
	$(PYTHON) scripts/datos.py restaurar --respaldo $(RESPALDO)

# --- Docker --------------------------------------------------------------------

docker-build: ## Construye la imagen Docker del servicio
	docker build -t $(IMAGEN) .

docker-run: ## Ejecuta la imagen en PUERTO (pasa LOGFIRE_TOKEN si existe)
	@$(CARGAR_ENV) docker run --rm -p $(PUERTO):8080 -e LOGFIRE_TOKEN -e LOGFIRE_ENVIRONMENT -e INSTANCE_ID=$(ID) $(IMAGEN)

compose-up: datos ## Levanta dos instancias detrás de NGINX con Docker Compose
	$(COMPOSE) up --build

compose-down: ## Detiene y elimina los contenedores de Docker Compose
	$(COMPOSE) down

compose-verificar: ## Verifica que el balanceo reparte entre instancia-1 e instancia-2
	$(PYTHON) scripts/verificar_servicio.py --peticiones $(PETICIONES) --esperadas $(ESPERADAS) \
		--salida evidencias/compose_$$(date +%Y%m%d_%H%M%S).json

# --- Limpieza ------------------------------------------------------------------

clean: ## Elimina cachés de Python (no toca data/, respaldos/ ni evidencias/)
	find . -type d -name "__pycache__" -not -path "./$(VENV)/*" -prune -exec rm -rf {} +
