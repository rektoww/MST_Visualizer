-- История вычислений минимального остовного дерева
CREATE TABLE IF NOT EXISTS calculations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    algorithm TEXT NOT NULL,
    run_mode TEXT NOT NULL,
    vertex_count INTEGER NOT NULL,
    edge_count INTEGER NOT NULL,
    graph_data JSONB NOT NULL,
    result_edges JSONB NOT NULL,
    steps JSONB NOT NULL,
    total_weight DOUBLE PRECISION NOT NULL,
    duration_ms DOUBLE PRECISION NOT NULL
);

-- Журнал событий приложения
CREATE TABLE IF NOT EXISTS event_logs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    level TEXT NOT NULL,
    source TEXT NOT NULL,
    event_code TEXT NOT NULL,
    message TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    calculation_id BIGINT REFERENCES calculations(id) ON DELETE SET NULL
);

-- Apply the same constraints to fresh installations and existing volumes.
-- Existing invalid rows are preserved. NOT VALID still checks new writes.
DO $$
DECLARE
    rule record;
BEGIN
    LOCK TABLE calculations, event_logs IN SHARE ROW EXCLUSIVE MODE;
    FOR rule IN
        SELECT * FROM (VALUES
            ('calculations'::regclass, 'calculations_algorithm_check', $rule$algorithm IN ('kruskal', 'prim')$rule$),
            ('calculations'::regclass, 'calculations_run_mode_check', $rule$run_mode IN ('build', 'step')$rule$),
            ('calculations'::regclass, 'calculations_vertex_count_check', 'vertex_count > 0'),
            ('calculations'::regclass, 'calculations_edge_count_check', 'edge_count >= 0'),
            ('calculations'::regclass, 'calculations_duration_ms_check', 'duration_ms >= 0'),
            ('calculations'::regclass, 'calculations_finite_result_check',
             $rule$total_weight > '-Infinity' AND total_weight < 'Infinity' AND duration_ms < 'Infinity'$rule$),
            ('event_logs'::regclass, 'event_logs_level_check', $rule$level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')$rule$),
            ('event_logs'::regclass, 'event_logs_source_length_check', 'char_length(source) <= 100'),
            ('event_logs'::regclass, 'event_logs_code_length_check', 'char_length(event_code) <= 100')
        ) AS rules(table_name, constraint_name, predicate)
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conrelid = rule.table_name AND conname = rule.constraint_name
        ) THEN
            EXECUTE format('ALTER TABLE %s ADD CONSTRAINT %I CHECK (%s) NOT VALID',
                           rule.table_name, rule.constraint_name, rule.predicate);
        END IF;

        BEGIN
            EXECUTE format('ALTER TABLE %s VALIDATE CONSTRAINT %I', rule.table_name, rule.constraint_name);
        EXCEPTION WHEN check_violation THEN
            RAISE WARNING 'Existing rows in % conflict with constraint %; rows preserved',
                          rule.table_name, rule.constraint_name;
        END;
    END LOOP;
END
$$;

-- Индексы для поиска и сортировки
CREATE INDEX IF NOT EXISTS idx_calculations_created_at ON calculations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_event_logs_created_at ON event_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_event_logs_calculation_id ON event_logs(calculation_id);
