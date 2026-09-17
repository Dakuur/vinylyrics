# vinylyrics — recetas del proyecto

inspect carpeta:
    uv run vinylizer inspect {{carpeta}}

vinylize carpeta *args:
    uv run vinylizer build {{carpeta}} {{args}}

dev:
    uv run vinylyrics-server

test:
    uv run pytest -v

lint:
    uv run python -m py_compile $(find vinylyrics -name '*.py')

# eval y eval-full llegan en la Fase 8, junto al subcomando que envuelven —
# no se declaran aquí todavía para no apuntar a un comando que no existe.
