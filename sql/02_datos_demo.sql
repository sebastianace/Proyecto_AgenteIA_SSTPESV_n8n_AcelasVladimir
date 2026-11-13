-- =====================================================================
-- ARCHIVO  : 02_datos_demo.sql
-- CONTENIDO: SOLO PARA DEMOSTRACION. Envejece las fechas de los documentos de
--            prueba para que preguntas como "que documentos estan estancados"
--            tengan respuestas interesantes.
-- POR QUE   : el seed del proyecto de base de datos crea todos los documentos
--            "hoy", asi que sin este script nada lleva dias sin cambios.
-- NO ejecutar en una base con datos reales.
-- USO      : psql -U postgres -d sst_pesv -f sql/02_datos_demo.sql
-- =====================================================================
UPDATE documents
SET created_at = CURRENT_TIMESTAMP - ((35 + id) || ' days')::INTERVAL,
    updated_at = CURRENT_TIMESTAMP - (((id * 7) % 40) || ' days')::INTERVAL
WHERE status <> 'FINALIZADO';

-- Los finalizados mantienen coherencia: se crearon antes de cerrarse.
UPDATE documents
SET created_at = finalized_at - INTERVAL '10 days',
    updated_at = finalized_at
WHERE status = 'FINALIZADO';
