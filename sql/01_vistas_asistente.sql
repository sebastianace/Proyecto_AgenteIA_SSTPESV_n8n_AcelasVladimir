-- =====================================================================
-- PROYECTO : Agente de IA para consultar el cumplimiento SST / PESV
-- ARCHIVO  : 01_vistas_asistente.sql
-- CONTENIDO: Esquema "asistente" con dos vistas de solo lectura y un rol de
--            PostgreSQL que SOLO puede leer esas vistas.
-- REQUISITO: la base sst_pesv ya esta instalada (repo proyecto_base_de_datos_en_PostgreSQL).
-- USO      : psql -U postgres -d sst_pesv -v clave='UNA_CLAVE_SEGURA' -f sql/01_vistas_asistente.sql
-- Es re-ejecutable: no borra datos.
--
-- POR QUE EXISTE: un agente de IA decide por su cuenta que consultar. Por eso
-- nunca se le da acceso a las tablas ni la posibilidad de escribir SQL libre:
--   1) solo ve estas vistas (sin datos personales: nada de cedulas, correos ni telefonos);
--   2) cada herramienta del agente ejecuta una consulta fija con parametros;
--   3) el rol no puede insertar, modificar ni borrar nada.
-- =====================================================================
\set ON_ERROR_STOP on

DO $$
BEGIN
    IF current_database() <> 'sst_pesv' THEN
        RAISE EXCEPTION 'Base equivocada: estas en "%". Conectate a sst_pesv.', current_database();
    END IF;
END $$;

CREATE SCHEMA IF NOT EXISTS asistente;

-- ---------------------------------------------------------------------
-- V1: cumplimiento por organizacion y sistema (SST / PESV).
-- Solo organizaciones activas y plantillas activas.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW asistente.v_cumplimiento AS
SELECT
    t.id                                                       AS tenant_id,
    t.name                                                     AS organizacion,
    s.code                                                     AS sistema,
    COUNT(d.id)::int                                           AS total_documentos,
    COUNT(*) FILTER (WHERE d.status = 'FINALIZADO')::int       AS finalizados,
    COUNT(*) FILTER (WHERE d.status = 'BORRADOR')::int         AS borradores,
    COUNT(*) FILTER (WHERE d.status = 'NO_INICIADO')::int      AS no_iniciados,
    ROUND(100.0 * COUNT(*) FILTER (WHERE d.status = 'FINALIZADO')
          / NULLIF(COUNT(d.id), 0), 1)                         AS porcentaje_cumplimiento
FROM documents        d
JOIN tenants          t  ON t.id  = d.tenant_id
JOIN tenanttemplates  tt ON tt.id = d.tenanttemplate_id
JOIN templates        tp ON tp.id = tt.template_id
JOIN type_system_sst  s  ON s.id  = tp.type_system_sst_id
WHERE t.is_active
  AND tt.is_active
GROUP BY t.id, t.name, s.code;

-- ---------------------------------------------------------------------
-- V2: un renglon por documento, con sus dias sin cambios.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW asistente.v_documentos AS
SELECT
    d.id                                AS documento_id,
    t.id                                AS tenant_id,
    t.name                              AS organizacion,
    s.code                              AS sistema,
    d.title                             AS titulo,
    d.status                            AS estado,
    CURRENT_DATE - d.updated_at::date   AS dias_sin_cambios,
    d.updated_at::date                  AS ultima_actualizacion,
    d.finalized_at::date                AS fecha_finalizacion
FROM documents        d
JOIN tenants          t  ON t.id  = d.tenant_id
JOIN tenanttemplates  tt ON tt.id = d.tenanttemplate_id
JOIN templates        tp ON tp.id = tt.template_id
JOIN type_system_sst  s  ON s.id  = tp.type_system_sst_id
WHERE t.is_active
  AND tt.is_active;

-- ---------------------------------------------------------------------
-- ROL DEL AGENTE (minimo privilegio)
-- Las vistas se ejecutan con los permisos de su dueno, asi que el rol no
-- necesita (ni tiene) acceso a las tablas de public. La clave llega por la
-- variable de psql :clave y no queda en el repositorio.
-- ---------------------------------------------------------------------
-- Si el rol ya existe, su clave NO se modifica. Para cambiarla: ALTER ROLE asistente_ia PASSWORD 'nueva_clave';
SELECT format('CREATE ROLE asistente_ia LOGIN PASSWORD %L', :'clave')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'asistente_ia')
\gexec

GRANT CONNECT ON DATABASE sst_pesv TO asistente_ia;
GRANT USAGE   ON SCHEMA asistente  TO asistente_ia;
GRANT SELECT  ON asistente.v_cumplimiento, asistente.v_documentos TO asistente_ia;
