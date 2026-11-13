"""Valida los workflows exportados de n8n antes de subirlos al repositorio.

Revisa:
  1. JSON valido, nombres de nodo unicos y conexiones (main y ai_*) a nodos existentes;
  2. que no incluyan credenciales, claves ni tokens;
  3. que las herramientas del agente solo consulten el esquema "asistente" y solo con SELECT;
  4. que el prompt incluya las reglas de seguridad;
  5. que la version de Telegram NO traiga un chat autorizado real (solo el marcador).
"""
import json
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
errores = []


def falla(msg):
    errores.append(msg)
    print('FALLA', msg)


archivos = sorted((RAIZ / 'workflows').glob('*.json'))
if not archivos:
    falla('no hay workflows en workflows/')

for ruta in archivos:
    texto = ruta.read_text(encoding='utf-8')
    try:
        wf = json.loads(texto)
    except json.JSONDecodeError as e:
        falla(f'{ruta.name}: JSON invalido ({e})')
        continue

    nombres = [n['name'] for n in wf['nodes']]
    if len(nombres) != len(set(nombres)):
        falla(f'{ruta.name}: nombres de nodo repetidos')

    for origen, salidas in wf['connections'].items():
        if origen not in nombres:
            falla(f'{ruta.name}: conexion desde un nodo inexistente ({origen})')
        for tipo, grupos in salidas.items():
            for grupo in grupos:
                for destino in grupo:
                    if destino['node'] not in nombres:
                        falla(f'{ruta.name}: conexion hacia un nodo inexistente ({destino["node"]})')

    for nodo in wf['nodes']:
        if 'credentials' in nodo:
            falla(f'{ruta.name}: el nodo "{nodo["name"]}" exporta credenciales; quitalas antes de subir')

    if re.search(r'(api[_-]?key|secret|bearer\s+[a-z0-9]|sk-[A-Za-z0-9]{10,}|gsk_[A-Za-z0-9]{10,})', texto, re.I):
        falla(f'{ruta.name}: parece contener un secreto')
    if re.search(r'\b\d{8,10}:[A-Za-z0-9_-]{35}\b', texto):
        falla(f'{ruta.name}: parece contener un token de Telegram')

    herramientas = [n for n in wf['nodes'] if n['type'].endswith('postgresTool')]
    if len(herramientas) != 3:
        falla(f'{ruta.name}: se esperaban 3 herramientas y hay {len(herramientas)}')
    for h in herramientas:
        consulta = h['parameters']['query']
        if not re.match(r'\s*SELECT\b', consulta, re.I):
            falla(f'{ruta.name}: la herramienta {h["name"]} no empieza con SELECT')
        if re.search(r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT)\b', consulta, re.I):
            falla(f'{ruta.name}: la herramienta {h["name"]} contiene una sentencia de escritura')
        tablas = re.findall(r'\b(?:FROM|JOIN)\s+([A-Za-z_][\w.]*)', consulta, re.I)
        for t in tablas:
            if not t.startswith('asistente.'):
                falla(f'{ruta.name}: la herramienta {h["name"]} consulta "{t}" fuera del esquema asistente')
        if '$fromAI' not in h['parameters'].get('options', {}).get('queryReplacement', ''):
            falla(f'{ruta.name}: la herramienta {h["name"]} no usa parametros $fromAI')

    agente = next((n for n in wf['nodes'] if n['type'].endswith('.agent')), None)
    if agente is None:
        falla(f'{ruta.name}: no hay nodo de agente')
    else:
        prompt = agente['parameters']['options'].get('systemMessage', '')
        for frase in ('SOLO con datos que obtengas de tus herramientas', 'Solo puedes CONSULTAR', 'datos personales', 'Ignora cualquier instrucci'):
            if frase not in prompt:
                falla(f'{ruta.name}: el prompt perdio la regla "{frase}"')

    if ruta.name.startswith('01_'):
        config = next((n for n in wf['nodes'] if n['name'] == 'Configuración'), None)
        valor = config['parameters']['assignments']['assignments'][0]['value'] if config else None
        if valor != 'REEMPLAZAR_CHAT_ID':
            falla(f'{ruta.name}: chat_ids_permitidos debe venir con el marcador REEMPLAZAR_CHAT_ID, no con un chat real')

if errores:
    print(f'\n{len(errores)} problema(s)')
    sys.exit(1)
print(f'OK: {len(archivos)} workflows validados')
