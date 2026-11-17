
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
