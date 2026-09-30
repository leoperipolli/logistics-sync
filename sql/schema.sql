-- Schema usado pelo logistics-sync (PostgreSQL 15+).
-- O painel que lê estas tabelas não faz parte deste repositório.

CREATE TABLE IF NOT EXISTS cidades (
  id   SMALLSERIAL PRIMARY KEY,
  nome TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS transportadoras (
  id   SMALLSERIAL PRIMARY KEY,
  nome TEXT NOT NULL UNIQUE
);

INSERT INTO transportadoras (id, nome) VALUES
  (1, 'Transportadora A'),
  (2, 'Transportadora B'),
  (3, 'Transportadora C'),
  (4, 'Transportadora D'),
  (5, 'Transportadora E')
ON CONFLICT DO NOTHING;

CREATE SEQUENCE IF NOT EXISTS volumes_doc_interno_seq;

CREATE TABLE IF NOT EXISTS volumes (
  id                 BIGSERIAL PRIMARY KEY,
  doc_interno        TEXT NOT NULL UNIQUE,          -- gerado por trigger: VOL + AA + MM + sequência
  transportadora_id  SMALLINT REFERENCES transportadoras (id),
  cod_transportadora TEXT,                          -- código do volume no sistema da transportadora
  cidade_id          SMALLINT NOT NULL REFERENCES cidades (id),
  bairro             TEXT,
  data_insercao      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  data_vencimento    DATE NOT NULL,
  data_entrega       DATE,
  status             TEXT,
  data_ult_status    TIMESTAMPTZ,
  data_ult_busca     TIMESTAMPTZ,
  atencao            BOOLEAN NOT NULL DEFAULT FALSE,
  observacao_cliente TEXT,
  observacao_interna TEXT,
  resolvido          BOOLEAN NOT NULL DEFAULT FALSE,
  resolvido_no_prazo BOOLEAN GENERATED ALWAYS AS (
    data_entrega IS NOT NULL AND data_vencimento IS NOT NULL AND data_entrega <= data_vencimento
  ) STORED,
  CONSTRAINT chk_doc_interno CHECK (doc_interno ~ '^VOL\d{2}\d{2}\d{8}$'),
  CONSTRAINT chk_resolvido_entregue CHECK (resolvido = FALSE OR status = 'entregue'),
  CONSTRAINT volumes_status_check CHECK (
    status IN ('recebido', 'em_manifesto', 'em_rota', 'entregue', 'tratativa')
  )
);

CREATE INDEX IF NOT EXISTS idx_volumes_data_insercao ON volumes (data_insercao);
CREATE INDEX IF NOT EXISTS idx_volumes_data_vencimento ON volumes (data_vencimento);
CREATE INDEX IF NOT EXISTS idx_volumes_status ON volumes (status);
CREATE INDEX IF NOT EXISTS idx_volumes_transportadora ON volumes (transportadora_id);
CREATE INDEX IF NOT EXISTS idx_volumes_cod_transportadora ON volumes (cod_transportadora);
CREATE INDEX IF NOT EXISTS idx_volumes_atencao ON volumes (atencao) WHERE atencao = TRUE;
CREATE INDEX IF NOT EXISTS idx_volumes_resolvido ON volumes (resolvido) WHERE resolvido = FALSE;

CREATE TABLE IF NOT EXISTS log_execucoes (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_name  TEXT NOT NULL,
  started_at     TIMESTAMPTZ,
  finished_at    TIMESTAMPTZ,
  execution_ms   INTEGER,
  volumes_lidos  INTEGER,
  status         TEXT,
  status_message TEXT
);

CREATE TABLE IF NOT EXISTS log_execucoes_detalhes (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  execucao_id UUID NOT NULL REFERENCES log_execucoes (id) ON DELETE CASCADE,
  caso        TEXT NOT NULL,          -- chave de classificação, ex.: "010", "101"
  quantidade  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_log_detalhes_execucao ON log_execucoes_detalhes (execucao_id);

-- Triggers --------------------------------------------------------------------

-- doc_interno gerado automaticamente quando o INSERT não informa o campo
CREATE OR REPLACE FUNCTION gerar_doc_interno() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.doc_interno := 'VOL' || TO_CHAR(NOW(), 'YY') || TO_CHAR(NOW(), 'MM')
                     || LPAD(nextval('volumes_doc_interno_seq')::TEXT, 8, '0');
  RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trigger_doc_interno
BEFORE INSERT ON volumes
FOR EACH ROW
WHEN (NEW.doc_interno IS NULL OR NEW.doc_interno = '')
EXECUTE FUNCTION gerar_doc_interno();

-- data da última sincronização em todo INSERT/UPDATE
CREATE OR REPLACE FUNCTION set_data_ult_busca() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.data_ult_busca := NOW();
  RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_data_ult_busca
BEFORE INSERT OR UPDATE ON volumes
FOR EACH ROW
EXECUTE FUNCTION set_data_ult_busca();

-- regras de negócio: resolvido limpa atenção; entrega limpa observação de conflito
CREATE OR REPLACE FUNCTION handle_volume_business_rules() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.resolvido = TRUE AND NEW.atencao = TRUE THEN
    NEW.atencao := FALSE;
  END IF;

  IF TG_OP = 'UPDATE'
     AND NEW.status = 'entregue'
     AND OLD.observacao_interna ILIKE '%conflito%' THEN
    NEW.observacao_interna := NULL;
  END IF;

  RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_volume_business_rules
BEFORE INSERT OR UPDATE ON volumes
FOR EACH ROW
EXECUTE FUNCTION handle_volume_business_rules();
