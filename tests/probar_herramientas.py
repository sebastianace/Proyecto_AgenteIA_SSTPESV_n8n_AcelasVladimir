"""Prueba las consultas de las herramientas del agente contra la base sst_pesv real.

Lee las consultas directamente del workflow (workflows/01_agente_telegram.json), asi se
prueba exactamente lo que ejecutara n8n, y las corre con el rol de minimo privilegio
asistente_ia. Tambien comprueba que ese rol no puede leer tablas ni escribir.

Variables de entorno: PGHOST, PGDATABASE (por defecto localhost / sst_pesv)
                      CLAVE_ASISTENTE = clave del rol asistente_ia (por defecto clave_ci)
Requisitos: base instalada + sql/01_vistas_asistente.sql + sql/02_datos_demo.sql
"""
import json
import os
import pathlib
import re
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
ENV = dict(os.environ,
           PGHOST=os.environ.get('PGHOST', 'localhost'),
           PGDATABASE=os.environ.get('PGDATABASE', 'sst_pesv'),
           PGUSER='asistente_ia',
           PGPASSWORD=os.environ.get('CLAVE_ASISTENTE', 'clave_ci'))

fallos = 0


def psql(sql):
    r = subprocess.run(['psql', '-v', 'ON_ERROR_STOP=1', '-At', '-c', sql],
                       env=ENV, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def literal(v):
    return str(v) if isinstance(v, (int, float)) else "'" + str(v).replace("'", "''") + "'"


def filas(consulta, params):
    """Cuenta las filas que devuelve la consulta de una herramienta con esos parametros."""
    cuerpo = consulta.strip().rstrip(';')
    sql = (f"PREPARE h AS SELECT count(*) FROM ({cuerpo}) q; "
           f"EXECUTE h({', '.join(literal(p) for p in params)});")
    rc, salida = psql(sql)
    if rc != 0:
        return f'ERROR: {salida}'
    return int(salida.splitlines()[-1])


def esperar(descripcion, esperado, obtenido, minimo=False):
    global fallos
    ok = (obtenido >= esperado) if (minimo and isinstance(obtenido, int)) else (obtenido == esperado)
    print(('OK    ' if ok else 'FALLA ') + f'{descripcion} (esperado {"≥" if minimo else ""}{esperado}, obtenido {obtenido})')
    if not ok:
        fallos += 1


wf = json.loads((RAIZ / 'workflows' / '01_agente_telegram.json').read_text(encoding='utf-8'))
herramientas = {n['name']: n['parameters']['query'] for n in wf['nodes'] if n['type'].endswith('postgresTool')}
esperar('herramientas encontradas en el workflow', 3, len(herramientas))

# --- resumen_cumplimiento ($1 organizacion, $2 sistema) ---
q = herramientas['resumen_cumplimiento']
esperar('resumen: todas las organizaciones', 6, filas(q, ['', '']))
esperar('resumen: filtro por nombre parcial (Transportes)', 2, filas(q, ['transportes', '']))
esperar('resumen: filtro por sistema PESV (minusculas)', 2, filas(q, ['', 'pesv']))
esperar('resumen: organizacion inexistente', 0, filas(q, ['no existe', '']))
esperar('resumen: la inactiva (Quito) no aparece', 0, filas(q, ['Quito', '']))

# --- documentos_organizacion ($1 organizacion, $2 estado, $3 limite) ---
q = herramientas['documentos_organizacion']
esperar('documentos: todos los de Andina', 5, filas(q, ['Andina', '', 25]))
esperar('documentos: solo borradores de Andina', 2, filas(q, ['Andina', 'BORRADOR', 25]))
esperar('documentos: el limite se respeta', 2, filas(q, ['Andina', '', 2]))
esperar('documentos: limite absurdo se recorta a 25', 5, filas(q, ['Andina', '', 100000]))
esperar('documentos: limite negativo se sube a 1', 1, filas(q, ['Andina', '', -5]))

# --- documentos_estancados ($1 dias_minimos) ---
q = herramientas['documentos_estancados']
esperar('estancados: con 30 dias hay resultados', 1, filas(q, [30]), minimo=True)
esperar('estancados: con 100000 dias no hay', 0, filas(q, [100000]))
esperar('estancados: nunca devuelve mas de 15 filas', 15, filas(q, [0]))

# --- inyeccion: el texto del usuario nunca se concatena a la consulta ---
q = herramientas['resumen_cumplimiento']
esperar("inyeccion SQL en 'organizacion' no devuelve nada", 0, filas(q, ["x' OR '1'='1", '']))

# --- minimo privilegio ---
for descripcion, sql in [
    ('no puede leer la tabla documents', 'SELECT 1 FROM public.documents LIMIT 1'),
    ('no puede leer la tabla persons (datos personales)', 'SELECT 1 FROM public.persons LIMIT 1'),
    ('no puede escribir en las vistas', "UPDATE asistente.v_documentos SET estado = 'FINALIZADO' WHERE false"),
    ('no puede crear tablas', 'CREATE TABLE asistente.prueba (id int)'),
]:
    rc, _ = psql(sql)
    esperar(f'permisos: {descripcion}', True, rc != 0)

if fallos:
    print(f'\n{fallos} prueba(s) fallaron')
    sys.exit(1)
print('\nTodas las pruebas pasaron')
