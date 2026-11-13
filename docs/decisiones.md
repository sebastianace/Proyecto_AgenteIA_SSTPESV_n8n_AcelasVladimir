# Decisiones de diseño

Este documento explica por qué el agente está hecho como está y qué alternativas se descartaron.

## 1. El modelo no escribe SQL

La forma más corta de hacer un asistente sobre una base de datos es darle al modelo el esquema y dejar que genere las consultas (*text-to-SQL*). Se descartó por tres razones:

- el modelo puede generar una consulta incorrecta que devuelve datos equivocados sin que nadie lo note;
- puede ser manipulado con texto malicioso (inyección de prompt) para leer lo que no debe;
- una consulta mal hecha sobre tablas grandes puede tumbar la base.

En su lugar el agente tiene **3 herramientas**, cada una con una consulta fija y revisada. El modelo solo decide *cuál* usar y *con qué valores* (`$fromAI`). Si algún día hace falta una pregunta nueva, se agrega una herramienta nueva, no se abre la puerta a SQL libre.

## 2. Vistas de solo lectura y un rol que solo ve las vistas

Las herramientas consultan dos vistas del esquema `asistente` (`v_cumplimiento` y `v_documentos`). El rol `asistente_ia` solo tiene `SELECT` sobre ellas: no puede leer las tablas, ni crear nada. Las vistas se ejecutan con los permisos de su dueño, así que el rol funciona sin tocar las tablas.

Esto es **minimización de datos**: las vistas no exponen cédulas, correos ni teléfonos (tabla `persons`). Aunque alguien lograra manipular al modelo, no existe forma de que esa información llegue a la respuesta. Las pruebas (`tests/probar_herramientas.py`) verifican que el rol falla al leer `documents` y `persons`.

**Alternativa descartada:** dar `SELECT` sobre las tablas y confiar en el prompt para que el modelo "no consulte datos personales". El prompt no es una frontera de seguridad.

## 3. Parámetros, no texto pegado

Los valores que elige el modelo llegan al nodo Postgres como parámetros (`$1`, `$2`, `$3`). Hay una prueba con un intento de inyección (`x' OR '1'='1`) que debe devolver cero filas. Además cada consulta aplica topes (`LIMIT`, `LEAST/GREATEST`) por si el modelo pide, por ejemplo, 100000 filas.

## 4. `total_coincidencias`

Cada herramienta limita cuántas filas devuelve. Para que el agente sepa si hay más de las que ve, las consultas incluyen `COUNT(*) OVER ()` y el prompt le indica avisar al usuario cuando el total supera lo que muestra. Sin esto, el agente podría presentar una lista truncada como si fuera completa.

## 5. Chats autorizados

Un bot de Telegram es público. Sin control, cualquiera que encuentre su nombre podría consultar datos de las organizaciones (y gastar la cuota del modelo). El workflow compara el chat con `chat_ids_permitidos` antes de llamar al agente. Si no está autorizado, responde con su chat id: así el administrador sabe qué id agregar, sin tener que usar herramientas externas para averiguarlo.

## 6. Un modelo intercambiable

El nodo es el de OpenAI con la *Base URL* configurable, que funciona con Groq, Gemini y otros proveedores compatibles. Así el proyecto no queda atado a un proveedor de pago. Se desactiva la *Responses API* (`responsesApiEnabled: false`) porque es propia de OpenAI y los demás proveedores usan *chat completions*.

El agente necesita un modelo con **llamadas a herramientas**. Los nombres de modelo cambian con frecuencia: el valor del workflow (`llama-3.3-70b-versatile` en Groq) puede necesitar actualizarse.

## 7. Memoria corta y en proceso

Se usa la memoria de ventana (últimos 6 mensajes) por chat, para que el usuario pueda preguntar "¿y los borradores?" sin repetir la organización. Vive en el proceso de n8n y se pierde al reiniciar. Una memoria persistente en Postgres exigiría que el rol del agente pudiera escribir, contra el principio de mínimo privilegio; para este caso de uso no compensa.

## 8. Qué pasa cuando algo falla

- El nodo del agente usa *On Error → Continue (using error output)*. Si el modelo o la base fallan, el usuario recibe un mensaje claro en lugar de silencio.
- Los mensajes que no son texto (fotos, stickers) reciben una respuesta indicándolo, en lugar de llegar vacíos al modelo.

## 9. Cómo se probó

| Qué | Cómo | Dónde corre |
|---|---|---|
| Consultas de las herramientas, inyección y permisos del rol | `tests/probar_herramientas.py`, leyendo las consultas del propio workflow | Automático en cada push (CI) |
| Workflows válidos, sin secretos, herramientas solo de lectura, reglas del prompt intactas | `tests/validar_workflows.py` | Automático en cada push (CI) |
| Ciclo completo del agente | Se importó el workflow en un n8n real, con la base real y un **servidor falso compatible con OpenAI** que decide la herramienta según la pregunta y responde citando lo que devolvió la base | Manual, una vez |

La prueba con el servidor falso verificó que: el prompt y el esquema de las 3 herramientas (generado desde `$fromAI`) llegan al modelo; cada herramienta ejecuta su consulta con los parámetros correctos contra la base; un chat no autorizado es rechazado; un mensaje sin texto recibe su aviso; y un fallo del modelo termina en el mensaje de problema técnico.

**Lo que esa prueba NO cubre:** la calidad de las respuestas de un modelo real (si elige bien la herramienta, si redacta bien). Eso depende del modelo y se comprueba a mano con preguntas reales. Tampoco se probó el envío real por Telegram.

## 10. Lo que no hace

- No modifica datos ni ejecuta acciones: es de solo lectura.
- No usa streaming de respuesta: Telegram recibe el mensaje completo.
- No guarda historial de conversaciones.
