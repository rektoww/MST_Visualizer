-- История вычислений минимального остовного дерева
CREATE TABLE IF NOT EXISTS calculations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    algorithm VARCHAR(20) NOT NULL CHECK (algorithm IN ('kruskal', 'prim')),
    run_mode VARCHAR(10) NOT NULL CHECK (run_mode IN ('build', 'step')),
    vertex_count INTEGER NOT NULL CHECK (vertex_count > 0),
    edge_count INTEGER NOT NULL CHECK (edge_count >= 0),
    graph_data JSONB NOT NULL,
    result_edges JSONB NOT NULL,
    steps JSONB NOT NULL,
    total_weight DOUBLE PRECISION NOT NULL,
    duration_ms DOUBLE PRECISION NOT NULL CHECK (duration_ms >= 0)
);

-- Журнал событий приложения
CREATE TABLE IF NOT EXISTS event_logs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    level VARCHAR(10) NOT NULL CHECK (level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    source VARCHAR(100) NOT NULL,
    event_code VARCHAR(100) NOT NULL,
    message TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    calculation_id BIGINT REFERENCES calculations(id) ON DELETE SET NULL
);

-- Индексы для поиска и сортировки
CREATE INDEX IF NOT EXISTS idx_calculations_created_at ON calculations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_event_logs_created_at ON event_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_event_logs_calculation_id ON event_logs(calculation_id);
